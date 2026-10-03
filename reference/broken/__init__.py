"""Broken variants: the reference converter with one known mistake reintroduced.

Each module B1..B8 names the mistake and gives exact text replacements on
reference/workbench_rest.py. `build_variant` applies them and fails loudly if the
reference has drifted so a replacement no longer matches exactly once. The result
is a complete, standalone converter, mounted in the sandbox as prepare.py when
the agent's tests are run against it.
"""

from __future__ import annotations

import importlib
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1] / "workbench_rest.py"
IDS = tuple(f"B{n}" for n in range(1, 9))


def _load(variant: str) -> tuple[str, list[tuple[str, str]]]:
    module = importlib.import_module(f"reference.broken.{variant}")
    return module.MISTAKE, module.REPLACEMENTS


VARIANTS: dict[str, str] = {variant: _load(variant)[0] for variant in IDS}


def build_variant(variant: str) -> str:
    """Source code of one broken variant."""
    if variant not in VARIANTS:
        raise KeyError(f"unknown broken variant {variant!r}")
    mistake, replacements = _load(variant)
    source = REFERENCE.read_text(encoding="utf-8")
    for old, new in replacements:
        count = source.count(old)
        if count != 1:
            raise ValueError(f"{variant}: expected one match for {old!r}, found {count}")
        source = source.replace(old, new)
    if not source.startswith('"""'):
        raise ValueError("the reference must start with its module docstring")
    return f'"""Broken variant {variant}: {mistake}.\n\n' + source[3:]
