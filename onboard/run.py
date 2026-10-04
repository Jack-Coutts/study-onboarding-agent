"""One agent run, from frozen inputs to a finished run directory (spec section 15)."""

from __future__ import annotations

import json
import secrets
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from onboard.config import ROOT, Config
from onboard.injection import scan_run
from onboard.loop import AgentLoop, Outcome, RunLog
from onboard.manifest import (
    CODE_FILES,
    OUTPUT_FILES,
    hashes,
    new_manifest,
    now_iso,
    write_manifest,
)
from onboard.model_client import ModelClient
from onboard.sandbox import Execution, Sandbox
from onboard.task import TaskInputs, freeze_inputs
from onboard.tools import Tools
from onboard.validate import development_checks

PROMPTS = ROOT / "prompts"


class TimedSandbox:
    """Adds up the time spent in the sandbox, for the manifest."""

    def __init__(self, inner: Sandbox) -> None:
        self.inner = inner
        self.image = inner.image
        self.seconds = 0.0

    def run_converter(self, code_dir: Path, input_dir: Path, output_dir: Path) -> Execution:
        execution = self.inner.run_converter(code_dir, input_dir, output_dir)
        self.seconds += execution.seconds
        return execution

    def run_tests(self, code_dir: Path) -> Execution:
        execution = self.inner.run_tests(code_dir)
        self.seconds += execution.seconds
        return execution


@dataclass(frozen=True)
class RunResult:
    run_dir: Path
    outcome: Outcome
    manifest: dict[str, Any]


def render_task_prompt(study_id: str, frozen_task: Path) -> str:
    """The task prompt, from the frozen task: settings only, no comments."""
    template = (PROMPTS / "task.md").read_text(encoding="utf-8")
    return template.replace("{{STUDY_ID}}", study_id).replace(
        "{{TASK_YAML}}", frozen_task.read_text(encoding="utf-8").strip()
    )


def new_run_dir(root: Path) -> tuple[str, Path]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}_{secrets.token_hex(3)}"
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True)
    return run_id, run_dir


def run_task(
    task: TaskInputs,
    config: Config,
    client: ModelClient,
    sandbox: Sandbox,
    root: Path = ROOT,
    save_study: bool = True,
) -> RunResult:
    started = time.monotonic()
    run_id, run_dir = new_run_dir(root)
    inputs_dir = freeze_inputs(task, run_dir / "inputs")
    system_prompt = (PROMPTS / "system.md").read_text(encoding="utf-8")
    task_prompt = render_task_prompt(task.study_id, inputs_dir / "task.yaml")
    manifest = new_manifest(
        run_id, config, task, inputs_dir, system_prompt, task_prompt, sandbox.image
    )
    write_manifest(run_dir, manifest)
    timed = TimedSandbox(sandbox)

    def validator(version_id: str, version_dir: Path) -> dict[str, Any]:
        workdir = run_dir / "validation" / version_id
        return development_checks(version_id, version_dir, inputs_dir, timed, workdir)

    tools = Tools(run_dir, inputs_dir, config.limits.submissions, validator)

    def recheck(version_id: str) -> dict[str, Any]:
        workdir = run_dir / "validation" / f"{version_id}-recheck"
        return development_checks(
            version_id, tools.version_dir(version_id), inputs_dir, timed, workdir
        )

    loop = AgentLoop(
        config, client, tools, RunLog(run_dir / "log.jsonl"), system_prompt, task_prompt, recheck
    )
    try:
        outcome = loop.run()
    except BaseException as error:
        manifest.update(status="failed", status_reason=f"harness error: {error!r}")
        manifest["finished_at"] = now_iso()
        write_manifest(run_dir, manifest)
        raise

    if outcome.status == "passed" and outcome.accepted_version:
        accepted = run_dir / "accepted"
        accepted.mkdir()
        for name in CODE_FILES:
            shutil.copyfile(tools.version_dir(outcome.accepted_version) / name, accepted / name)
        output = run_dir / "output"
        recheck_output = run_dir / "validation" / f"{outcome.accepted_version}-recheck" / "task"
        shutil.copytree(recheck_output / "output", output)
        manifest["accepted_version"] = outcome.accepted_version
        manifest["code_sha256"] = hashes(accepted, CODE_FILES)
        manifest["outputs_sha256"] = hashes(output, OUTPUT_FILES)

    accounting = loop.accounting
    manifest.update(
        status=outcome.status,
        status_reason=outcome.reason,
        finish_claim=outcome.finish.__dict__ if outcome.finish else None,
        submissions=tools.submissions,
        injection=scan_run(run_dir),
    )
    manifest["model"]["served"] = accounting.served_models
    manifest["usage"] = {
        "requests": accounting.requests,
        "input_tokens": accounting.input_tokens,
        "output_tokens": accounting.output_tokens,
        "cache_creation_input_tokens": accounting.cache_creation_input_tokens,
        "cache_read_input_tokens": accounting.cache_read_input_tokens,
        "estimated_usd": round(accounting.estimated_usd, 4),
    }
    manifest["timing_seconds"] = {
        "total": round(time.monotonic() - started, 2),
        "model": round(accounting.model_seconds, 2),
        "sandbox": round(timed.seconds, 2),
    }
    manifest["finished_at"] = now_iso()
    write_manifest(run_dir, manifest)
    (run_dir / "report.md").write_text(render_report(manifest, tools), encoding="utf-8")
    if save_study and outcome.status == "passed":
        save_accepted_study(run_dir, manifest, root)
    return RunResult(run_dir, outcome, manifest)


def render_report(manifest: dict[str, Any], tools: Tools) -> str:
    usage, timing, model = manifest["usage"], manifest["timing_seconds"], manifest["model"]
    lines = [
        f"# Run {manifest['run_id']}",
        "",
        f"- Study: {manifest['task']['study_id']}",
        f"- Status: **{manifest['status']}**. {manifest['status_reason']}",
        f"- Model: {model['requested']} (served: {', '.join(model['served']) or 'none'}), "
        f"effort {model['effort']}",
        f"- Requests: {usage['requests']}; submissions: {manifest['submissions']}",
        f"- Tokens: {usage['input_tokens']} input, {usage['output_tokens']} output; "
        f"estimated ${usage['estimated_usd']:.2f}",
        f"- Time: {timing['total']} s total, {timing['model']} s model, "
        f"{timing['sandbox']} s sandbox",
        "",
        "## Versions",
        "",
    ]
    for directory in sorted(tools.versions_dir.glob("v*"), key=lambda p: int(p.name[1:])):
        validation_file = directory / "validation.json"
        if validation_file.exists():
            validation = json.loads(validation_file.read_text())
            failing = [n for n, c in validation["checks"].items() if c["status"] != "ok"]
            state = validation["overall"] + (f" (failing: {', '.join(failing)})" if failing else "")
        else:
            state = "not validated"
        lines.append(f"- {directory.name}: {state}")
    injection = manifest["injection"]
    lines += ["", "## Deposit free text", "", f"- Instruction-like text: {injection['outcome']}"]
    lines += [f"- Blocked by the sandbox: {b}" for b in injection.get("blocked", [])]
    lines += [f"- Evidence: {e}" for e in injection.get("evidence", [])]
    return "\n".join(lines) + "\n"


def save_accepted_study(run_dir: Path, manifest: dict[str, Any], root: Path = ROOT) -> Path:
    """Copy an accepted converter to studies/<ST>/ with notes on how to re-run it."""
    study_id: str = manifest["task"]["study_id"]
    target = root / "studies" / study_id
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in CODE_FILES:
        shutil.copyfile(run_dir / "accepted" / name, target / name)
    shutil.copyfile(run_dir / "inputs" / "task.yaml", target / "task.yaml")
    shutil.copyfile(run_dir / "manifest.json", target / "manifest.json")
    (target / "PROCESSING.md").write_text(
        f"# {study_id}\n\n"
        f"Converter accepted in run `{manifest['run_id']}` "
        f"({manifest['status_reason']}).\n\n"
        f"- Task: `task.yaml` (SHA-256 {manifest['task']['task_sha256']})\n"
        f"- Model: {', '.join(manifest['model']['served'])}, effort {manifest['model']['effort']}\n"
        f"- Sandbox image: {manifest['sandbox']['digest']}\n"
        f"- Harness commit: {manifest['harness_git_commit']}\n\n"
        "## Re-run without a model\n\n"
        f"Fetch the deposit with `onboard fetch {study_id}` if `data/raw/{study_id}/` is "
        f"missing, then run `onboard rerun studies/{study_id}`. It checks the input hashes, "
        "runs this converter and its tests in the recorded sandbox image, and compares the "
        "output hashes with `manifest.json`.\n",
        encoding="utf-8",
    )
    return target
