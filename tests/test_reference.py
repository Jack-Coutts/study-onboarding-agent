"""The reference converter passes every fixture; each broken variant fails one.

The reference and broken variants are trusted code written for this repository,
so they run on the host. Generated converters never do.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from onboard.compare import compare_result
from onboard.fixtures import Fixture, list_fixtures
from reference.broken import VARIANTS, build_variant

REFERENCE = Path(__file__).resolve().parents[1] / "reference" / "workbench_rest.py"
ALL = list_fixtures("dev") + list_fixtures("heldout")


def run_converter(script: Path, fixture: Fixture, output: Path) -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--factors",
            str(fixture.factors),
            "--data",
            str(fixture.data),
            "--task",
            str(fixture.task),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return compare_result(result.returncode, result.stderr, output, fixture.expected)


@pytest.mark.parametrize("fixture", ALL, ids=[f.id for f in ALL])
def test_reference_matches_expected_output(fixture, tmp_path):
    assert run_converter(REFERENCE, fixture, tmp_path / "out") == []


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_broken_variant_fails_at_least_one_fixture(variant, tmp_path):
    script = tmp_path / "prepare.py"
    script.write_text(build_variant(variant))
    failing = [f.id for f in ALL if run_converter(script, f, tmp_path / f.id)]
    assert failing, f"{variant} passes every fixture, so it does not exercise its mistake"


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_broken_variant_differs_from_reference_in_one_place(variant):
    reference = REFERENCE.read_text()
    source = build_variant(variant)
    assert source != reference
    compile(source, f"{variant}.py", "exec")


def test_reference_runs_as_a_function(tmp_path):
    from reference.workbench_rest import prepare

    fixture = list_fixtures("dev")[0]
    prepare(fixture.factors, fixture.data, fixture.task, tmp_path)
    assert compare_result(0, "", tmp_path, fixture.expected) == []


# Observed from pandas 3.0.6 `read_csv` (C parser) on these header rows.
@pytest.mark.parametrize(
    ("header", "pandas_columns"),
    [
        (["x", "y", "x", "x"], ["x", "y", "x.1", "x.2"]),
        (["a", "a", "a.1", "a.1", "a"], ["a", "a.2", "a.1", "a.1.1", "a.3"]),
        (["x.1", "x", "x", "x.1"], ["x.1", "x", "x.2", "x.1.1"]),
        (["a", "b", "a", "a.2", "a"], ["a", "b", "a.1", "a.2", "a.3"]),
    ],
)
def test_repeated_names_are_numbered_as_pandas_reads_them(header, pandas_columns):
    from reference.workbench_rest import number_repeated

    assert number_repeated(header) == pandas_columns


def test_a_record_giving_one_factor_two_values_names_its_sample(tmp_path):
    # Found by a gpt-6.1-sol run's tests: the error named the factor but not the sample.
    import json

    from reference.workbench_rest import ConversionError, prepare

    (tmp_path / "f.json").write_text(
        json.dumps({"1": {"local_sample_id": "S07", "factors": "Group:case | Group:control"}})
    )
    (tmp_path / "d.json").write_text(
        json.dumps({"1": {"analysis_id": "AN1", "metabolite_name": "m", "DATA": {"S07": "1"}}})
    )
    (tmp_path / "t.yaml").write_text("phenotype_key: Group\n")
    with pytest.raises(ConversionError, match="S07"):
        prepare(tmp_path / "f.json", tmp_path / "d.json", tmp_path / "t.yaml", tmp_path / "out")
    assert not (tmp_path / "out").exists()
