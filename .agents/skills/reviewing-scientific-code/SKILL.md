---
name: reviewing-scientific-code
description: "Reviews local diffs, branches, and uncommitted changes against requirements, repository standards, scientific invariants, and privacy. Use for in-repo code-review requests that are not a GitHub PR review. For pull requests, use reviewing-prs instead."
disable-model-invocation: true
license: MIT
metadata:
  upstream: https://github.com/mattpocock/skills/tree/d81f3a183412e71a5b1e84ca21bc1a35eea03a60/skills/engineering/code-review
  upstream-revision: d81f3a183412e71a5b1e84ca21bc1a35eea03a60
---

# Reviewing scientific code

Review intent and scientific correctness before style. A review does not authorize fixes.

Read the [repository workflow](../reference/repository.md), `AGENTS.md`,
`docs/data_policy.md`, and the matching decision pages. Use the contract
checker tests, the reference-converter fixture tests, and the broken-variant
tests to locate existing guarantees where relevant. Inspect `tests/conftest.py`
before claiming sandbox coverage from a passing suite: Docker tests skip
without Docker.

## GitHub pull requests

For a PR number, URL, or label-triggered review workflow, stop here and follow
[reviewing-prs](../reviewing-prs/SKILL.md) instead. Use
[reviewing-pr-simplicity](../reviewing-pr-simplicity/SKILL.md) only as an
explicit follow-up after that pass. This skill does not replace pinned PR scope,
safe execution, synthetic pipeline checks, visual verification, or authorized
posting.

## Pin the scope

Resolve the requested base/ref and read the actual diff. For branch changes,
`git diff <base>...HEAD` compares committed work from the merge-base. For work
in progress, include unstaged `git diff`, staged `git diff --cached`, and relevant
untracked files as well. State the scope; do not silently omit local edits.
Ask only when an essential baseline cannot be established from the request.

Read the originating request/spec, owning code and callers, repository guidance,
scientific decision pages, and relevant tests. Use the conversation as intent
when no separate spec exists. Missing tracker configuration is not a review blocker.

## Review axes

1. **Requirements:** missing/partial behavior, incorrect interpretations,
   unintended scope, error paths, compatibility, and user-facing contracts.
2. **Standards and design:** actual repository rules, clear ownership, justified
   abstraction, and maintainability. Code-smell labels are heuristics, not proof
   that a refactor is required. Keep meaningful scientific comments and guards.
3. **Scientific correctness:** input alignment and scale, missingness/zero rules,
   contrast and class direction, design validity, subject grouping, fold-local
   fitting/tuning, reference calculations, statistical calibration, and the
   assumptions under which results are interpretable.
4. **Privacy and evidence:** forbidden private measurements and derived counts,
   metrics, paths, names, or identifiers in code, fixtures, docs, captures,
   commit/PR text, or proposed publication. Check provenance, not just credentials.

## Confirm and report

For material concerns, trace a concrete failure and execute a targeted safe check
when practical. Distinguish executed evidence from source inspection and untested
risks. Report actual R integration coverage and dependency-related skips.
Decision checkers confirm specified consistency rules, not scientific validity.

Review directly by default. Use independent bounded reviewers only when permitted
by tool rules and worth their cost. Give them the exact code state and constraints;
assess their findings yourself rather than forwarding reports verbatim.

Return actionable findings with severity, source locations, the violated
requirement/invariant, and a concrete failing case or consequence. Separate
optional design advice from defects. Report gaps even when no defect is found.
Do not prescribe unrelated cleanup, edit the code, commit, or publish a review
comment unless the user requested that action. A favorable review is not permission
to merge or deploy.
