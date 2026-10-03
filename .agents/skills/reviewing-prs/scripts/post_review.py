"""Publish the two authorized review comments in order, without touching PR code."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Protocol, cast

REPO = "Jack-Coutts/study-onboarding-agent"

Comment = dict[str, Any]


class Api(Protocol):
    def __call__(
        self, path: str, payload: dict[str, Any] | None = ..., *, paginate: bool = ...
    ) -> Any: ...


def github(path: str, payload: dict[str, Any] | None = None, *, paginate: bool = False) -> Any:
    command = ["gh", "api", path]
    if paginate:
        command += ["--paginate", "--slurp"]
    if payload is not None:
        command += ["--method", "POST", "--input", "-"]
    result = subprocess.run(
        command,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def publish(
    pr: int, base: str, head: str, key: str, stage: str, body: str, api: Api = github
) -> Comment:
    if (
        pr < 1
        or stage not in {"scientific", "simplicity"}
        or not all(
            re.fullmatch(pattern, value)
            for pattern, value in (
                (r"[a-f0-9]{40}", base),
                (r"[a-f0-9]{40}", head),
                (r"[a-f0-9]{64}", key),
            )
        )
    ):
        raise ValueError("Invalid pinned review identifiers")
    if not body.strip():
        raise ValueError("Review body is empty")
    user_id = api("user")["id"]
    comments_path = f"repos/{REPO}/issues/{pr}/comments"
    marker = f"<!-- onboarding-review:{key}:{stage} -->"
    primary_marker = f"<!-- onboarding-review:{key}:scientific -->"

    def comments() -> list[Comment]:
        return [comment for page in api(comments_path, paginate=True) for comment in page]

    def find(items: list[Comment], token: str) -> Comment | None:
        return next(
            (
                item
                for item in items
                if item.get("user", {}).get("id") == user_id and token in item.get("body", "")
            ),
            None,
        )

    items = comments()
    previous = find(items, marker)
    if previous:
        return previous
    primary = find(items, primary_marker)
    if stage == "simplicity" and primary is None:
        raise ValueError("Initial scientific feedback must be confirmed on GitHub first")
    current = api(f"repos/{REPO}/pulls/{pr}")
    if current["state"] != "open":
        raise ValueError("PR is no longer open; no comment posted")
    title = "Scientific and correctness review" if stage == "scientific" else "Simplicity follow-up"
    scope = (
        f"Base: [{base[:7]}](https://github.com/{REPO}/commit/{base}). "
        f"Reviewed head: [{head[:7]}](https://github.com/{REPO}/commit/{head})."
    )

    def merge_base(base_sha: str) -> str:
        return cast(
            str, api(f"repos/{REPO}/compare/{base_sha}...{head}")["merge_base_commit"]["sha"]
        )

    # A base branch that only advanced keeps the reviewed diff; a retarget changes it.
    if current["head"]["sha"] != head:
        stale = "\n\n**Stale scope:** this review does not cover the current PR head."
    elif current["base"]["sha"] != base and merge_base(current["base"]["sha"]) != merge_base(base):
        stale = (
            "\n\n**Stale scope:** the PR's base comparison changed after this review,"
            " so its current diff differs from the reviewed diff."
        )
    else:
        stale = ""
    prior = (
        f"\n\nInitial feedback: {primary['html_url']}" if primary and stage == "simplicity" else ""
    )
    payload = {"body": f"{marker}\n## {title}\n\n{scope}{stale}{prior}\n\n{body.strip()}"}
    try:
        posted = api(comments_path, payload)
    except (subprocess.SubprocessError, OSError):
        # A failed acknowledgement does not prove the write failed. Read back;
        # if still unresolved, stop. A later invocation also checks before writing.
        recovered = find(comments(), marker)
        if recovered:
            return recovered
        raise
    confirmed: Comment = api(f"repos/{REPO}/issues/comments/{posted['id']}")
    if find([confirmed], marker) is None:
        raise ValueError("Posted comment could not be confirmed")
    return confirmed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--stage", choices=("scientific", "simplicity"), required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    args = parser.parse_args()
    comment = publish(
        args.pr, args.base, args.head, args.key, args.stage, args.body_file.read_text()
    )
    print(json.dumps({"id": comment["id"], "url": comment["html_url"], "stage": args.stage}))


if __name__ == "__main__":
    main()
