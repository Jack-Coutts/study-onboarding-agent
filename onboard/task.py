"""Resolve a task file to its frozen deposit, and freeze both into a run directory."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from onboard.config import ROOT
from onboard.fetch import load_sources, raw_dir, verify_frozen

DEPOSIT_FILES = ("factors.json", "data.json", "summary.json")


class TaskError(ValueError):
    pass


@dataclass(frozen=True)
class TaskInputs:
    task_path: Path
    study_id: str
    deposit_dir: Path
    sources: dict[str, dict[str, Any]]

    @property
    def task_yaml(self) -> str:
        return self.task_path.read_text(encoding="utf-8")


def resolve_task(task_path: Path, root: Path = ROOT) -> TaskInputs:
    """A task next to its own deposit files (a fixture) or a fetched study in data/raw/."""
    task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    if not isinstance(task, dict) or not task.get("study_id"):
        raise TaskError(f"{task_path} must set study_id")
    study_id = str(task["study_id"])
    if all((task_path.parent / name).exists() for name in DEPOSIT_FILES):
        return TaskInputs(task_path, study_id, task_path.parent, {})
    problems = verify_frozen(study_id, root)
    if problems:
        raise TaskError("; ".join(problems))
    record = load_sources(root)["studies"][study_id]
    sources = {entry["path"]: entry for entry in record["files"]}
    return TaskInputs(task_path, study_id, raw_dir(study_id, root), sources)


def freeze_inputs(task: TaskInputs, target: Path) -> Path:
    """Copy the deposit and task into the run, read-only. Tools and the sandbox use this copy."""
    target.mkdir(parents=True)
    for name in DEPOSIT_FILES:
        shutil.copyfile(task.deposit_dir / name, target / name)
    shutil.copyfile(task.task_path, target / "task.yaml")
    for path in target.iterdir():
        path.chmod(0o444)
    return target
