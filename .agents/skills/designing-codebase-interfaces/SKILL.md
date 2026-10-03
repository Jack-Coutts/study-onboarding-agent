---
name: designing-codebase-interfaces
description: "Designs caller contracts and ownership boundaries with simple, testable interfaces. Use for codebase-design requests, consequential API choices, shared analysis interfaces, or architecture improvement."
disable-model-invocation: true
license: MIT
metadata:
  upstream: https://github.com/mattpocock/skills/tree/d81f3a183412e71a5b1e84ca21bc1a35eea03a60/skills/engineering/codebase-design
  upstream-revision: d81f3a183412e71a5b1e84ca21bc1a35eea03a60
---

# Designing codebase interfaces

Reduce what callers must know while keeping important domain distinctions explicit.

Read the [repository workflow](../reference/repository.md) and
`docs/spec.md`. Ground designs in the existing output contract, tool schemas,
sandbox runner, validator, and run manifest. Inspect the actual owner rather
than creating a parallel API. The `onboard` commands remain the supported entry
points.

1. Read the code that owns the behavior and representative callers. Identify
   their actual needs, invariants, and present failure modes before proposing
   a type, wrapper, adapter, or framework.
2. Write a caller usage sketch and contract. Include configuration, ordering,
   mutation, errors, units/scale, missingness, alignment, learning scope,
   reproducibility, and performance where relevant, not just a signature.
3. Check whether the source of truth can be changed directly. Prefer existing
   abstractions and helpers; a new seam needs a real variation or responsibility.
4. For a consequential unresolved choice, compare genuinely different designs
   against caller burden, locality, scientific clarity, testability, and migration
   cost. Use concrete scenarios or a small safe experiment when it can decide
   a fact. Routine function changes do not require parallel design agents.
5. Recommend the smallest sufficient design, its trade-offs, verification, and
   migration plan. Implement only when implementation is within the request.

## Scientific boundaries

Python types do not establish DataFrame shape, numeric finiteness, design rank,
or sample/feature alignment. Validate required numerical invariants at callable
analysis boundaries and where transformations introduce new requirements.
Prefer pure calculations where practical, but keep necessary I/O ownership clear.

Do not hide observed versus imputed data, raw versus log scale, fit versus
transform, or train versus held-out rows behind a smaller but ambiguous interface.
Preserve useful numerical functions and their tests. Fewer public methods or
fewer files are not improvements unless they reduce real caller/maintainer work.

Respect existing domain vocabulary and decision records. Use API, boundary,
interface, or module when each is accurate; do not impose a terminology ban.
Keep scientific rationale and meaningful guards. A larger architecture proposal
is not permission for an unrelated cleanup or a new documentation system.
