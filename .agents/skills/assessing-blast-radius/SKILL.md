---
name: assessing-blast-radius
description: "Traces downstream breakage beyond direct callers and executes load-bearing safety checks. Use for blast-radius questions, cross-module changes, shared preprocessing, and output-contract or tool-schema changes."
disable-model-invocation: true
license: MIT
metadata:
  upstream: https://github.com/cursor/plugins/tree/c47b12849e43f18d5c374c7069c744cc55b0ea00/pstack/skills/blast-radius
  upstream-revision: c47b12849e43f18d5c374c7069c744cc55b0ea00
---

# Assessing blast radius

Find the consequences a caller search misses, then test the facts safety depends on.

Read the [repository workflow](../reference/repository.md). Trace the harness
(loop, tools, sandbox runner, validator) separately from the converters it
produces. Consult `docs/spec.md` for the output contract, tool schemas, and run
directory, `contract/input_contract.py` for the pipeline input rules, and
`onboard/validate.py` for what decides a run's status. A shared helper's callers
are not the complete risk map.

1. Pin the exact diff or proposed change. Identify changed behavior, data shapes,
   error modes, ordering, fitting scope, and serialization contracts.
2. Follow actual consumers across imports, CLI/configuration, tool results,
   sandbox mounts, reports, manifests, plots, and downstream tools. Check dependency versions and
   authoritative source when a library's behavior is decisive.
3. Identify the load-bearing safety facts. A change may depend on several
   independent invariants; do not force everything into a single explanation.
4. Trace a concrete failure sequence for each material risk. Separate confirmed
   consequences, plausible untested risks, and checked/cleared cases. Do not
   invent likelihood percentages or callers.
5. Execute the cheapest meaningful check against real production code using
   independently synthetic data. Broaden to affected integration paths when
   necessary. Mark unproven facts explicitly; prose reasoning is not a test run.

For a conversion-rule change, check which samples and metabolites survive,
which values stay blank, and what the pipeline will do with the result. Verify
both scientific meaning and output compatibility. For example, a change in how
blank values are written can make the pipeline impute low values for samples
that were never measured, even though every check still passes.

Stay within a read-only review when that is the request. Tests may use disposable
local outputs, but do not implement fixes, publish findings, or change shared
state without authorization. Keep private-study-derived values, counts, names,
paths, and logs out of durable evidence and external messages.

Return the changed contract, material risks with source locations, the safety
facts proven by executed checks, cleared cases, and remaining verification.
Keep the report proportionate; a long risk list is not stronger evidence.
