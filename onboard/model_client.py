"""Model access behind one small interface (spec section 4).

The loop sees only ModelClient.create and plain-dict content blocks, so another
provider, a scripted fake, or a replay of a recorded run can stand in for the
Anthropic API without touching the loop.
"""

from __future__ import annotations

import copy
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, cast

from onboard.config import Config, ConfigError

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
    """Calls the Messages API directly, with no agent framework.

    compatible=True adapts requests for another provider's Anthropic-compatible
    endpoint. DeepSeek's documents `is_error` on tool results as ignored and do not
    list `strict`, so errors are also stated in the result text and `strict` is
    dropped; the harness validates every tool argument itself either way. The
    harness's own history is never changed: the adapted copy is built per request.
    """

    def __init__(self, client: Any = None, compatible: bool = False) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        self.compatible = compatible

    def _adapt(
        self, tools: list[dict[str, Any]], messages: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        tools = copy.deepcopy(tools)
        if tools:
            tools[-1]["cache_control"] = {"type": "ephemeral"}
        if not self.compatible:
            return tools, messages
        for tool in tools:
            tool.pop("strict", None)
        adapted = copy.deepcopy(messages)
        for message in adapted:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if block.get("type") == "tool_result" and block.get("is_error"):
                    block["content"] = f"Error: {block['content']}"
        return tools, adapted

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
        sent_tools, sent_messages = self._adapt(tools, messages)
        started = time.monotonic()
        # Thinking stays at the model's adaptive default; effort is set explicitly.
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=sent_tools,
            tool_choice={"type": "auto"},
            messages=sent_messages,
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


def client_for(config: Config) -> AnthropicClient:
    """The client for config.model: the Anthropic API, or the model's provider."""
    provider = config.provider(config.model)
    if provider is None:
        return AnthropicClient()
    key = os.environ.get(provider.api_key_env)
    if not key:
        raise ConfigError(f"{config.model} needs {provider.api_key_env} set in the environment")
    if os.environ.get("ANTHROPIC_CUSTOM_HEADERS"):
        # The SDK adds these headers to every request, so they would go to the provider.
        raise ConfigError(f"unset ANTHROPIC_CUSTOM_HEADERS before calling {provider.name}")
    import anthropic

    # An explicit key stops the SDK reading ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN,
    # so Anthropic credentials are never sent to another provider.
    return AnthropicClient(
        anthropic.Anthropic(api_key=key, base_url=provider.base_url), compatible=True
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
