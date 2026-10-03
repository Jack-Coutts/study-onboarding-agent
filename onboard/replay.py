"""`onboard replay`: re-drive the harness from a run's log with no API calls.

The recorded model responses are played back in order; tool calls run again,
including the sandbox. A replay is a new run directory, and is never saved to
studies/.
"""

from __future__ import annotations

import json
from pathlib import Path

from onboard.config import ROOT, Config
from onboard.manifest import read_manifest
from onboard.model_client import ModelResponse, ScriptedClient
from onboard.run import RunResult, run_task
from onboard.sandbox import Sandbox
from onboard.task import TaskInputs


def recorded_responses(run_dir: Path) -> list[ModelResponse]:
    responses = []
    for line in (run_dir / "log.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["event"] == "response":
            responses.append(ModelResponse.from_json(record["response"]))
    return responses


def replay(run_dir: Path, config: Config, sandbox: Sandbox, root: Path = ROOT) -> RunResult:
    manifest = read_manifest(run_dir)
    inputs = run_dir / "inputs"
    task = TaskInputs(
        task_path=inputs / "task.yaml",
        study_id=manifest["task"]["study_id"],
        deposit_dir=inputs,
        sources={entry["path"]: entry for entry in manifest["inputs"]},
    )
    original = config.with_overrides(
        model=manifest["model"]["requested"], effort=manifest["model"]["effort"]
    )
    client = ScriptedClient(recorded_responses(run_dir))
    return run_task(task, original, client, sandbox, root=root, save_study=False)
