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
        "analyses": ["AN000001", "AN000002"],
        "control_sample_types": ["QC", "PBQC", "pool", "blank"],
    }
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
        "analyses",
        "control_sample_types",
    }
    assert yaml.safe_load(text)["analyses"] == ["AN000001", "AN000002"]
    for line in text.splitlines():
        assert (
            line.startswith("#")
            or not line
            or line.split(":")[0]
            in {"study_id", "phenotype_key", "analyses", "control_sample_types"}
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
