"""Isolation probe, run inside the sandbox by `onboard check-sandbox` (spec section 11.3).

Each check tries something the sandbox must stop and records whether it was
blocked. Two controls must succeed, so a broken container does not pass by
blocking everything. Prints one JSON object and always exits 0.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

# Credential variable names, and value shapes of common API keys. The python base
# image sets GPG_KEY to a public signing-key fingerprint, which is not a secret.
SECRET_NAME = re.compile(
    r"^(ANTHROPIC_|OPENAI_|AWS_|GOOGLE_|AZURE_)|API_KEY|_TOKEN$|^GH_TOKEN$|SECRET|PASSWORD"
)
SECRET_VALUE = re.compile(r"sk-ant-|sk-[A-Za-z0-9]{20}|ghp_|github_pat_|AKIA[0-9A-Z]{16}")


def network() -> tuple[bool, str]:
    try:
        urllib.request.urlopen("https://www.metabolomicsworkbench.org", timeout=10)
    except Exception as error:
        return True, f"{type(error).__name__}: {error}"
    return False, "HTTP request succeeded"


def write(path: str) -> tuple[bool, str]:
    try:
        Path(path).write_text("probe")
    except OSError as error:
        return True, f"{type(error).__name__}: {error}"
    return False, f"wrote {path}"


def api_key() -> tuple[bool, str]:
    found = [
        name
        for name, value in os.environ.items()
        if SECRET_NAME.search(name) or SECRET_VALUE.search(value)
    ]
    if found:
        return False, f"credential-like variables present: {sorted(found)}"
    return True, f"no credential-like variables among {sorted(os.environ)}"


def processes(target: int = 500) -> tuple[bool, str]:
    started: list[subprocess.Popen[bytes]] = []
    error_text = ""
    try:
        for _ in range(target):
            started.append(subprocess.Popen(["sleep", "30"]))
    except OSError as error:
        error_text = f"{type(error).__name__}: {error}"
    finally:
        for process in started:
            process.kill()
        for process in started:
            process.wait()
    if len(started) < target:
        return True, f"stopped after {len(started)} processes ({error_text})"
    return False, f"started {target} processes"


def main() -> None:
    checks = {
        "network": network(),
        "write_code": write("/code/probe-write"),
        "write_input": write("/input/probe-write"),
        "write_root": write("/probe-write"),
        "api_key": api_key(),
        "processes": processes(),
    }
    controls = {
        "write_output": write("/output/probe-write"),
        "write_tmp": write("/tmp/probe-write"),
    }
    print(
        json.dumps(
            {
                "blocked": {name: {"blocked": b, "detail": d} for name, (b, d) in checks.items()},
                "controls": {name: {"ok": not b, "detail": d} for name, (b, d) in controls.items()},
            }
        )
    )


if __name__ == "__main__":
    main()
