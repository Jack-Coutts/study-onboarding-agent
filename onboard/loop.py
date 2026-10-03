"""The agent loop (spec section 9) and how a run's status is decided (section 10).

The message history is append-only: earlier messages are never edited or
dropped, because the API ties thinking blocks to the exact conversation that
produced them. The model's finish call is a claim; the harness re-runs the
development checks before it records `passed`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from onboard.config import Config
from onboard.model_client import ModelClient, ModelResponse, Usage
from onboard.tools import TOOL_DEFINITIONS, FinishClaim, Tools

MAX_TOKENS_NOTE = (
    "Not run: your reply reached the max_tokens limit, so this tool call may be incomplete."
)
SHORTER_REPLY = (
    "Your last reply reached the max_tokens limit, so none of its tool calls ran. "
    "Send a shorter reply: make one tool call at a time, and keep notes brief."
)
FINISH_REMINDER = (
    "You ended your turn without calling finish. Call finish now: outcome 'complete' with a "
    "validated version, or 'needs_review' with the reason a human decision is needed."
)


class RunLog:
    """Append-only JSONL log of every request, response, tool call, and result."""

    def __init__(self, path: Path, clock: Callable[[], float] = time.time) -> None:
        self.path = path
        self.clock = clock
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **payload: Any) -> None:
        record = {"event": event, "time": round(self.clock(), 3), **payload}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


@dataclass
class Outcome:
    status: str
    reason: str
    finish: FinishClaim | None = None
    accepted_version: str | None = None
    final_validation: dict[str, Any] | None = None


@dataclass
class Accounting:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    estimated_usd: float = 0.0
    model_seconds: float = 0.0
    served_models: list[str] = field(default_factory=list)

    def add(self, response: ModelResponse, cost: float) -> None:
        self.requests += 1
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        self.cache_creation_input_tokens += response.usage.cache_creation_input_tokens
        self.cache_read_input_tokens += response.usage.cache_read_input_tokens
        self.estimated_usd += cost
        self.model_seconds += response.seconds
        if response.model not in self.served_models:
            self.served_models.append(response.model)


def _tool_result(tool_use_id: str, content: str, is_error: bool) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if is_error:
        block["is_error"] = True
    return block


class AgentLoop:
    def __init__(
        self,
        config: Config,
        client: ModelClient,
        tools: Tools,
        log: RunLog,
        system_prompt: str,
        task_prompt: str,
        recheck: Callable[[str], dict[str, Any]],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.client = client
        self.tools = tools
        self.log = log
        self.system_prompt = system_prompt
        self.task_prompt = task_prompt
        self.recheck = recheck
        self.clock = clock
        self.accounting = Accounting()
        self.messages: list[dict[str, Any]] = []
        self.started = 0.0

    def limit_reached(self, before_request: bool = True) -> str | None:
        """A limit that has been reached. The request count matters only before a new
        request, so the last permitted response may still finish the run."""
        limits = self.config.limits
        if self.tools.limit_hit:
            return self.tools.limit_hit
        if before_request and self.accounting.requests >= limits.requests:
            return "requests"
        if self.clock() - self.started >= limits.wall_clock_seconds:
            return "wall_clock_seconds"
        if self.accounting.estimated_usd >= limits.usd:
            return "usd"
        return None

    def run(self) -> Outcome:
        self.started = self.clock()
        price = self.config.price(self.config.model)
        self.messages.append({"role": "user", "content": self.task_prompt})
        self.log.write("message", message=self.messages[-1])
        reminded = False
        while True:
            limit = self.limit_reached()
            if limit:
                return self.end("failed", f"limit reached: {limit}")
            sent = len(self.messages)
            self.log.write("request", number=self.accounting.requests + 1, messages=sent)
            response = self.client.create(
                model=self.config.model,
                system=self.system_prompt,
                tools=TOOL_DEFINITIONS,
                messages=self.messages,
                max_tokens=self.config.max_tokens,
                effort=self.config.effort,
            )
            self.accounting.add(response, response.usage.cost(price.input, price.output))
            self.log.write("response", response=response.to_json())
            self.messages.append({"role": "assistant", "content": response.content})

            tool_uses = [block for block in response.content if block.get("type") == "tool_use"]
            if response.stop_reason == "refusal":
                return self.end("failed", "the model refused", details=response.stop_details)
            if response.stop_reason == "max_tokens":
                content: list[dict[str, Any]] = [
                    _tool_result(block["id"], MAX_TOKENS_NOTE, True) for block in tool_uses
                ]
                content.append({"type": "text", "text": SHORTER_REPLY})
                self.append_user(content)
                continue
            if response.stop_reason == "end_turn" and not tool_uses:
                if reminded:
                    return self.end("failed", "the model ended twice without calling finish")
                reminded = True
                self.append_user([{"type": "text", "text": FINISH_REMINDER}])
                continue
            if response.stop_reason not in ("tool_use", "end_turn"):
                return self.end("failed", f"unexpected stop_reason {response.stop_reason!r}")

            results = []
            for block in tool_uses:
                self.log.write(
                    "tool_call", id=block["id"], name=block["name"], input=block["input"]
                )
                result = self.tools.call(block["name"], block["input"])
                self.log.write(
                    "tool_result", id=block["id"], content=result.content, is_error=result.is_error
                )
                results.append(_tool_result(block["id"], result.content, result.is_error))
            self.append_user(results)
            if self.tools.finish_claim is not None:
                # A limit reached by this response (cost, time, a sandbox timeout) is not
                # excused because the same response also called finish.
                limit = self.limit_reached(before_request=False)
                if limit:
                    return self.end(
                        "failed", f"limit reached: {limit}", finish=self.tools.finish_claim
                    )
                return self.decide(self.tools.finish_claim)

    def append_user(self, content: list[dict[str, Any]]) -> None:
        self.messages.append({"role": "user", "content": content})
        self.log.write("message", message=self.messages[-1])

    def decide(self, claim: FinishClaim) -> Outcome:
        """Section 10: the model's claim never sets `passed` on its own."""
        if claim.outcome == "needs_review":
            return self.end(
                "needs_review",
                f"finish(needs_review) on {claim.version_id}: {claim.summary}",
                finish=claim,
            )
        try:
            validation = self.recheck(claim.version_id)
        except Exception as error:
            return self.end(
                "failed",
                f"finish(complete) on {claim.version_id}, but the re-run raised {error!r}",
                finish=claim,
            )
        self.log.write("recheck", version_id=claim.version_id, validation=validation)
        if validation.get("sandbox_timed_out"):
            return self.end(
                "failed", "limit reached: sandbox_seconds", finish=claim, validation=validation
            )
        if validation.get("overall") == "ok":
            return self.end(
                "passed",
                f"finish(complete) on {claim.version_id}; all development checks ok",
                finish=claim,
                accepted=claim.version_id,
                validation=validation,
            )
        failing = [name for name, c in validation.get("checks", {}).items() if c["status"] != "ok"]
        return self.end(
            "failed",
            f"finish(complete) on {claim.version_id}, but the re-run fails {failing}",
            finish=claim,
            validation=validation,
        )

    def end(
        self,
        status: str,
        reason: str,
        finish: FinishClaim | None = None,
        accepted: str | None = None,
        validation: dict[str, Any] | None = None,
        details: Any = None,
    ) -> Outcome:
        self.log.write("status", status=status, reason=reason, details=details)
        return Outcome(status, reason, finish, accepted, validation)

    @property
    def usage(self) -> Usage:
        a = self.accounting
        return Usage(
            a.input_tokens,
            a.output_tokens,
            a.cache_creation_input_tokens,
            a.cache_read_input_tokens,
        )
