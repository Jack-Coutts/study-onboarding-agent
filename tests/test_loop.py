"""The agent loop against a scripted model client (spec section 20)."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest

from onboard.config import load_config
from onboard.loop import FINISH_REMINDER, AgentLoop, RunLog
from onboard.model_client import ScriptedClient
from tests.fakes import response, submit, text, tool_use
from tests.test_tools import make_tools

CONFIG = load_config()


def finish(outcome: str = "complete", version_id: str = "v1"):
    return tool_use("finish", outcome=outcome, version_id=version_id, summary="done")


def validate(version_id: str = "v1"):
    return tool_use("validate_converter", version_id=version_id)


def ok_check(version_id):
    return {"version_id": version_id, "overall": "ok", "checks": {"tests": {"status": "ok"}}}


def failing_check(version_id):
    return {
        "version_id": version_id,
        "overall": "fail",
        "checks": {"tests": {"status": "ok"}, "dev_fixtures": {"status": "fail"}},
    }


def run(tmp_path: Path, responses, config=CONFIG, recheck=ok_check, clock=None, tools=None):
    client = ScriptedClient(list(responses))
    tools = tools or make_tools(tmp_path, max_submissions=config.limits.submissions)
    loop = AgentLoop(
        config=config,
        client=client,
        tools=tools,
        log=RunLog(tmp_path / "log.jsonl"),
        system_prompt="system",
        task_prompt="task",
        recheck=recheck,
        **({"clock": clock} if clock else {}),
    )
    return loop.run(), client, tools, loop


def test_a_validated_finish_passes(tmp_path):
    outcome, client, _, loop = run(
        tmp_path,
        [
            response("tool_use", submit()),
            response("tool_use", validate()),
            response("tool_use", text("Ready."), finish()),
        ],
    )
    assert (outcome.status, outcome.accepted_version) == ("passed", "v1")
    assert loop.accounting.requests == 3
    assert client.requests[0]["effort"] == "high"
    assert client.requests[0]["max_tokens"] == 16000


def test_finish_complete_on_a_failing_version_fails(tmp_path):
    outcome, *_ = run(
        tmp_path,
        [response("tool_use", submit()), response("tool_use", finish())],
        recheck=failing_check,
    )
    assert outcome.status == "failed"
    assert "dev_fixtures" in outcome.reason
    assert outcome.accepted_version is None


def test_needs_review_is_recorded_without_a_recheck(tmp_path):
    def recheck(version_id):
        raise AssertionError("needs_review must not be rechecked as a pass")

    outcome, *_ = run(
        tmp_path,
        [response("tool_use", submit()), response("tool_use", finish("needs_review"))],
        recheck=recheck,
    )
    assert outcome.status == "needs_review"
    assert outcome.finish is not None and outcome.finish.version_id == "v1"


def test_refusal_fails_the_run(tmp_path):
    outcome, *_ = run(tmp_path, [response("refusal")])
    assert (outcome.status, outcome.reason) == ("failed", "the model refused")


def test_no_tool_call_runs_from_a_max_tokens_response(tmp_path):
    cut = submit()
    outcome, client, tools, _ = run(
        tmp_path,
        [
            response("max_tokens", text("Here is the converter"), cut),
            response("tool_use", submit()),
            response("tool_use", finish()),
        ],
    )
    assert outcome.status == "passed"
    assert tools.submissions == 1  # only the second submission ran
    reply = client.requests[1]["messages"][-1]
    assert reply["role"] == "user"
    results = [b for b in reply["content"] if b["type"] == "tool_result"]
    assert [(r["tool_use_id"], r["is_error"]) for r in results] == [(cut["id"], True)]


def test_a_missing_finish_gets_one_reminder_then_fails(tmp_path):
    outcome, client, *_ = run(
        tmp_path, [response("end_turn", text("All done.")), response("end_turn", text("Done!"))]
    )
    assert outcome.status == "failed"
    assert "without calling finish" in outcome.reason
    assert client.requests[1]["messages"][-1]["content"] == [
        {"type": "text", "text": FINISH_REMINDER}
    ]


def test_a_reminder_can_be_followed_by_finish(tmp_path):
    outcome, *_ = run(
        tmp_path,
        [
            response("tool_use", submit()),
            response("end_turn", text("Done.")),
            response("tool_use", finish()),
        ],
    )
    assert outcome.status == "passed"


def test_history_is_append_only(tmp_path):
    _, client, *_ = run(
        tmp_path,
        [
            response("tool_use", submit()),
            response("max_tokens", submit()),
            response("end_turn", text("Done.")),
            response("tool_use", validate(), validate("v9")),
            response("tool_use", finish()),
        ],
    )
    sent = [request["messages"] for request in client.requests]
    for earlier, later in pairwise(sent):
        assert later[: len(earlier)] == earlier
        assert len(later) == len(earlier) + 2
    # Every tool result for a response goes back in one user message.
    parallel = sent[4][-1]["content"]
    assert [b["type"] for b in parallel] == ["tool_result", "tool_result"]
    assert parallel[1]["is_error"] is True


def _with_limits(**changes):
    limits = {**CONFIG.limits.__dict__, **changes}
    return type(CONFIG)(**{**CONFIG.__dict__, "limits": type(CONFIG.limits)(**limits)})


def test_the_request_limit_ends_the_run(tmp_path):
    outcome, client, *_ = run(
        tmp_path,
        [response("tool_use", submit()), response("tool_use", validate())],
        config=_with_limits(requests=2),
    )
    assert (outcome.status, outcome.reason) == ("failed", "limit reached: requests")
    assert len(client.requests) == 2


@pytest.mark.parametrize(
    ("changes", "responses", "limit"),
    [
        (
            {"submissions": 1},
            [response("tool_use", submit()), response("tool_use", submit())],
            "submissions",
        ),
        ({"usd": 0.001}, [response("tool_use", submit(), tokens=1000)], "usd"),
    ],
)
def test_each_limit_ends_the_run(tmp_path, changes, responses, limit):
    outcome, *_ = run(
        tmp_path, [*responses, response("tool_use", finish())], config=_with_limits(**changes)
    )
    assert (outcome.status, outcome.reason) == ("failed", f"limit reached: {limit}")


def test_the_wall_clock_limit_ends_the_run(tmp_path):
    times = iter([0.0, 10.0, 1000.0])
    outcome, client, *_ = run(
        tmp_path,
        [response("tool_use", submit()), response("tool_use", finish())],
        clock=lambda: next(times),
    )
    assert (outcome.status, outcome.reason) == ("failed", "limit reached: wall_clock_seconds")
    assert len(client.requests) == 1


def test_a_sandbox_timeout_ends_the_run(tmp_path):
    tools = make_tools(tmp_path)
    tools.validator = lambda version_id, directory: {"overall": "fail", "sandbox_timed_out": True}
    outcome, *_ = run(
        tmp_path,
        [
            response("tool_use", submit()),
            response("tool_use", validate()),
            response("tool_use", finish()),
        ],
        tools=tools,
    )
    assert (outcome.status, outcome.reason) == ("failed", "limit reached: sandbox_seconds")


def test_an_unknown_stop_reason_fails(tmp_path):
    outcome, *_ = run(tmp_path, [response("pause_turn")])
    assert outcome.status == "failed"
    assert "pause_turn" in outcome.reason


def test_every_request_response_and_tool_call_is_logged(tmp_path):
    import json

    run(tmp_path, [response("tool_use", submit()), response("tool_use", finish())])
    events = [
        json.loads(line)["event"] for line in (tmp_path / "log.jsonl").read_text().splitlines()
    ]
    assert events == [
        "message",
        "request",
        "response",
        "tool_call",
        "tool_result",
        "message",
        "request",
        "response",
        "tool_call",
        "tool_result",
        "message",
        "recheck",
        "status",
    ]
