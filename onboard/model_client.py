"""Model access behind one small interface (spec section 4).

The loop sees only ModelClient.create and plain-dict content blocks, so another
provider, a scripted fake, or a replay of a recorded run can stand in for the
Anthropic API without touching the loop.
"""

from __future__ import annotations

import copy
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, cast

# Cache pricing relative to the input price: writes with the default 5-minute
# TTL cost 1.25x, reads 0.1x.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.1


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def cost(self, input_price: float, output_price: float) -> float:
        """Estimated USD, from per-million-token prices."""
        input_equivalent = (
            self.input_tokens
            + CACHE_WRITE_MULTIPLIER * self.cache_creation_input_tokens
            + CACHE_READ_MULTIPLIER * self.cache_read_input_tokens
        )
        return (input_equivalent * input_price + self.output_tokens * output_price) / 1_000_000


@dataclass(frozen=True)
class ModelResponse:
    id: str
    model: str
    stop_reason: str | None
    content: list[dict[str, Any]]
    usage: Usage
    seconds: float = 0.0
    stop_details: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> ModelResponse:
        return cls(**{**value, "usage": Usage(**value["usage"])})


class ModelClient(Protocol):
    def create(
        self,
        *,
        model: str,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
        effort: str,
    ) -> ModelResponse: ...


class AnthropicClient:
    """Calls the Messages API directly, with no agent framework."""

    def __init__(self, client: Any = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client

    def create(
        self,
        *,
        model: str,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
        effort: str,
    ) -> ModelResponse:
        cached_tools = copy.deepcopy(tools)
        if cached_tools:
            cached_tools[-1]["cache_control"] = {"type": "ephemeral"}
        started = time.monotonic()
        # Thinking stays at the model's adaptive default; effort is set explicitly.
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=cached_tools,
            tool_choice={"type": "auto"},
            messages=messages,
            output_config={"effort": effort},
        )
        seconds = time.monotonic() - started
        usage = response.usage
        stop_details = getattr(response, "stop_details", None)
        return ModelResponse(
            id=response.id,
            model=response.model,
            stop_reason=response.stop_reason,
            content=[
                cast(dict[str, Any], block.model_dump(mode="json", exclude_none=True))
                for block in response.content
            ],
            usage=Usage(
                input_tokens=usage.input_tokens or 0,
                output_tokens=usage.output_tokens or 0,
                cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
                cache_read_input_tokens=usage.cache_read_input_tokens or 0,
            ),
            seconds=seconds,
            stop_details=stop_details.model_dump(mode="json") if stop_details else None,
        )


@dataclass
class ScriptedClient:
    """Returns prepared responses in order and records every request it was sent.

    Used by the harness tests and by `onboard replay`, so neither needs an API key.
    """

    responses: list[ModelResponse]
    requests: list[dict[str, Any]] = field(default_factory=list)

    def create(
        self,
        *,
        model: str,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
        effort: str,
    ) -> ModelResponse:
        self.requests.append(
            {
                "model": model,
                "system": system,
                "tools": copy.deepcopy(tools),
                "messages": copy.deepcopy(messages),
                "max_tokens": max_tokens,
                "effort": effort,
            }
        )
        if len(self.requests) > len(self.responses):
            raise RuntimeError("the scripted client has no response left for this request")
        return self.responses[len(self.requests) - 1]
