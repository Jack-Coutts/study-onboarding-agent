"""Run manifests (spec section 15): what went in, what ran, and what came out."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from onboard.config import ROOT, Config
from onboard.hashing import sha256_bytes, sha256_file, sha256_json
from onboard.task import DEPOSIT_FILES, TaskInputs
from onboard.tools import TOOL_DEFINITIONS

CODE_FILES = ("prepare.py", "test_prepare.py")
OUTPUT_FILES = ("prepared.csv", "summary.json", "config.yaml")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def git_commit(root: Path = ROOT) -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{commit}-dirty" if dirty else commit


def input_records(task: TaskInputs, inputs_dir: Path) -> list[dict[str, Any]]:
    records = []
    for name in DEPOSIT_FILES:
        source = task.sources.get(name, {})
        records.append(
            {
                "path": name,
                "sha256": sha256_file(inputs_dir / name),
                "url": source.get("url"),
                "retrieved_at": source.get("retrieved_at"),
            }
        )
    return records


def hashes(directory: Path, names: tuple[str, ...]) -> dict[str, str]:
    return {name: sha256_file(directory / name) for name in names if (directory / name).exists()}


def new_manifest(
    run_id: str,
    config: Config,
    task: TaskInputs,
    inputs_dir: Path,
    system_prompt: str,
    task_prompt: str,
    sandbox_digest: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "running",
        "status_reason": "",
        "task": {
            "study_id": task.study_id,
            "task_sha256": sha256_file(inputs_dir / "task.yaml"),
            "path": str(task.task_path),
        },
        "inputs": input_records(task, inputs_dir),
        "config_sha256": sha256_file(config.path),
        "prompt_sha256": sha256_bytes((system_prompt + "\n\n" + task_prompt).encode()),
        "tools_sha256": sha256_json(TOOL_DEFINITIONS),
        "model": {
            "provider": provider.name
            if (provider := config.provider(config.model))
            else "anthropic",
            "base_url": provider.base_url if provider else None,
            "requested": config.model,
            "served": [],
            "effort": config.effort,
            "max_tokens": config.max_tokens,
        },
        "limits": dict(config.limits.__dict__),
        "sandbox": {"image": config.sandbox.image, "digest": sandbox_digest, "network": "none"},
        "accepted_version": None,
        "code_sha256": {},
        "outputs_sha256": {},
        "usage": {"requests": 0, "input_tokens": 0, "output_tokens": 0, "estimated_usd": 0.0},
        "timing_seconds": {"total": 0.0, "model": 0.0, "sandbox": 0.0},
        "harness_git_commit": git_commit(),
        "started_at": now_iso(),
        "finished_at": None,
    }


def write_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def read_manifest(directory: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads((directory / "manifest.json").read_text())
    return manifest
