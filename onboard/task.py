"""Resolve a task file to its frozen deposit, and freeze both into a run directory."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from onboard.config import ROOT
from onboard.fetch import load_sources, raw_dir, verify_frozen
from onboard.tools import data_digest, deposit_records, factors_digest

DEPOSIT_FILES = ("factors.json", "data.json", "summary.json")
DRAFT_MARK = "CHOOSE"
CONTROL_TYPES = ["QC", "PBQC", "pool", "blank"]


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
    unfinished = sorted(key for key, value in task.items() if value == DRAFT_MARK)
    if unfinished:
        raise TaskError(f"{task_path} is an unfinished draft: set {unfinished}, now {DRAFT_MARK}")
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


def _counts(values: dict[str, Any]) -> str:
    return ", ".join(f"{value} ({count})" for value, count in values.items())


def draft_task(study_id: str, root: Path = ROOT) -> Path:
    """Write tasks/draft-<ST>.yaml from a fetched study, leaving the outcome for a person.

    It fills in facts (analyses, which technical factors exist) and never guesses
    the outcome: runs refuse the file until every CHOOSE is replaced.
    """
    deposit = raw_dir(study_id, root)
    if not (deposit / "factors.json").exists():
        raise TaskError(f"{study_id} is not downloaded; run `onboard fetch {study_id}` first")
    target = root / "tasks" / f"draft-{study_id}.yaml"
    if target.exists():
        raise TaskError(f"{target} already exists; edit it or delete it first")

    def load(name: str) -> Any:
        return json.loads((deposit / name).read_text(encoding="utf-8"))

    factors = factors_digest(deposit_records(load("factors.json")))
    analyses = sorted(data_digest(deposit_records(load("data.json")))["analyses"])
    summary = load("summary.json")
    title = " ".join(str(summary.get("study_title", "")).split())[:100]
    keys: dict[str, dict[str, Any]] = factors["factor_keys"]
    width = max((len(key) for key in keys), default=0)

    def technical(name: str) -> dict[str, Any] | None:
        return next((v for k, v in keys.items() if k.casefold() == name.casefold()), None)

    sample_types = technical("Sample type")
    lines = [
        f"# DRAFT task for {study_id} ({factors['distinct_local_sample_ids']} samples): {title}",
        f"# Replace every {DRAFT_MARK}. Runs refuse this file until you do.",
        f"study_id: {study_id}",
        "",
        "# CHOOSE the outcome to compare. Factors in this study:",
        *(f"#   {key:<{width}}  {_counts(values)}" for key, values in keys.items()),
        f"phenotype_key: {DRAFT_MARK}",
        "",
        "# Optional: rename outcome labels, e.g. {Healthy control: control}",
        "# map: {}",
        "# Optional: keep only these outcome groups (default: all)",
        "# keep: []",
        "",
        f"# Analyses found: {', '.join(analyses)}. Order them by priority if there are several.",
        f"analyses: [{', '.join(analyses)}]",
        "",
        "# Sample types that mark QC, pooled QC, or blank samples.",
        f"#   Sample type: {_counts(sample_types)}"
        if sample_types
        else "# No sample-type factor in this study, so no QC or blank samples are recognised.",
        f"control_sample_types: [{', '.join(CONTROL_TYPES)}]",
    ]
    missing = [name for name in ("Batch", "Injection order") if technical(name) is None]
    if missing:
        lines += [
            "",
            f"# Heads-up: no {' or '.join(missing)} factor, so those columns will be blank.",
        ]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
