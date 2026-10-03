"""Harness configuration (spec section 21) and repository paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.yaml"
EFFORTS = ("low", "medium", "high", "xhigh", "max")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    requests: int
    submissions: int
    wall_clock_seconds: float
    usd: float
    sandbox_seconds: int


@dataclass(frozen=True)
class Price:
    input: float
    output: float


@dataclass(frozen=True)
class SandboxConfig:
    image: str
    digest: str

    @property
    def reference(self) -> str:
        """What `docker run` is given: the image ID, so the checked image is the one used."""
        return self.digest


@dataclass(frozen=True)
class Config:
    model: str
    effort: str
    max_tokens: int
    limits: Limits
    prices: dict[str, Price]
    sandbox: SandboxConfig
    runs_per_task: int
    path: Path

    def price(self, model: str) -> Price:
        try:
            return self.prices[model]
        except KeyError:
            raise ConfigError(
                f"no price for model {model!r} in prices_per_million_tokens"
            ) from None

    def with_overrides(self, model: str | None = None, effort: str | None = None) -> Config:
        values = dict(self.__dict__)
        if model is not None:
            values["model"] = model
        if effort is not None:
            values["effort"] = effort
        updated = Config(**values)
        updated.check()
        return updated

    def check(self) -> None:
        if self.effort not in EFFORTS:
            raise ConfigError(f"effort must be one of {EFFORTS}, not {self.effort!r}")
        self.price(self.model)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a mapping")
    return value


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    raw = _mapping(yaml.safe_load(path.read_text()), "config")
    try:
        limits = _mapping(raw["limits"], "limits")
        prices = _mapping(raw["prices_per_million_tokens"], "prices_per_million_tokens")
        sandbox = _mapping(raw["sandbox"], "sandbox")
        config = Config(
            model=str(raw["model"]),
            effort=str(raw["effort"]),
            max_tokens=int(raw["max_tokens"]),
            limits=Limits(
                requests=int(limits["requests"]),
                submissions=int(limits["submissions"]),
                wall_clock_seconds=float(limits["wall_clock_seconds"]),
                usd=float(limits["usd"]),
                sandbox_seconds=int(limits["sandbox_seconds"]),
            ),
            prices={
                str(name): Price(input=float(p["input"]), output=float(p["output"]))
                for name, p in prices.items()
            },
            sandbox=SandboxConfig(image=str(sandbox["image"]), digest=str(sandbox["digest"])),
            runs_per_task=int(_mapping(raw.get("eval", {}), "eval").get("runs_per_task", 1)),
            path=path,
        )
    except KeyError as error:
        raise ConfigError(f"config is missing {error.args[0]!r}") from None
    config.check()
    return config
