"""Sandbox command shape, the isolation probe, and real execution (Docker-marked)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from onboard.compare import compare_result
from onboard.fixtures import list_fixtures
from onboard.sandbox import (
    DockerSandbox,
    Mount,
    SandboxError,
    evaluate_probe,
    record_check,
    require_check,
    run_probe,
    set_config_digest,
)

REFERENCE = Path(__file__).resolve().parents[1] / "reference" / "workbench_rest.py"


def test_converter_command_locks_the_container_down(tmp_path):
    sandbox = DockerSandbox("sha256:abc", 120)
    mounts = [
        Mount(tmp_path / "code", "/code", read_only=True),
        Mount(tmp_path / "in", "/input", read_only=True),
        Mount(tmp_path / "out", "/output", read_only=False),
    ]
    command = sandbox.command("onboard-x", mounts, ["python", "/code/prepare.py"])
    text = " ".join(command)

    for flag in (
        "--rm",
        "--network none",
        "--read-only",
        "--tmpfs /tmp:size=64m",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        "--user runner",
        "--memory 1g",
        "--cpus 1",
        "--pids-limit 128",
    ):
        assert flag in text
    assert f"{(tmp_path / 'code').resolve()}:/code:ro" in command
    assert f"{(tmp_path / 'in').resolve()}:/input:ro" in command
    assert f"{(tmp_path / 'out').resolve()}:/output" in command
    assert not {"-e", "--env", "--env-file", "--privileged"} & set(command)
    assert "docker.sock" not in text
    assert command[-3:] == ["sha256:abc", "python", "/code/prepare.py"]


def _report(**overrides):
    blocked = {name: {"blocked": True, "detail": ""} for name in ("network", "api_key")}
    controls = {"write_output": {"ok": True, "detail": ""}}
    for name, value in overrides.items():
        blocked[name] = {"blocked": value, "detail": "it worked"}
    return json.dumps({"blocked": blocked, "controls": controls})


def test_probe_report_passes_only_when_everything_is_blocked():
    assert evaluate_probe(_report()) == (True, [])
    passed, problems = evaluate_probe(_report(network=False))
    assert not passed
    assert problems == ["network was not blocked: it worked"]
    assert not evaluate_probe("Traceback ...")[0]


def test_runs_require_a_passing_check_for_the_same_image(tmp_path):
    record = tmp_path / "check.json"
    with pytest.raises(SandboxError, match="not been checked"):
        require_check("sha256:a", record)
    record_check("sha256:a", True, [], record)
    require_check("sha256:a", record)
    with pytest.raises(SandboxError, match="changed"):
        require_check("sha256:b", record)
    record_check("sha256:a", False, ["network was not blocked"], record)
    with pytest.raises(SandboxError, match="failed"):
        require_check("sha256:a", record)


def test_set_config_digest_rewrites_only_the_digest(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("model: m\nsandbox:\n  image: x\n  digest: sha256:REPLACE\n")
    set_config_digest(config, "sha256:new")
    assert config.read_text() == "model: m\nsandbox:\n  image: x\n  digest: sha256:new\n"


@pytest.mark.docker
def test_probe_observes_every_expected_failure(sandbox_image, tmp_path):
    passed, problems, _ = run_probe(DockerSandbox(sandbox_image, 120), tmp_path)
    assert (passed, problems) == (True, [])


class LeakySandbox(DockerSandbox):
    """Passes a key into the container, which the real runner never does."""

    def command(self, name, mounts, argv):
        command = super().command(name, mounts, argv)
        at = command.index(self.image)
        return [*command[:at], "-e", "ANTHROPIC_API_KEY=sk-ant-leak", *command[at:]]


@pytest.mark.docker
def test_probe_detects_a_leaked_key(sandbox_image, tmp_path):
    passed, problems, _ = run_probe(LeakySandbox(sandbox_image, 120), tmp_path)
    assert not passed
    assert any(problem.startswith("api_key") for problem in problems)


@pytest.mark.docker
def test_a_slow_converter_is_stopped(sandbox_image, tmp_path):
    code = tmp_path / "code"
    code.mkdir()
    (code / "prepare.py").write_text("import time\ntime.sleep(60)\n")
    (tmp_path / "in").mkdir()
    execution = DockerSandbox(sandbox_image, 3).run_converter(
        code, tmp_path / "in", tmp_path / "out"
    )
    assert execution.timed_out
    assert execution.seconds < 30


@pytest.mark.docker
def test_reference_converter_runs_in_the_sandbox(sandbox_image, tmp_path):
    fixture = list_fixtures("dev")[0]
    code, inputs = tmp_path / "code", tmp_path / "input"
    code.mkdir()
    inputs.mkdir()
    (code / "prepare.py").write_text(REFERENCE.read_text())
    for name in ("factors.json", "data.json", "task.yaml"):
        (inputs / name).write_bytes((fixture.directory / name).read_bytes())
    execution = DockerSandbox(sandbox_image, 120).run_converter(code, inputs, tmp_path / "out")
    assert execution.ok, execution.stderr
    assert compare_result(0, "", tmp_path / "out", fixture.expected) == []


def test_collect_outputs_keeps_only_regular_top_level_files(tmp_path):
    from onboard.sandbox import collect_outputs

    secret = tmp_path / "heldout_expected.csv"
    secret.write_text("held-out answer")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "summary.json").write_text("{}")
    (raw / "prepared.csv").symlink_to(secret)
    (raw / "config.yaml").symlink_to("../heldout_expected.csv")
    (raw / "nested").mkdir()
    (raw / "nested" / "x.txt").write_text("x")

    problems = collect_outputs(raw, tmp_path / "out")

    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["summary.json"]
    assert len(problems) == 3
    assert all("not a regular file" in p or "directory" in p for p in problems)


def test_collect_outputs_skips_oversized_files(tmp_path, monkeypatch):
    import onboard.sandbox

    monkeypatch.setattr(onboard.sandbox, "OUTPUT_FILE_LIMIT", 10)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "prepared.csv").write_text("x" * 11)
    problems = onboard.sandbox.collect_outputs(raw, tmp_path / "out")
    assert not (tmp_path / "out" / "prepared.csv").exists()
    assert "larger than" in problems[0]


@pytest.mark.docker
def test_symlinks_written_by_generated_code_are_not_followed(sandbox_image, tmp_path):
    (tmp_path / "secret.txt").write_text("held-out answer")
    code = tmp_path / "code"
    code.mkdir()
    (code / "prepare.py").write_text(
        "import os\n"
        "os.symlink('../../secret.txt', '/output/prepared.csv')\n"
        "os.symlink('/proc/self/environ', '/output/summary.json')\n"
        "os.makedirs('/output/sub/deeper')\n"
        "open('/output/sub/deeper/f.txt', 'w').write('x')\n"
        "open('/output/config.yaml', 'w').write('ok: 1\\n')\n"
    )
    (tmp_path / "in").mkdir()
    out = tmp_path / "work" / "out"
    execution = DockerSandbox(sandbox_image, 60).run_converter(code, tmp_path / "in", out)

    assert execution.exit_code == 0, execution.stderr
    assert sorted(p.name for p in out.iterdir()) == ["config.yaml"]
    assert "prepared.csv" in execution.stderr and "not a regular file" in execution.stderr
    import shutil

    shutil.rmtree(tmp_path / "work")  # the host can clean up what the container wrote
