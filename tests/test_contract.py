"""The contract checker accepts reference outputs and rejects each rule violation."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import yaml

from contract.input_contract import check_contract
from onboard.fixtures import Fixture, list_fixtures
from reference.workbench_rest import ConversionError, prepare
from tests.fakes import load_variant

ALL = list_fixtures("dev") + list_fixtures("heldout")
BY_ID = {f.id: f for f in ALL}


def check(fixture: Fixture, output: Path) -> list[str]:
    return [v.rule for v in check_contract(output, fixture.factors, fixture.data, fixture.task)]


def reference_output(fixture: Fixture, tmp_path: Path) -> Path:
    output = tmp_path / "out"
    prepare(fixture.factors, fixture.data, fixture.task, output)
    return output


def variant_output(variant: str, fixture: Fixture, tmp_path: Path) -> Path:
    output = tmp_path / variant
    load_variant(variant).prepare(fixture.factors, fixture.data, fixture.task, output)
    return output


def rewrite_csv(path: Path, edit) -> None:
    with path.open(newline="") as handle:
        grid = [list(row) for row in csv.reader(handle)]
    edit(grid)
    with path.open("w", newline="") as handle:
        csv.writer(handle, lineterminator="\n").writerows(grid)


def rewrite_json(path: Path, edit) -> None:
    value = json.loads(path.read_text())
    edit(value)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize("fixture", ALL, ids=[f.id for f in ALL])
def test_reference_output_satisfies_the_contract(fixture, tmp_path):
    try:
        output = reference_output(fixture, tmp_path)
    except ConversionError:
        assert fixture.expects_error
        output = tmp_path / "empty"
        output.mkdir()
    assert check(fixture, output) == []


# Broken variants that still write output must be rejected by the rule they break.
@pytest.mark.parametrize(
    ("variant", "fixture_id", "rule"),
    [
        ("B2", "D2", "kept_samples"),
        ("B3", "D3", "technical"),
        ("B4", "H2", "conflicts"),
        ("B5", "D1", "kept_samples"),
        ("B6", "D4", "kept_samples"),
        ("B7", "H1", "duplicates"),
        ("B8", "H3", "unique_names"),
    ],
)
def test_contract_rejects_broken_variant_output(variant, fixture_id, rule, tmp_path):
    fixture = BY_ID[fixture_id]
    assert rule in check(fixture, variant_output(variant, fixture, tmp_path))


def _drop(name):
    def edit(output: Path) -> None:
        (output / name).unlink()

    return edit


def _csv(edit):
    return lambda output: rewrite_csv(output / "prepared.csv", edit)


def _summary(edit):
    return lambda output: rewrite_json(output / "summary.json", edit)


def _config(key, value):
    def edit(output: Path) -> None:
        config = yaml.safe_load((output / "config.yaml").read_text())
        config[key] = value
        (output / "config.yaml").write_text(yaml.safe_dump(config))

    return edit


def _swap_rows(grid):
    grid[2], grid[3] = grid[3], grid[2]


def _numeric_id(grid):
    grid[2][0] = "2"  # "002" read as a number


def _unsorted_extras(grid):
    for row in grid:
        row[2], row[3] = row[3], row[2]


def _qc_phenotype(grid):
    grid[2][1] = "case"


def _na_as_blank(grid):
    grid[2][1] = ""


def _method(grid):
    grid[1][0] = "Method"


def _wrong_analysis(grid):
    grid[1][-1] = "AN999999"


def _excluded_and_kept(summary):
    summary["excluded_samples"]["S01"] = "no phenotype"


def _forget_excluded(summary):
    summary["excluded_samples"] = {}


def _wrong_count(summary):
    summary["n_samples"] = 99


def _drop_key(summary):
    del summary["blank_technical_columns"]


@pytest.mark.parametrize(
    ("fixture_id", "mutate", "rule"),
    [
        ("D1", _drop("summary.json"), "files"),
        ("D1", _csv(_swap_rows), "rows"),
        ("D4", _csv(_numeric_id), "identifiers"),
        ("D3", _csv(_unsorted_extras), "layout"),
        ("D1", _csv(_qc_phenotype), "controls"),
        ("D4", _csv(_na_as_blank), "phenotype"),
        ("D1", _csv(_method), "layout"),
        ("D2", _csv(_wrong_analysis), "layout"),
        ("D1", _summary(_excluded_and_kept), "accounting"),
        ("D1", _summary(_forget_excluded), "accounting"),
        ("D1", _summary(_wrong_count), "summary"),
        ("D1", _summary(_drop_key), "summary"),
        ("D1", _config("feature_start_column", 6), "config"),
        ("D1", _config("qc_sample_types", []), "config"),
        ("D2", _config("data_start_row", 2), "config"),
    ],
)
def test_contract_rejects_each_rule_violation(fixture_id, mutate, rule, tmp_path):
    fixture = BY_ID[fixture_id]
    output = reference_output(fixture, tmp_path)
    assert check(fixture, output) == []
    mutate(output)
    assert rule in check(fixture, output)


def _deposit(tmp_path: Path, factors: dict[str, str], names: list[str], task: str) -> Fixture:
    directory = tmp_path / "deposit"
    directory.mkdir()
    (directory / "factors.json").write_text(
        json.dumps(
            {
                str(i): {"local_sample_id": s, "factors": f}
                for i, (s, f) in enumerate(factors.items(), 1)
            }
        )
    )
    data = {
        str(i): {"analysis_id": "AN1", "metabolite_name": name, "DATA": {s: "1" for s in factors}}
        for i, name in enumerate(names, 1)
    }
    (directory / "data.json").write_text(json.dumps(data))
    (directory / "task.yaml").write_text(task)
    return Fixture(id="tmp", split="dev", directory=directory)


def test_reference_output_with_numbered_metadata_names_is_accepted(tmp_path):
    fixture = _deposit(
        tmp_path,
        {"A": "Diagnosis:x | Phenotype:old label | Samples:3", "B": "Diagnosis:y"},
        ["Batch", "Phenotype.1", "Valine"],
        "phenotype_key: Diagnosis\n",
    )
    output = reference_output(fixture, tmp_path)
    header = (output / "prepared.csv").read_text().splitlines()[0].split(",")
    assert header[:7] == [
        "Samples",
        "Phenotype",
        "Phenotype.2",
        "Samples.1",
        "Sample type",
        "Batch",
        "Injection order",
    ]
    assert header[7:] == ["Batch.1", "Phenotype.1", "Valine"]
    assert check(fixture, output) == []


def test_contract_rejects_a_misnumbered_feature_name(tmp_path):
    fixture = _deposit(tmp_path, {"A": "G:x"}, ["Batch", "Valine"], "phenotype_key: G\n")
    output = reference_output(fixture, tmp_path)
    rewrite_csv(output / "prepared.csv", lambda grid: grid[0].__setitem__(5, "Batch_2"))
    assert "feature_names" in check(fixture, output)


def test_factors_naming_one_technical_column_twice_must_stop(tmp_path):
    fixture = _deposit(tmp_path, {"A": "G:x | Batch:1 | batch:2"}, ["Valine"], "phenotype_key: G\n")
    with pytest.raises(ConversionError, match="Batch"):
        reference_output(fixture, tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert check(fixture, empty) == []
    (empty / "prepared.csv").write_text("Samples\n")
    assert check(fixture, empty) == ["conflicts"]


def test_unreadable_output_is_a_violation_not_a_crash(tmp_path):
    fixture = BY_ID["D1"]
    output = reference_output(fixture, tmp_path)
    (output / "prepared.csv").write_bytes(b"\xff\xfe\x00bad")
    (output / "summary.json").write_bytes(b"\xff")
    assert check(fixture, output) == ["files", "files"]


@pytest.mark.parametrize(
    ("header", "pandas_columns"),
    [
        (["a", "a", "a.1", "a.1", "a"], ["a", "a.2", "a.1", "a.1.1", "a.3"]),
        (["x.1", "x", "x", "x.1"], ["x.1", "x", "x.2", "x.1.1"]),
    ],
)
def test_contract_numbers_headers_as_pandas_does(header, pandas_columns):
    from contract.input_contract import number_like_pandas

    assert number_like_pandas(header) == pandas_columns


# Findings from the Amp review of 641675d.


def test_contract_rejects_a_blank_cell_written_as_zero(tmp_path):
    fixture = BY_ID["D1"]
    output = reference_output(fixture, tmp_path)
    rewrite_csv(output / "prepared.csv", lambda grid: grid[6].__setitem__(6, "0"))  # S03 Alanine
    assert "values" in check(fixture, output)


def test_contract_rejects_zero_for_a_sample_missing_from_one_record(tmp_path):
    fixture = BY_ID["D1"]  # QC2 is measured in AN000101 but missing from the Glucose record
    output = reference_output(fixture, tmp_path)
    rewrite_csv(output / "prepared.csv", lambda grid: grid[3].__setitem__(7, "0"))  # QC2 Glucose
    assert "values" in check(fixture, output)


def test_contract_requires_a_stop_on_a_record_that_repeats_a_factor(tmp_path):
    fixture = _deposit(
        tmp_path, {"A": "G:case | G:control", "B": "G:case"}, ["x"], "phenotype_key: G\n"
    )
    with pytest.raises(ConversionError):
        reference_output(fixture, tmp_path)
    written = tmp_path / "written"
    written.mkdir()
    (written / "prepared.csv").write_text("Samples\n")
    assert check(fixture, written) == ["conflicts"]


def test_unnamed_features_are_never_merged_across_analyses(tmp_path):
    directory = tmp_path / "deposit"
    directory.mkdir()
    (directory / "factors.json").write_text(
        json.dumps({"1": {"local_sample_id": "A", "factors": "G:x"}})
    )
    records = [
        ("AN1", "unnamed", ""),
        ("AN2", "unnamed", ""),
        ("AN1", "", ""),
        ("AN2", "", ""),
    ]
    data = {
        str(i): {"analysis_id": a, "metabolite_name": m, "refmet_name": r, "DATA": {"A": str(i)}}
        for i, (a, m, r) in enumerate(records, 1)
    }
    (directory / "data.json").write_text(json.dumps(data))
    (directory / "task.yaml").write_text("phenotype_key: G\n")
    fixture = Fixture(id="tmp", split="dev", directory=directory)
    output = reference_output(fixture, tmp_path)
    header = (output / "prepared.csv").read_text().splitlines()[0].split(",")
    assert header[5:] == ["unnamed", "unnamed.1", "unnamed.2", "unnamed.3"]
    assert check(fixture, output) == []


def _wrong_reason(summary):
    summary["excluded_samples"]["P3"] = "no phenotype"


def _invented_drop(summary):
    summary["duplicate_metabolites_dropped"].append(
        {"metabolite": "Valine", "analysis_id": "AN000202", "kept_from": "AN000201"}
    )


@pytest.mark.parametrize("mutate", [_wrong_reason, _invented_drop])
def test_contract_checks_the_audit_in_the_summary(tmp_path, mutate):
    fixture = BY_ID["D2"]
    output = reference_output(fixture, tmp_path)
    rewrite_json(output / "summary.json", mutate)
    assert "summary" in check(fixture, output)


# Technical factors spelled differently in different samples are one column
# (decisions/technical-columns.md); one sample giving two values stops the run.


def test_spellings_that_differ_in_case_are_one_technical_column(tmp_path):
    fixture = _deposit(
        tmp_path,
        {
            "A": "G:x | Sample type:Sample | Batch:1",
            "B": "G:y | SAMPLE TYPE:qc | batch:2",
            "C": "G:x | sample type:Sample | BATCH:2 | Batch:2",
        },
        ["m"],
        "phenotype_key: G\ncontrol_sample_types: [QC]\n",
    )
    output = reference_output(fixture, tmp_path)
    rows = [r.split(",") for r in (output / "prepared.csv").read_text().splitlines()]
    assert rows[0][:5] == ["Samples", "Phenotype", "Sample type", "Batch", "Injection order"]
    assert [r[:4] for r in rows[2:]] == [
        ["A", "x", "subject", "1"],
        ["B", "", "qc", "2"],
        ["C", "x", "subject", "2"],
    ]
    assert check(fixture, output) == []


def test_one_sample_giving_two_spellings_different_values_must_stop(tmp_path):
    fixture = _deposit(
        tmp_path,
        {"A": "G:x | Batch:1", "S7": "G:y | Batch:1 | batch:2"},
        ["m"],
        "phenotype_key: G\n",
    )
    with pytest.raises(ConversionError, match="S7"):
        reference_output(fixture, tmp_path)
    written = tmp_path / "written"
    written.mkdir()
    (written / "prepared.csv").write_text("Samples\n")
    assert check(fixture, written) == ["conflicts"]
