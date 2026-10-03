"""Synthetic GitHub responses only; no network requests or real comments."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[1] / ".agents/skills/reviewing-prs/scripts/post_review.py"
spec = importlib.util.spec_from_file_location("review_publisher", SOURCE)
assert spec is not None and spec.loader is not None
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

BASE, HEAD, KEY = "b" * 40, "c" * 40, "d" * 64


class Github:
    def __init__(self):
        self.comments = []
        self.posts = []
        self.head = HEAD
        self.base = BASE
        self.merge_bases = {BASE: BASE}
        self.state = "open"
        self.lose_ack = False
        self.hide_once = False

    def __call__(self, path, payload=None, *, paginate=False):
        if path == "user":
            return {"id": 7}
        if path.endswith("/pulls/5"):
            return {"state": self.state, "head": {"sha": self.head}, "base": {"sha": self.base}}
        if "/compare/" in path:
            base = path.rsplit("/", 1)[1].split("...")[0]
            return {"merge_base_commit": {"sha": self.merge_bases[base]}}
        if paginate:
            if self.hide_once:
                self.hide_once = False
                return [[], []]
            return [[], list(self.comments)]  # Relevant comments are on the second page.
        if payload is not None:
            self.posts.append(payload)
            comment = {
                "id": len(self.posts),
                "user": {"id": 7},
                "body": payload["body"],
                "html_url": f"https://example.invalid/comment/{len(self.posts)}",
            }
            self.comments.append(comment)
            if self.lose_ack:
                self.lose_ack = False
                raise subprocess.TimeoutExpired("gh", 30)
            return comment
        return next(item for item in self.comments if path.endswith(f"/comments/{item['id']}"))


def post(api, stage):
    return publisher.publish(5, BASE, HEAD, KEY, stage, "Synthetic review findings.", api)


def test_followup_requires_own_confirmed_primary_feedback():
    api = Github()
    api.comments.append({"user": {"id": 8}, "body": f"<!-- onboarding-review:{KEY}:scientific -->"})
    with pytest.raises(ValueError, match="Initial scientific feedback"):
        post(api, "simplicity")
    assert api.posts == []


def test_separate_ordered_comments_dedupe_and_stale_scope():
    api = Github()
    primary = post(api, "scientific")
    assert "## Scientific and correctness review" in primary["body"]
    assert "Stale scope" not in primary["body"]
    assert post(api, "scientific") == primary
    api.head = "e" * 40
    followup = post(api, "simplicity")
    assert followup["id"] != primary["id"]
    assert "## Simplicity follow-up" in followup["body"]
    assert "Stale scope" in followup["body"]
    assert f"Initial feedback: {primary['html_url']}" in followup["body"]
    assert f"/commit/{HEAD}" in followup["body"]
    assert post(api, "simplicity") == followup
    assert len(api.posts) == 2


def test_stale_scope_flags_a_retargeted_base_but_not_an_advanced_one():
    api = Github()
    api.base = "f" * 40  # The base branch advanced; the reviewed merge base still applies.
    api.merge_bases[api.base] = BASE
    assert "Stale scope" not in post(api, "scientific")["body"]
    api.base = "a" * 40  # Retargeted onto a branch with a different merge base.
    api.merge_bases[api.base] = api.base
    assert "base comparison changed" in post(api, "simplicity")["body"]


def test_lost_acknowledgement_is_recovered_without_second_write():
    api = Github()
    api.lose_ack = True
    result = post(api, "scientific")
    assert result == api.comments[0]
    assert len(api.posts) == 1
    assert post(api, "scientific") == result
    assert len(api.posts) == 1


def test_unknown_post_outcome_stops_then_reads_back_before_retry():
    api = Github()
    original = api.__call__

    def delayed_visibility(path, payload=None, *, paginate=False):
        try:
            return original(path, payload, paginate=paginate)
        except subprocess.TimeoutExpired:
            api.hide_once = True
            raise

    api.lose_ack = True
    with pytest.raises(subprocess.TimeoutExpired):
        post(delayed_visibility, "scientific")
    assert len(api.posts) == 1
    assert post(api, "scientific") == api.comments[0]
    assert len(api.posts) == 1


def test_closed_pr_and_invalid_scope_do_not_post():
    api = Github()
    api.state = "closed"
    with pytest.raises(ValueError, match="no longer open"):
        post(api, "scientific")
    with pytest.raises(ValueError, match="Invalid pinned"):
        publisher.publish(5, BASE, "main", KEY, "scientific", "Report", api)
    assert api.posts == []
