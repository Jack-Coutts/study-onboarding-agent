---
name: applying-poteto-mode
description: "Applies an evidence-first engineering workflow with simple code, scoped autonomy, and precise prose. Use when explicitly asked for poteto-mode or the adapted pstack style."
disable-model-invocation: true
license: MIT
metadata:
  upstream: https://github.com/cursor/plugins/tree/c47b12849e43f18d5c374c7069c744cc55b0ea00/pstack/skills/poteto-mode
  upstream-revision: c47b12849e43f18d5c374c7069c744cc55b0ea00
---

# Applying poteto mode

Investigate the contract, make the smallest correct change, and prove the
requested outcome. This is a workflow, not a model selection or permission grant.

## Establish the task

1. Read applicable repository guidance and the owning code. For scientific work,
   read the matching decision record before altering a method or assumption.
   Read the shared [repository workflow](../reference/repository.md).
2. Distinguish investigation, planning, implementation, debugging, and refactoring.
   A request for an explanation or recommendation remains read-only.
3. State the behavior contract and consequential assumptions. Before nontrivial
   edits, identify the data shape, scientific invariants, affected consumers,
   and cheapest decisive check. Do not manufacture ceremony for a small change.

## Route only the work that needs it

Read `.agents/skills/<name>/SKILL.md` when its branch applies, using the agent's
skill loader if available or ordinary file reading otherwise. All routed skills
are checked into this repository; no agent-specific tools or installation are
required. Do not load every branch for a small task.

| Task | Skill |
| --- | --- |
| Reproduce and fix a defect | [diagnosing-bugs](../diagnosing-bugs/SKILL.md) |
| Add or change scientific behavior test-first | [testing-scientific-code](../testing-scientific-code/SKILL.md) |
| Preserve behavior while changing structure | [refactoring-safely](../refactoring-safely/SKILL.md) |
| Check cross-module, language, or output consequences | [assessing-blast-radius](../assessing-blast-radius/SKILL.md) |
| Resolve a consequential interface design | [designing-codebase-interfaces](../designing-codebase-interfaces/SKILL.md) |
| Evaluate methodological evidence | [researching-scientific-decisions](../researching-scientific-decisions/SKILL.md) |
| Explain why an existing decision was made | [tracing-decisions](../tracing-decisions/SKILL.md) |
| Review a GitHub pull request | [reviewing-prs](../reviewing-prs/SKILL.md) |
| Review a local diff, branch, or uncommitted changes | [reviewing-scientific-code](../reviewing-scientific-code/SKILL.md) |
| Clarify terminology or record a changed decision | [documenting-decisions](../documenting-decisions/SKILL.md) |
| Plan substantial dependent changes | [planning-scientific-changes](../planning-scientific-changes/SKILL.md) |
| Write or edit the deliverable | [unslopping-writing](../unslopping-writing/SKILL.md) |

## Execution rules

- Inspect observable facts yourself. Ask only for essential missing information,
  unresolved human preferences, or approval required by the governing rules.
- Prefer existing helpers and ownership boundaries. Add a type, layer, tool, or
  alternative design only when it removes real complexity or settles a real risk.
- Separate behavior-preserving refactoring from fixes and new features. Preserve
  meaningful numerical guards, scientific comments, and compatibility contracts.
- After repeated failed fixes, test their shared premise. Do not label a plausible
  explanation the cause until it matches the original failure.
- Scale verification to risk. Numerical correctness, leakage prevention,
  integration, and statistical calibration require different evidence.
- Preserve uncertainty. A cited rationale, a passing test, and a valid scientific
  method are distinct claims. Reviewer agreement is not experimental replication.

## Autonomy and delegation

Proceed with local, reversible work within the user's request. Follow the agent's
governing approval rules for pushes, publication, tracker/chat writes, deployments,
destructive actions, and changes to shared state. "Keep going" does not expand
authorization. A monitoring request does not authorize changes to its target.

Use the current agent's available tools and obey their restrictions. Work directly
by default. Delegation is optional; the workflow must also work for a single agent
with file and shell access. Give any workers the exact scope, guidance, privacy
policy, code state, and required evidence. Isolate concurrent writers; inspect
returned changes and run combined validation. There are no mandatory models.

Private study measurements and derived counts, metrics, paths, identifiers,
study names, and outcome names must not enter committed artifacts or external
messages. Use independently synthetic reproductions and permitted public sources.
Do not copy private diagnostics into prompts for other services without authority.

## Finish on evidence

Inspect the actual result, not only lint or compilation. Use existing checks and
real package entry points when integration changes. For appearance changes,
render representative states and inspect captures; for scientific plots use safe
synthetic data and verify labels, units, contrast direction, and captions.

Report the outcome, decisive executed checks, important gaps or skips, and actual
delivery state. Keep principle names out of replies unless requested. Do not
automatically commit, open a PR, publish a trail, or fix unrelated skill files.
For longer work, preserve a short sanitized checkpoint in an approved local
location when needed, not a compulsory committed log.
