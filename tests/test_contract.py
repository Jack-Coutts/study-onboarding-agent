"""The contract checker accepts reference outputs and rejects each rule violation."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

from contract.input_contract import check_contract
from onboard.fixtures import Fixture, list_fixtures
from reference.broken import build_variant
from reference.workbench_rest import ConversionError, prepare

ALL = list_fixtures("dev") + list_fixtures("heldout")
BY_ID = {f.id: f for f in ALL}


def check(fixture: Fixture, output: Path) -> list[str]:
    return [v.rule for v in check_contract(output, fixture.factors, fixture.data, fixture.task)]


def reference_output(fixture: Fixture, tmp_path: Path) -> Path:
    output = tmp_path / "out"
    prepare(fixture.factors, fixture.data, fixture.task, output)
    return output


def variant_output(variant: str, fixture: Fixture, tmp_path: Path) -> Path:
    path = tmp_path / f"broken_{variant}.py"
    path.write_text(build_variant(variant))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module  # dataclasses look their module up here
    try:
        spec.loader.exec_module(module)
        output = tmp_path / variant
        module.prepare(fixture.factors, fixture.data, fixture.task, output)
    finally:
        del sys.modules[path.stem]
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
