"""Synthetic fixtures (spec section 5.3).

Dev fixtures' expected outputs may be shown to the agent during repair. Held-out
fixtures' expected outputs must never reach it; only `onboard eval` reads them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from onboard.config import ROOT

Split = Literal["dev", "heldout"]
FIXTURES = ROOT / "fixtures"
INPUT_FILES = ("factors.json", "data.json", "summary.json", "task.yaml")


@dataclass(frozen=True)
class Fixture:
    id: str
    split: Split
    directory: Path

    @property
    def factors(self) -> Path:
        return self.directory / "factors.json"

    @property
    def data(self) -> Path:
        return self.directory / "data.json"

    @property
    def summary(self) -> Path:
        return self.directory / "summary.json"

    @property
    def task(self) -> Path:
        return self.directory / "task.yaml"

    @property
    def expected(self) -> Path:
        return self.directory / "expected"

    @property
    def expects_error(self) -> bool:
        return (self.expected / "error.txt").exists()


def list_fixtures(split: Split, root: Path = FIXTURES) -> list[Fixture]:
    base = root / split
    return [
        Fixture(id=path.name, split=split, directory=path)
        for path in sorted(base.iterdir())
        if path.is_dir()
    ]
