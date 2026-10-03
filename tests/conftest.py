"""Shared pytest fixtures: paths, Docker availability, and the sandbox image."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from onboard.config import ROOT


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if any("docker" in item.keywords for item in items) and not docker_available():
        skip = pytest.mark.skip(reason="Docker daemon not available")
        for item in items:
            if "docker" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def sandbox_image() -> str:
    """Build the sandbox image once per session and return its image ID."""
    subprocess.run(
        ["docker", "build", "-q", "-t", "study-onboarding-runner", str(ROOT / "sandbox")],
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", "study-onboarding-runner"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
