---
name: planning-scientific-changes
description: "Turns substantial scientific changes into a scoped specification and verifiable dependent slices. Use for to-spec or to-tickets requests, input migrations, analysis extensions, and multi-step implementation plans."
disable-model-invocation: true
license: MIT
metadata:
  upstream: https://github.com/mattpocock/skills/tree/d81f3a183412e71a5b1e84ca21bc1a35eea03a60/skills/engineering/to-tickets
  upstream-spec: https://github.com/mattpocock/skills/tree/d81f3a183412e71a5b1e84ca21bc1a35eea03a60/skills/engineering/to-spec
  upstream-revision: d81f3a183412e71a5b1e84ca21bc1a35eea03a60
---

# Planning scientific changes

Produce a plan whose slices can be independently verified without hiding scientific risk.

Read the [repository workflow](../reference/repository.md),
`docs/spec.md`, and matching decision pages. Use `tmp/` (git-ignored) when a
local plan is useful. For contract work, read the output contract in the spec
and inspect which code actually applies it. Do not assume that a specified
behaviour has landed.

1. Read the request, owning code, existing plans/issues, guidance, and relevant
   scientific decisions. Separate accepted choices from unresolved facts and
   genuine human decisions. A planning request does not authorize implementation.
2. Synthesize a compact specification: problem and intended result, current and
   proposed contracts, assumptions, scientific invariants, compatibility,
   acceptance criteria, verification, and out-of-scope work. Prefer useful detail
   over a mandatory long list of user stories.
3. Settle the riskiest factual uncertainty with inspection or a safe local
   experiment when within scope. Label experiments and proposed checks distinctly
   from executed evidence. Ask only for essential unresolved user decisions.
4. Divide substantial work into coherent, verifiable slices. For a pipeline,
   a slice can span input/config, scientific transformation, CLI/report, and
   synthetic verification. Do not force every slice to touch every layer.
5. Name genuine blocking dependencies and shared write targets. Scientific
   coupling matters even if files differ. Prefer sequential implementation when
   invariants cross the workstreams; parallelize only independently owned work.
6. Include decision updates and integration verification in the slice that changes
   the contract. Put prerequisite refactoring first only when it removes a real
   obstacle, and pin behavior before it. Use an explicit migration for public
   contracts rather than blindly removing old forms.
7. Present or save a sanitized local draft using existing conventions. Publish
   tickets, apply labels, assign work, or update/close issues only when explicitly
   authorized. Confirm the destination and exact content if authorization is
   unclear. Never invent tracker labels or treat a local folder as privacy-safe.

## Slice template

- Outcome: the behavior this slice delivers.
- Blocked by: only prerequisites that genuinely gate it.
- Contract: data, scientific, and compatibility rules that change or remain fixed.
- Acceptance: observable criteria that distinguish wrong implementations.
- Verification: targeted tests, real sandbox execution, and evaluation runs needed.
- Documentation: the existing decision records affected.
- Scope exclusions: work this slice deliberately does not do.

Durable plans contain no private-study-derived measurements, names, identifiers,
counts, metrics, or paths. Preserve public/synthetic evidence citations and source
locations where needed for auditability. Do not substitute tracker decisions for
canonical scientific records or add a mandatory workflow configuration system.
