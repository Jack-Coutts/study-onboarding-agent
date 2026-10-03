"""Development checks: static analysis, contract, dev fixtures, generated tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from onboard.fixtures import list_fixtures
from onboard.validate import development_checks, static_check
from tests.fakes import FakeSandbox

REPO = Path(__file__).resolve().parents[1]
GOOD_TEST = "from prepare import prepare\n\n\ndef test_runs(tmp_path):\n    assert prepare\n"


def version(tmp_path: Path, prepare_code: str, test_code: str = GOOD_TEST) -> Path:
    directory = tmp_path / "versions" / "v1"
    directory.mkdir(parents=True)
    (directory / "prepare.py").write_text(prepare_code)
    (directory / "test_prepare.py").write_text(test_code)
    return directory


def task_inputs(tmp_path: Path, fixture_id: str = "D1") -> Path:
    source = REPO / "fixtures" / "dev" / fixture_id
    target = tmp_path / "inputs"
    target.mkdir()
    for name in ("factors.json", "data.json", "summary.json", "task.yaml"):
        shutil.copyfile(source / name, target / name)
    return target


def test_static_check_accepts_the_reference(tmp_path):
    reference = (REPO / "reference" / "workbench_rest.py").read_text()
    assert static_check(version(tmp_path, reference)).ok


@pytest.mark.parametrize(
    ("prepare_code", "test_code", "problem"),
    [
        ("def prepare(:\n", GOOD_TEST, "prepare.py line 1"),
        ("import requests\ndef prepare(a, b, c, d): pass\n", GOOD_TEST, "'requests'"),
        ("from . import x\ndef prepare(a, b, c, d): pass\n", GOOD_TEST, "'.'"),
        ("def convert(a, b, c, d): pass\n", GOOD_TEST, "does not define"),
        ("def prepare(a, b): pass\n", GOOD_TEST, "must take"),
        ("def prepare(a, b, c, d): pass\n", "import prepare\n", "from prepare import prepare"),
        ("def prepare(a, b, c, d): pass\n", "import pytest, sklearn\n", "'sklearn'"),
    ],
)
def test_static_check_reports_problems(tmp_path, prepare_code, test_code, problem):
    check = static_check(version(tmp_path, prepare_code, test_code))
    assert not check.ok
    assert any(problem in p for p in check.details["problems"]), check.details


def test_reference_passes_every_development_check(tmp_path):
    reference = (REPO / "reference" / "workbench_rest.py").read_text()
    result = development_checks(
        "v1", version(tmp_path, reference), task_inputs(tmp_path), FakeSandbox(), tmp_path / "w"
    )
    assert result["overall"] == "ok", result
    assert set(result["checks"]) == {"static", "execution", "contract", "dev_fixtures", "tests"}
    assert set(result["checks"]["dev_fixtures"]["fixtures"]) == {"D1", "D2", "D3", "D4"}


def test_a_broken_converter_gets_a_cell_level_diff(tmp_path):
    reference = (REPO / "reference" / "workbench_rest.py").read_text()
    result = development_checks(
        "v1",
        version(tmp_path, reference),
        task_inputs(tmp_path, "D3"),
        FakeSandbox(variant="B3"),
        tmp_path / "w",
    )
    assert result["overall"] == "fail"
    assert result["checks"]["contract"]["status"] == "fail"
    d3 = result["checks"]["dev_fixtures"]["fixtures"]["D3"]
    assert "prepared.csv sample 'B1', column 'Batch': expected '', got '1'" in d3["diff"]


def test_failing_generated_tests_report_counts_and_first_failure(tmp_path):
    reference = (REPO / "reference" / "workbench_rest.py").read_text()
    result = development_checks(
        "v1",
        version(tmp_path, reference),
        task_inputs(tmp_path),
        FakeSandbox(tests_pass=False),
        tmp_path / "w",
    )
    tests = result["checks"]["tests"]
    assert (tests["status"], tests["passed"], tests["failed"]) == ("fail", 2, 1)
    assert tests["first_failure"].startswith("___ test_ids ___")


def test_only_converter_inputs_are_mounted(tmp_path):
    reference = (REPO / "reference" / "workbench_rest.py").read_text()
    sandbox = FakeSandbox()
    development_checks(
        "v1", version(tmp_path, reference), task_inputs(tmp_path), sandbox, tmp_path / "w"
    )
    for _, input_dir, _ in sandbox.converter_runs:
        assert sorted(p.name for p in input_dir.iterdir()) == [
            "data.json",
            "factors.json",
            "task.yaml",
        ]


def test_development_checks_refuse_held_out_fixtures(tmp_path):
    with pytest.raises(ValueError, match="dev fixtures"):
        development_checks(
            "v1",
            version(tmp_path, ""),
            task_inputs(tmp_path),
            FakeSandbox(),
            tmp_path / "w",
            fixtures=list_fixtures("heldout"),
        )


def test_a_timeout_is_reported(tmp_path):
    result = development_checks(
        "v1",
        version(tmp_path, "def prepare(a, b, c, d): pass\n"),
        task_inputs(tmp_path),
        FakeSandbox(timeout=True),
        tmp_path / "w",
    )
    assert result["sandbox_timed_out"] is True
    assert result["checks"]["execution"]["timed_out"] is True


REAL_TESTS = """
import json

from prepare import prepare


def deposit(tmp_path, factors, data, task):
    (tmp_path / "factors.json").write_text(json.dumps(factors))
    (tmp_path / "data.json").write_text(json.dumps(data))
    (tmp_path / "task.yaml").write_text(task)
    return [tmp_path / n for n in ("factors.json", "data.json", "task.yaml")]


def test_leading_zeros_survive(tmp_path):
    files = deposit(
        tmp_path,
        {"1": {"local_sample_id": "01", "factors": "G:a"},
         "2": {"local_sample_id": "1", "factors": "G:b"}},
        {"1": {"analysis_id": "AN1", "metabolite_name": "x", "DATA": {"01": "1", "1": "2"}}},
        "phenotype_key: G\\n",
    )
    prepare(*files, tmp_path / "out")
    rows = (tmp_path / "out" / "prepared.csv").read_text().splitlines()
    assert [r.split(",")[0] for r in rows[2:]] == ["01", "1"]
"""


@pytest.mark.docker
def test_development_checks_in_the_real_sandbox(sandbox_image, tmp_path):
    from onboard.sandbox import DockerSandbox

    reference = (REPO / "reference" / "workbench_rest.py").read_text()
    result = development_checks(
        "v1",
        version(tmp_path, reference, REAL_TESTS),
        task_inputs(tmp_path),
        DockerSandbox(sandbox_image, 120),
        tmp_path / "w",
    )
    assert result["overall"] == "ok", json.dumps(result, indent=1)
    assert result["checks"]["tests"]["passed"] == 1
