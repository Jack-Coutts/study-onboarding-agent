"""`onboard eval`: runs on the frozen tasks, then the hidden checks (spec sections 12.2, 17).

Nothing here is returned to the model. Hidden checks run only after a run has
ended: the accepted converter against the reference converter's output on the
same deposit, against held-out fixtures H1-H5, and the agent's tests against
every broken variant.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from onboard.compare import cell_agreement, compare_outputs
from onboard.config import ROOT, Config
from onboard.fixtures import list_fixtures
from onboard.manifest import read_manifest
from onboard.rerun import rerun
from onboard.run import run_task
from onboard.sandbox import Sandbox
from onboard.task import resolve_task
from onboard.validate import run_fixture, stage_inputs
from reference.broken import IDS, build_variant

REFERENCE = ROOT / "reference" / "workbench_rest.py"


def _code_dir(target: Path, prepare_source: str, test_source: str | None = None) -> Path:
    target.mkdir(parents=True)
    (target / "prepare.py").write_text(prepare_source, encoding="utf-8")
    if test_source is not None:
        (target / "test_prepare.py").write_text(test_source, encoding="utf-8")
    return target


def hidden_checks(run_dir: Path, sandbox: Sandbox, root: Path = ROOT) -> dict[str, Any]:
    manifest = read_manifest(run_dir)
    result: dict[str, Any] = {
        "run_id": manifest["run_id"],
        "study_id": manifest["task"]["study_id"],
        "status": manifest["status"],
        "status_reason": manifest["status_reason"],
        "requests": manifest["usage"]["requests"],
        "submissions": manifest.get("submissions"),
        "input_tokens": manifest["usage"]["input_tokens"],
        "output_tokens": manifest["usage"]["output_tokens"],
        "estimated_usd": manifest["usage"]["estimated_usd"],
        "wall_seconds": manifest["timing_seconds"]["total"],
        "injection": manifest.get("injection", {}),
    }
    if manifest["status"] != "passed":
        return result
    accepted = run_dir / "accepted"
    prepare_source = (accepted / "prepare.py").read_text(encoding="utf-8")
    test_source = (accepted / "test_prepare.py").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        reference_code = _code_dir(work / "reference", REFERENCE.read_text(encoding="utf-8"))
        inputs = stage_inputs(run_dir / "inputs", work / "inputs")
        reference_execution = sandbox.run_converter(reference_code, inputs, work / "reference-out")
        if reference_execution.ok:
            diffs = compare_outputs(run_dir / "output", work / "reference-out")
            matching, total = cell_agreement(
                run_dir / "output" / "prepared.csv", work / "reference-out" / "prepared.csv"
            )
            result["reference"] = {
                "matches": not diffs,
                "cells_matching": matching,
                "cells_total": total,
                "diff": diffs,
            }
        else:
            result["reference"] = {
                "matches": None,
                "error": f"the reference converter failed: {reference_execution.stderr[-500:]}",
            }

        agent_code = _code_dir(work / "agent", prepare_source)
        heldout = {}
        for fixture in list_fixtures("heldout", root / "fixtures"):
            check, _ = run_fixture(sandbox, agent_code, fixture, work / "heldout")
            heldout[fixture.id] = check.as_dict()
        result["heldout"] = heldout
        result["heldout_correct"] = sum(r["status"] == "ok" for r in heldout.values())

        variants = {}
        for variant in IDS:
            code = _code_dir(work / "variants" / variant, build_variant(variant), test_source)
            execution = sandbox.run_tests(code)
            variants[variant] = {"caught": not execution.ok, "exit_code": execution.exit_code}
        result["variants"] = variants
        result["variants_caught"] = sum(v["caught"] for v in variants.values())

    steps = rerun(run_dir, sandbox, root)
    result["rerun_matches"] = all(step.ok for step in steps)
    result["rerun"] = [step.__dict__ for step in steps]
    return result


def _cell(result: dict[str, Any]) -> str:
    reference = result.get("reference")
    if not reference:
        return "n/a"
    if reference.get("matches") is None:
        return "reference failed"
    if reference["matches"]:
        return "yes"
    return f"no ({reference['cells_matching']}/{reference['cells_total']} cells)"


def _out_of(result: dict[str, Any], key: str, total: int) -> str:
    return f"{result[key]}/{total}" if key in result else "n/a"


def _row(r: dict[str, Any]) -> list[str]:
    injection = r.get("injection") or {}
    blocked = " (blocked)" if injection.get("blocked") else ""
    rerun_cell = "n/a"
    if "rerun_matches" in r:
        rerun_cell = "yes" if r["rerun_matches"] else "no"
    return [
        r["run_id"],
        r["study_id"],
        r["status"],
        _cell(r),
        _out_of(r, "heldout_correct", 5),
        _out_of(r, "variants_caught", 8),
        f"{injection.get('outcome', 'n/a')}{blocked}",
        str(r["requests"]),
        str(r["submissions"]),
        f"{r['input_tokens']}/{r['output_tokens']}",
        f"{r['estimated_usd']:.2f}",
        str(r["wall_seconds"]),
        rerun_cell,
    ]


def _summary_row(results: list[dict[str, Any]]) -> list[str]:
    passed = [r for r in results if r["status"] == "passed"]
    n = len(passed)
    matches = sum(1 for r in passed if (r.get("reference") or {}).get("matches"))
    return [
        "**Summary**",
        f"{len(results)} runs",
        f"{n} passed",
        f"{matches}/{n} match",
        f"{sum(r.get('heldout_correct', 0) for r in passed)}/{5 * n}",
        f"{sum(r.get('variants_caught', 0) for r in passed)}/{8 * n}",
        "",
        str(sum(r["requests"] for r in results)),
        "",
        "",
        f"{sum(r['estimated_usd'] for r in results):.2f}",
        "",
        f"{sum(1 for r in passed if r.get('rerun_matches'))}/{n}",
    ]


COLUMNS = [
    "Run",
    "Study",
    "Status",
    "Matches reference",
    "Held-out correct",
    "Variants caught",
    "Injection",
    "Requests",
    "Submissions",
    "Tokens in/out",
    "Est. USD",
    "Wall s",
    "Re-run matches",
]


def render_results(results: list[dict[str, Any]], notes: list[str]) -> str:
    lines = [
        "# Evaluation results",
        "",
        "Generated by `onboard eval`. Failures are reported, not hidden. A disagreement with "
        "the reference converter is investigated both ways: the reference can be wrong too.",
        "",
        *[f"- {note}" for note in notes],
        "",
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "---|" * len(COLUMNS),
    ]
    for row in [*(_row(r) for r in results), _summary_row(results)]:
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "## Disagreements", ""]
    any_disagreement = False
    for r in results:
        if r["status"] != "passed":
            lines.append(f"- {r['run_id']}: ended `{r['status']}`: {r['status_reason']}")
            any_disagreement = True
            continue
        for line in (r.get("reference") or {}).get("diff", []):
            lines.append(f"- {r['run_id']} vs reference: {line}")
            any_disagreement = True
        for fixture, check in (r.get("heldout") or {}).items():
            for line in check.get("diff", []) or (["failed"] if check["status"] != "ok" else []):
                lines.append(f"- {r['run_id']} on {fixture}: {line}")
                any_disagreement = True
        missed = [v for v, c in (r.get("variants") or {}).items() if not c["caught"]]
        if missed:
            lines.append(f"- {r['run_id']}: tests did not catch {', '.join(missed)}")
            any_disagreement = True
    if not any_disagreement:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def write_results(results: list[dict[str, Any]], notes: list[str], root: Path = ROOT) -> Path:
    directory = root / "eval"
    directory.mkdir(exist_ok=True)
    (directory / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    path = directory / "results.md"
    path.write_text(render_results(results, notes), encoding="utf-8")
    return path


def evaluate(
    task_paths: list[Path],
    config: Config,
    client_factory: Callable[[], Any],
    sandbox: Sandbox,
    root: Path = ROOT,
) -> Path:
    """Section 17.2: run each task, then the hidden checks on every passed run."""
    results = []
    for task_path in task_paths:
        task = resolve_task(task_path, root)
        for _ in range(config.runs_per_task):
            run = run_task(task, config, client_factory(), sandbox, root=root)
            results.append(hidden_checks(run.run_dir, sandbox, root))
    notes = [
        f"Tasks: {', '.join(p.stem for p in task_paths)}; {config.runs_per_task} runs each.",
        f"Model {config.model}, effort {config.effort}.",
    ]
    return write_results(results, notes, root)
