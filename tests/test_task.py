"""onboard draft-task pre-fills a task file; runs refuse one that is unfinished."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from onboard.fetch import fetch_study
from onboard.task import TaskError, draft_task, resolve_task

FACTORS = {
    "1": {"local_sample_id": "A1", "factors": "Genotype:wt | Treatment:Control"},
    "2": {"local_sample_id": "A2", "factors": "Genotype:ko | Treatment:Wounded"},
    "3": {"local_sample_id": "A3", "factors": "Genotype:ko | Treatment:Control"},
}
DATA = {
    "1": {"analysis_id": "AN000002", "metabolite_name": "x", "DATA": {"A1": "1"}},
    "2": {"analysis_id": "AN000001", "metabolite_name": "y", "DATA": {"A1": "2"}},
}
SUMMARY = {"study_id": "ST000123", "study_title": "Wounding\nexperiment"}


def fetched(tmp_path: Path, factors=FACTORS) -> Path:
    bodies = {"factors": factors, "data": DATA, "summary": SUMMARY}
    fetch_study(
        "ST000123",
        root=tmp_path,
        opener=lambda url: json.dumps(bodies[url.rsplit("/", 1)[1]]).encode(),
    )
    return tmp_path


def test_draft_lists_the_choices_and_fills_in_only_facts(tmp_path):
    root = fetched(tmp_path)
    path = draft_task("ST000123", root=root)
    text = path.read_text()

    assert path == root / "tasks" / "draft-ST000123.yaml"
    task = yaml.safe_load(text)
    assert task == {
        "study_id": "ST000123",
        "phenotype_key": "CHOOSE",
        "control_sample_types": ["QC", "PBQC", "pool", "blank"],
    }
    # Analysis IDs are listed for the person in a comment, never as a setting.
    assert "# Analyses found: AN000001, AN000002." in text
    assert "Genotype" in text and "ko (2), wt (1)" in text
    assert "Control (2), Wounded (1)" in text
    assert "No sample-type factor" in text
    assert "Batch" in text and "Injection order" in text
    assert "Wounding experiment" in text  # a title's newline cannot break out of the comment


def test_draft_shows_sample_types_and_recorded_technical_factors(tmp_path):
    factors = {
        "1": {"local_sample_id": "A1", "factors": "G:x | Sample type:QC | Batch:1"},
        "2": {"local_sample_id": "A2", "factors": "G:y | Sample type:Sample | Batch:2"},
    }
    text = draft_task("ST000123", root=fetched(tmp_path, factors)).read_text()
    assert "QC (1), Sample (1)" in text
    assert "No sample-type factor" not in text
    assert "Heads-up: no Batch" not in text


def test_draft_does_not_overwrite_a_file(tmp_path):
    root = fetched(tmp_path)
    draft_task("ST000123", root=root)
    with pytest.raises(TaskError, match="already exists"):
        draft_task("ST000123", root=root)


def test_draft_needs_the_study_fetched_first(tmp_path):
    with pytest.raises(TaskError, match="onboard fetch ST000999"):
        draft_task("ST000999", root=tmp_path)


def test_runs_refuse_an_unfinished_draft(tmp_path):
    root = fetched(tmp_path)
    path = draft_task("ST000123", root=root)
    with pytest.raises(TaskError, match="CHOOSE"):
        resolve_task(path, root=root)
    path.write_text(path.read_text().replace("phenotype_key: CHOOSE", "phenotype_key: Treatment"))
    assert resolve_task(path, root=root).study_id == "ST000123"


# Amp review of 435a7d4: deposit text must stay inside comments, and the lock
# must find CHOOSE anywhere in the task's values.
@pytest.mark.parametrize("brk", ["\n", "\r", "\u2028", "\x85"])
def test_factor_text_cannot_add_task_settings(tmp_path, brk):
    factors = {
        "1": {"local_sample_id": "A1", "factors": f"Group:control | Notes:ok{brk}keep: [case] #"},
        "2": {"local_sample_id": "A2", "factors": f"Group:case | Sample type:QC{brk}map: {{a: b}}"},
        "3": {"local_sample_id": "A3", "factors": f"Bad{brk}analyses: [AN9]:x | Group:case"},
    }
    text = draft_task("ST000123", root=fetched(tmp_path, factors)).read_text()
    assert set(yaml.safe_load(text)) == {
        "study_id",
        "phenotype_key",
        "control_sample_types",
    }
    for line in text.splitlines():
        assert (
            line.startswith("#")
            or not line
            or line.split(":")[0] in {"study_id", "phenotype_key", "control_sample_types"}
        ), line


@pytest.mark.parametrize(
    "unfinished",
    [
        "map: {case: CHOOSE}",
        "map: {CHOOSE: case}",
        "keep: [CHOOSE]",
        "analyses: [CHOOSE]",
        "control_sample_types: [QC, CHOOSE]",
    ],
)
def test_runs_refuse_choose_anywhere_in_the_values(tmp_path, unfinished):
    root = fetched(tmp_path)
    path = draft_task("ST000123", root=root)
    text = path.read_text().replace("phenotype_key: CHOOSE", "phenotype_key: Treatment")
    key = unfinished.split(":")[0]
    path.write_text(
        "\n".join(line for line in text.splitlines() if not line.startswith(f"{key}:"))
        + f"\n{unfinished}\n"
    )
    with pytest.raises(TaskError, match=key):
        resolve_task(path, root=root)


# Amp review of 32b52f9.
def test_analysis_ids_cannot_add_task_settings(tmp_path):
    hostile = "AN000001]\nanalyses: [AN000001]\nkeep: [case]\n#"
    data = {
        "1": {"analysis_id": "AN000001", "metabolite_name": "x", "DATA": {"A1": "1"}},
        "2": {"analysis_id": hostile, "metabolite_name": "y", "DATA": {"A1": "2"}},
    }
    bodies = {"factors": FACTORS, "data": data, "summary": SUMMARY}
    fetch_study(
        "ST000123",
        root=tmp_path,
        opener=lambda url: json.dumps(bodies[url.rsplit("/", 1)[1]]).encode(),
    )
    task = yaml.safe_load(draft_task("ST000123", root=tmp_path).read_text())
    assert set(task) == {"study_id", "phenotype_key", "control_sample_types"}


def test_draft_counts_samples_not_records(tmp_path):
    factors = {
        "1": {"local_sample_id": "A1", "factors": "Group:control"},
        "2": {"local_sample_id": "A1", "factors": "Group:control"},
        "3": {"local_sample_id": "A2", "factors": "Group:case"},
    }
    text = draft_task("ST000123", root=fetched(tmp_path, factors)).read_text()
    assert "(2 samples)" in text
    assert "control (1), case (1)" in text
    assert "1 factor record repeats a sample" in text


@pytest.mark.parametrize("study_id", ["../ST000123", "ST000123\nkeep: [x]", "123"])
def test_draft_rejects_malformed_study_ids(tmp_path, study_id):
    with pytest.raises(TaskError, match="must look like ST000123"):
        draft_task(study_id, root=tmp_path)


def test_a_factor_repeated_within_one_record_counts_once(tmp_path):
    factors = {
        "1": {"local_sample_id": "A1", "factors": "Group:control | Group:control"},
        "2": {"local_sample_id": "A2", "factors": "Group:case"},
    }
    text = draft_task("ST000123", root=fetched(tmp_path, factors)).read_text()
    assert "control (1), case (1)" in text


# Amp review of 463035c: characters YAML forbids, even in comments, must not
# make the draft unloadable.
@pytest.mark.parametrize("char", ["\x00", "\x07", "\x7f", "￾"])
def test_control_characters_in_study_text_keep_the_draft_loadable(tmp_path, char):
    factors = {"1": {"local_sample_id": "A1", "factors": f"Group:ca{char}se | No{char}te:x"}}
    bodies = {"factors": factors, "data": DATA, "summary": {"study_title": f"title{char}suffix"}}
    fetch_study(
        "ST000123",
        root=tmp_path,
        opener=lambda url: json.dumps(bodies[url.rsplit("/", 1)[1]]).encode(),
    )
    path = draft_task("ST000123", root=tmp_path)
    path.write_text(path.read_text().replace("phenotype_key: CHOOSE", "phenotype_key: Group"))
    assert resolve_task(path, root=tmp_path).study_id == "ST000123"
    assert "titlesuffix" in path.read_text()


def test_a_task_saved_while_drafting_is_never_overwritten(tmp_path, monkeypatch):
    # Amp review of 70a4507: the existence check and the write must be one step.
    from onboard.tools import factors_digest as real

    root = fetched(tmp_path)
    target = root / "tasks" / "draft-ST000123.yaml"

    def save_a_task_mid_draft(records):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("phenotype_key: AlreadySelected\n")
        return real(records)

    monkeypatch.setattr("onboard.task.factors_digest", save_a_task_mid_draft)
    with pytest.raises(TaskError, match="already exists"):
        draft_task("ST000123", root=root)
    assert target.read_text() == "phenotype_key: AlreadySelected\n"


@pytest.mark.parametrize("analyses", ["[AN404]", "[AN000001, AN404]", "[]"])
def test_a_task_selecting_unknown_or_no_analyses_is_refused(tmp_path, analyses):
    # Amp review of 976b23d: converters wrote empty results for these and reported
    # success; the harness now refuses such a task before any run.
    root = fetched(tmp_path)
    task = root / "tasks" / "R1.yaml"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(f"study_id: ST000123\nphenotype_key: Treatment\nanalyses: {analyses}\n")
    with pytest.raises(TaskError, match="analyses"):
        resolve_task(task, root=root)
    task.write_text(
        "study_id: ST000123\nphenotype_key: Treatment\nanalyses: [AN000002, AN000001]\n"
    )
    assert resolve_task(task, root=root).study_id == "ST000123"
