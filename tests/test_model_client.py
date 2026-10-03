"""Model clients: Anthropic by default, other providers through their Anthropic-compatible API."""

from __future__ import annotations

from typing import Any

import pytest

from onboard.config import ConfigError, load_config
from onboard.model_client import AnthropicClient, client_for
from onboard.tools import TOOL_DEFINITIONS

CONFIG = load_config()


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        from anthropic.types import Message

        self.calls.append(kwargs)
        return Message.model_validate(
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": kwargs["model"],
                "content": [{"type": "text", "text": "hi"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )


class FakeAnthropic:
    def __init__(self):
        self.messages = FakeMessages()


HISTORY: list[dict[str, Any]] = [
    {"role": "user", "content": "task"},
    {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}]},
    {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "t1",
                "content": "no version 'v9'",
                "is_error": True,
            }
        ],
    },
]


def send(compatible: bool):
    import copy

    fake = FakeAnthropic()
    history = copy.deepcopy(HISTORY)
    AnthropicClient(fake, compatible=compatible).create(
        model="m",
        system="s",
        tools=TOOL_DEFINITIONS,
        messages=history,
        max_tokens=10,
        effort="high",
    )
    assert history == HISTORY, "the client must not change the harness's history"
    return fake.messages.calls[0]


def test_anthropic_requests_keep_strict_tools_and_cache_breakpoints():
    sent = send(compatible=False)
    assert all(tool["strict"] is True for tool in sent["tools"])
    assert sent["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert sent["output_config"] == {"effort": "high"}
    assert sent["messages"][2]["content"][0]["content"] == "no version 'v9'"


def test_compatible_requests_drop_strict_and_mark_errors_in_the_text():
    sent = send(compatible=True)
    assert not any("strict" in tool for tool in sent["tools"])
    result = sent["messages"][2]["content"][0]
    assert result["content"] == "Error: no version 'v9'"
    assert sent["output_config"] == {"effort": "high"}


def _with_model(model: str):
    return CONFIG.with_overrides(model=model)


def test_deepseek_uses_only_its_own_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-must-not-leave")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "anthropic-token-must-not-leave")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    monkeypatch.delenv("ANTHROPIC_CUSTOM_HEADERS", raising=False)

    client = client_for(_with_model("deepseek-flash"))

    assert isinstance(client, AnthropicClient) and client.compatible
    sdk = client.client
    assert str(sdk.base_url).rstrip("/") == "https://api.deepseek.com/anthropic"
    assert sdk.api_key == "sk-deepseek-test"
    assert sdk.auth_token is None
    sent = " ".join(sdk.default_headers.values())
    assert "must-not-leave" not in sent


def test_deepseek_without_its_key_is_refused(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-must-not-leave")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY"):
        client_for(_with_model("deepseek-flash"))


def test_deepseek_refuses_custom_headers_from_the_environment(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", "x-secret: value")
    with pytest.raises(ConfigError, match="ANTHROPIC_CUSTOM_HEADERS"):
        client_for(_with_model("deepseek-flash"))


def test_claude_models_use_the_anthropic_api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    client = client_for(CONFIG)
    assert isinstance(client, AnthropicClient) and not client.compatible
    assert "anthropic.com" in str(client.client.base_url)


def test_every_priced_model_has_a_known_provider():
    for model in CONFIG.prices:
        CONFIG.provider(model)


def test_deepseek_prices_are_the_peak_rates():
    price = CONFIG.price("deepseek-flash")
    assert (price.input, price.output) == (0.30, 1.20)
