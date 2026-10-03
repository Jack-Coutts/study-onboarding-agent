"""Development checks for one submitted version (spec section 12.1).

The result is returned to the model, so it may include only the task's own
deposit, the dev fixtures, and the version's own tests. Held-out fixtures, the
reference converter's output, and broken-variant results live in evaluate.py.
"""

from __future__ import annotations

import ast
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contract.input_contract import check_contract
from onboard.compare import compare_result
from onboard.fixtures import Fixture, list_fixtures
from onboard.sandbox import Execution, Sandbox

THIRD_PARTY = frozenset({"pandas", "numpy", "yaml"})
TEST_ONLY = frozenset({"pytest", "prepare"})
CONVERTER_INPUTS = ("factors.json", "data.json", "task.yaml")
OUTPUT_TAIL = 2000
PREPARE_PARAMS = 4


@dataclass(frozen=True)
class Check:
    ok: bool
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"status": "ok" if self.ok else "fail", **self.details}


def _imports(tree: ast.Module) -> list[tuple[str, int]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(alias.name.split(".")[0], node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.append(("." * node.level + (node.module or ""), node.lineno))
            elif node.module:
                found.append((node.module.split(".")[0], node.lineno))
    return found


def static_check(version_dir: Path) -> Check:
    """Both files parse, imports are allowed, and prepare() exists with four parameters."""
    problems: list[str] = []
    trees: dict[str, ast.Module] = {}
    for name in ("prepare.py", "test_prepare.py"):
        try:
            trees[name] = ast.parse((version_dir / name).read_text(encoding="utf-8"), name)
        except SyntaxError as error:
            problems.append(f"{name} line {error.lineno}: {error.msg}")
        except FileNotFoundError:
            problems.append(f"{name} is missing")
    for name, tree in trees.items():
        allowed = THIRD_PARTY | (TEST_ONLY if name == "test_prepare.py" else frozenset())
        for module, line in _imports(tree):
            if module not in sys.stdlib_module_names and module not in allowed:
                problems.append(
                    f"{name} line {line}: import of {module!r} is not allowed "
                    "(standard library, pandas, numpy, and pyyaml only)"
                )
    if "prepare.py" in trees:
        functions = {
            node.name: node
            for node in trees["prepare.py"].body
            if isinstance(node, ast.FunctionDef)
        }
        prepare = functions.get("prepare")
        if prepare is None:
            problems.append("prepare.py does not define a top-level function prepare")
        elif len(prepare.args.args) != PREPARE_PARAMS:
            problems.append(
                "prepare() must take (factors_json, data_json, task_yaml, output_dir), "
                f"got {len(prepare.args.args)} positional parameters"
            )
    if "test_prepare.py" in trees and not any(
        isinstance(node, ast.ImportFrom)
        and node.module == "prepare"
        and any(alias.name == "prepare" for alias in node.names)
        for node in ast.walk(trees["test_prepare.py"])
    ):
        problems.append("test_prepare.py must import prepare with `from prepare import prepare`")
    return Check(not problems, {"problems": problems})


def stage_inputs(source: Path, target: Path) -> Path:
    """Copy only the converter's inputs, so nothing else in the source is mounted."""
    target.mkdir(parents=True, exist_ok=True)
    for name in CONVERTER_INPUTS:
        shutil.copyfile(source / name, target / name)
    return target


def _clean(directory: Path) -> Path:
    if directory.exists():
        shutil.rmtree(directory)
    return directory


def execution_check(execution: Execution) -> Check:
    return Check(execution.ok, execution.summary())


def run_fixture(
    sandbox: Sandbox, version_dir: Path, fixture: Fixture, workdir: Path
) -> tuple[Check, Execution]:
    """Run a version on one fixture and compare with its expected outputs.

    Only the fixture's inputs are mounted; its expected/ directory never is.
    """
    inputs = stage_inputs(fixture.directory, _clean(workdir / fixture.id / "input"))
    output = _clean(workdir / fixture.id / "output")
    execution = sandbox.run_converter(version_dir, inputs, output)
    if execution.timed_out:
        return Check(False, {"execution": execution.summary(), "diff": []}), execution
    exit_code = execution.exit_code if execution.exit_code is not None else -1
    try:
        diffs = compare_result(exit_code, execution.stderr, output, fixture.expected)
    except Exception as error:  # a malformed output must fail the check, not the run
        diffs = [f"the output could not be compared: {type(error).__name__}: {error}"]
    details: dict[str, Any] = {"diff": diffs}
    if diffs:
        details["execution"] = execution.summary()
    return Check(not diffs, details), execution


_COUNT = re.compile(r"(\d+) (passed|failed|errors?)")


def tests_check(execution: Execution) -> Check:
    counts = {"passed": 0, "failed": 0, "errors": 0}
    for number, word in _COUNT.findall(execution.stdout):
        counts["errors" if word.startswith("error") else word] = int(number)
    details: dict[str, Any] = {**counts, "exit_code": execution.exit_code}
    if execution.timed_out:
        details["timed_out"] = True
    if not execution.ok:
        output = execution.stdout + execution.stderr
        start = output.find("___")
        details["first_failure"] = (output[start:] if start >= 0 else output)[:OUTPUT_TAIL]
    return Check(execution.ok, details)


def development_checks(
    version_id: str,
    version_dir: Path,
    inputs_dir: Path,
    sandbox: Sandbox,
    workdir: Path,
    fixtures: list[Fixture] | None = None,
) -> dict[str, Any]:
    """Run every development check and return one JSON-ready result."""
    fixtures = list_fixtures("dev") if fixtures is None else fixtures
    if any(f.split != "dev" for f in fixtures):
        raise ValueError("development checks may only use dev fixtures")
    checks: dict[str, Any] = {}
    timed_out = False

    static = static_check(version_dir)
    checks["static"] = static.as_dict()

    task_inputs = stage_inputs(inputs_dir, _clean(workdir / "task" / "input"))
    task_output = _clean(workdir / "task" / "output")
    execution = sandbox.run_converter(version_dir, task_inputs, task_output)
    timed_out |= execution.timed_out
    checks["execution"] = execution_check(execution).as_dict()

    if execution.ok:
        try:
            violations = [
                str(v)
                for v in check_contract(
                    task_output,
                    task_inputs / "factors.json",
                    task_inputs / "data.json",
                    task_inputs / "task.yaml",
                )
            ]
        except Exception as error:  # a malformed output must fail the check, not the run
            violations = [f"the contract could not be checked: {type(error).__name__}: {error}"]
        checks["contract"] = Check(not violations, {"violations": violations})
    else:
        checks["contract"] = Check(False, {"violations": ["not checked: the converter failed"]})
    checks["contract"] = checks["contract"].as_dict()

    fixture_results = {}
    for fixture in fixtures:
        result, fixture_execution = run_fixture(sandbox, version_dir, fixture, workdir / "fixtures")
        timed_out |= fixture_execution.timed_out
        fixture_results[fixture.id] = result.as_dict()
    checks["dev_fixtures"] = {
        "status": "ok" if all(r["status"] == "ok" for r in fixture_results.values()) else "fail",
        "fixtures": fixture_results,
    }

    test_execution = sandbox.run_tests(version_dir)
    timed_out |= test_execution.timed_out
    checks["tests"] = tests_check(test_execution).as_dict()

    overall = all(check["status"] == "ok" for check in checks.values())
    return {
        "version_id": version_id,
        "overall": "ok" if overall else "fail",
        "sandbox_timed_out": timed_out,
        "checks": checks,
    }
