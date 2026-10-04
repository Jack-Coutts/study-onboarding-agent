"""`onboard rerun`: re-run an accepted converter with no model call (spec section 16).

A match shows the saved converter is reproducible. It does not show that a new
generation would write the same code.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from onboard.config import ROOT
from onboard.fetch import raw_dir
from onboard.hashing import sha256_file
from onboard.manifest import CODE_FILES, hashes, read_manifest
from onboard.sandbox import DockerSandbox, Sandbox
from onboard.validate import CONVERTER_INPUTS

SANDBOX_SECONDS = 120


@dataclass(frozen=True)
class Step:
    name: str
    ok: bool
    detail: str


def _locate(name: str, directory: Path, study_id: str, task_path: str, root: Path) -> Path | None:
    candidates = [
        directory / "inputs" / name,
        directory / name,
        raw_dir(study_id, root) / name,
        # A relative task path is relative to the repository, not the working directory.
        (ROOT / task_path).parent / name,
    ]
    return next((path for path in candidates if path.is_file()), None)


def rerun(directory: Path, sandbox: Sandbox | None = None, root: Path = ROOT) -> list[Step]:
    """Check inputs, re-run the converter and its tests, and compare output hashes."""
    manifest = read_manifest(directory)
    if not manifest.get("accepted_version"):
        return [Step("accepted converter", False, "this run has no accepted converter")]
    study_id, task_path = manifest["task"]["study_id"], manifest["task"]["path"]
    seconds = manifest.get("limits", {}).get("sandbox_seconds", SANDBOX_SECONDS)
    sandbox = sandbox or DockerSandbox(manifest["sandbox"]["digest"], seconds)
    code_source = directory / "accepted" if (directory / "accepted").is_dir() else directory

    expected = {entry["path"]: entry["sha256"] for entry in manifest["inputs"]}
    expected["task.yaml"] = manifest["task"]["task_sha256"]
    located: dict[str, Path] = {}
    problems = []
    for name, digest in expected.items():
        path = _locate(name, directory, study_id, task_path, root)
        if path is None:
            problems.append(f"{name} not found")
        elif sha256_file(path) != digest:
            problems.append(f"{name} at {path} differs from the manifest")
        else:
            located[name] = path
    code_hashes = hashes(code_source, CODE_FILES)
    if code_hashes != manifest["code_sha256"]:
        problems.append("the accepted code differs from the manifest")
    steps = [Step("inputs and code match the manifest", not problems, "; ".join(problems) or "ok")]
    if problems:
        return steps

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        code, inputs, output = work / "code", work / "input", work / "output"
        code.mkdir()
        inputs.mkdir()
        for name in CODE_FILES:
            shutil.copyfile(code_source / name, code / name)
        for name in CONVERTER_INPUTS:
            shutil.copyfile(located[name], inputs / name)
        execution = sandbox.run_converter(code, inputs, output)
        steps.append(Step("converter runs", execution.ok, execution.stderr[-500:] or "ok"))
        tests = sandbox.run_tests(code)
        steps.append(Step("tests pass", tests.ok, (tests.stdout + tests.stderr)[-500:].strip()))
        got = hashes(output, tuple(manifest["outputs_sha256"]))
        same = got == manifest["outputs_sha256"]
        differing = sorted(
            k for k in manifest["outputs_sha256"] if got.get(k) != manifest["outputs_sha256"][k]
        )
        steps.append(Step("output hashes match", same, "ok" if same else f"differ: {differing}"))
    return steps
