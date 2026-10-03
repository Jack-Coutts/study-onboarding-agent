"""Run generated code in a fresh, locked-down container (spec section 11).

Generated code runs only through this module. Each execution starts a new
container with no network, a read-only root, all capabilities dropped, no
environment variables passed in, and only the directories it needs mounted.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import time
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from onboard.config import ROOT, Config

CHECK_RECORD = ROOT / "runs" / "sandbox-check.json"
STDERR_TAIL = 2000
OUTPUT_FILE_LIMIT = 50 * 1024 * 1024


class SandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class Execution:
    exit_code: int | None
    stdout: str
    stderr: str
    seconds: float
    timed_out: bool

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def summary(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "seconds": round(self.seconds, 2),
            "stderr_tail": self.stderr[-STDERR_TAIL:],
        }


class Sandbox(Protocol):
    """What the validator needs. Tests substitute a fake that executes nothing."""

    image: str

    def run_converter(self, code_dir: Path, input_dir: Path, output_dir: Path) -> Execution: ...

    def run_tests(self, code_dir: Path) -> Execution: ...


@dataclass(frozen=True)
class Mount:
    host: Path
    container: str
    read_only: bool

    def flag(self) -> list[str]:
        suffix = ":ro" if self.read_only else ""
        return ["-v", f"{self.host.resolve()}:{self.container}{suffix}"]


CONVERTER_ARGS = [
    "python",
    "/code/prepare.py",
    "--factors",
    "/input/factors.json",
    "--data",
    "/input/data.json",
    "--task",
    "/input/task.yaml",
    "--output",
    "/output",
]
TEST_ARGS = ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "/code/test_prepare.py"]


class DockerSandbox:
    def __init__(self, image: str, timeout_seconds: float, docker: str = "docker") -> None:
        self.image = image
        self.timeout_seconds = timeout_seconds
        self.docker = docker

    def command(self, name: str, mounts: list[Mount], argv: list[str]) -> list[str]:
        command = [
            self.docker,
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:size=64m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "runner",
            "--memory",
            "1g",
            "--cpus",
            "1",
            "--pids-limit",
            "128",
        ]
        for mount in mounts:
            command += mount.flag()
        return [*command, self.image, *argv]

    def execute(
        self, mounts: list[Mount], argv: list[str], host_env: dict[str, str] | None = None
    ) -> Execution:
        """Run argv in a new container. host_env is the docker CLI's own environment;
        nothing from it is passed into the container."""
        name = f"onboard-{uuid.uuid4().hex[:12]}"
        command = self.command(name, mounts, argv)
        started = time.monotonic()
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                env=host_env,
            )
        except subprocess.TimeoutExpired as expired:
            subprocess.run(
                [self.docker, "kill", name], capture_output=True, timeout=30, check=False
            )
            return Execution(
                exit_code=None,
                stdout=_text(expired.stdout),
                stderr=_text(expired.stderr) + f"\nstopped after {self.timeout_seconds:g} seconds",
                seconds=time.monotonic() - started,
                timed_out=True,
            )
        return Execution(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            seconds=time.monotonic() - started,
            timed_out=False,
        )

    def run_converter(self, code_dir: Path, input_dir: Path, output_dir: Path) -> Execution:
        """Run prepare.py; output_dir receives only the regular files it wrote.

        The container writes to a separate raw directory. The host never reads it
        directly: generated code could leave symlinks there pointing at held-out
        expectations or the harness's own environment.
        """
        raw = output_dir.with_name(output_dir.name + ".raw")
        if raw.exists():
            shutil.rmtree(raw)
        raw.mkdir(parents=True)
        raw.chmod(0o777)  # the container user is not the host user
        mounts = [
            Mount(code_dir, "/code", read_only=True),
            Mount(input_dir, "/input", read_only=True),
            Mount(raw, "/output", read_only=False),
        ]
        execution = self.execute(mounts, CONVERTER_ARGS)
        self._release(raw)
        problems = collect_outputs(raw, output_dir)
        if problems:
            notes = "".join(f"\nharness: {problem}" for problem in problems)
            execution = replace(execution, stderr=execution.stderr + notes)
        return execution

    def _release(self, raw: Path) -> None:
        """Let the host delete what the container wrote in subdirectories."""
        if any(entry.is_dir(follow_symlinks=False) for entry in os.scandir(raw)):
            self.execute(
                [Mount(raw, "/output", read_only=False)], ["chmod", "-R", "a+rwX", "/output"]
            )

    def run_tests(self, code_dir: Path) -> Execution:
        return self.execute([Mount(code_dir, "/code", read_only=True)], TEST_ARGS)


def collect_outputs(raw: Path, target: Path) -> list[str]:
    """Copy regular top-level files from raw to target without following links."""
    target.mkdir(parents=True, exist_ok=True)
    problems = []
    for entry in sorted(os.scandir(raw), key=lambda e: e.name):
        info = entry.stat(follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            problems.append(f"ignored {entry.name}/: outputs must be files, not a directory")
            continue
        if not stat.S_ISREG(info.st_mode):
            problems.append(f"ignored {entry.name}: not a regular file")
            continue
        if info.st_size > OUTPUT_FILE_LIMIT:
            problems.append(f"ignored {entry.name}: larger than {OUTPUT_FILE_LIMIT} bytes")
            continue
        descriptor = os.open(entry.path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as source, (target / entry.name).open("wb") as sink:
            shutil.copyfileobj(source, sink)
    return problems


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def docker_sandbox(config: Config) -> DockerSandbox:
    if "REPLACE" in config.sandbox.digest:
        raise SandboxError(
            "config.yaml sandbox.digest is not set; run `onboard check-sandbox --build`"
        )
    return DockerSandbox(config.sandbox.reference, config.limits.sandbox_seconds)


def build_image(tag: str, docker: str = "docker") -> str:
    """Build sandbox/Dockerfile and return the image ID."""
    subprocess.run([docker, "build", "-t", tag, str(ROOT / "sandbox")], check=True)
    result = subprocess.run(
        [docker, "image", "inspect", "--format", "{{.Id}}", tag],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def evaluate_probe(output: str) -> tuple[bool, list[str]]:
    """Whether the probe saw every expected failure and both controls succeed."""
    try:
        report = json.loads(output.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return False, [f"probe printed no JSON report: {output[-500:]!r}"]
    problems = [
        f"{name} was not blocked: {result['detail']}"
        for name, result in report["blocked"].items()
        if not result["blocked"]
    ]
    problems += [
        f"control {name} failed: {result['detail']}"
        for name, result in report["controls"].items()
        if not result["ok"]
    ]
    return not problems, problems


def run_probe(sandbox: DockerSandbox, workdir: Path) -> tuple[bool, list[str], Execution]:
    code, inputs, output = workdir / "code", workdir / "input", workdir / "output"
    for directory in (code, inputs, output):
        directory.mkdir(parents=True, exist_ok=True)
    output.chmod(0o777)
    (code / "probe.py").write_text((ROOT / "sandbox" / "probe.py").read_text())
    mounts = [
        Mount(code, "/code", read_only=True),
        Mount(inputs, "/input", read_only=True),
        Mount(output, "/output", read_only=False),
    ]
    # A canary key in the docker CLI's environment: the probe must not see it.
    host_env = dict(os.environ, ONBOARD_CANARY_API_KEY="sk-ant-canary-" + uuid.uuid4().hex)
    execution = sandbox.execute(mounts, ["python", "/code/probe.py"], host_env=host_env)
    if not execution.ok:
        return False, [f"probe did not run: {execution.summary()}"], execution
    passed, problems = evaluate_probe(execution.stdout)
    return passed, problems, execution


def record_check(digest: str, passed: bool, problems: list[str], path: Path = CHECK_RECORD) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "digest": digest,
        "passed": passed,
        "problems": problems,
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(record, indent=2) + "\n")


def require_check(digest: str, path: Path = CHECK_RECORD) -> None:
    """Refuse to run unless the isolation check passed for this exact image."""
    if not path.exists():
        raise SandboxError("the sandbox has not been checked; run `onboard check-sandbox`")
    record = json.loads(path.read_text())
    if record.get("digest") != digest:
        raise SandboxError("the sandbox image changed since it was checked; run it again")
    if not record.get("passed"):
        raise SandboxError(f"the last sandbox check failed: {record.get('problems')}")


def set_config_digest(config_path: Path, digest: str) -> None:
    """Write a newly built image ID into config.yaml's sandbox.digest line."""
    lines = config_path.read_text().splitlines(keepends=True)
    replaced = 0
    for i, line in enumerate(lines):
        if line.lstrip().startswith("digest:"):
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f"{indent}digest: {digest}\n"
            replaced += 1
    if replaced != 1:
        raise SandboxError(f"expected one digest line in {config_path}, found {replaced}")
    config_path.write_text("".join(lines))


def check_sandbox(config: Config, build: bool, workdir: Path) -> tuple[bool, list[str], str]:
    """`onboard check-sandbox`: optionally rebuild, run the probe, and record the result."""
    digest = config.sandbox.digest
    if build:
        digest = build_image(config.sandbox.image)
        if digest != config.sandbox.digest:
            set_config_digest(config.path, digest)
    if "REPLACE" in digest:
        raise SandboxError("config.yaml sandbox.digest is not set; run with --build")
    passed, problems, _ = run_probe(DockerSandbox(digest, config.limits.sandbox_seconds), workdir)
    record_check(digest, passed, problems)
    return passed, problems, digest
