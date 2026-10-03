---
name: diagnosing-bugs
description: "Builds minimal reproductions and tests falsifiable hypotheses for bugs or performance regressions. Use when debugging failures, wrong numerical results, flaky behavior, or slow commands."
disable-model-invocation: true
license: MIT
metadata:
  upstream: https://github.com/mattpocock/skills/tree/d81f3a183412e71a5b1e84ca21bc1a35eea03a60/skills/engineering/diagnosing-bugs
  upstream-revision: d81f3a183412e71a5b1e84ca21bc1a35eea03a60
---

# Diagnosing bugs

Establish a failure-specific feedback loop before claiming a cause.

Read the [repository workflow](../reference/repository.md). Start with the
affected test under `tests/`, a `uv run onboard ...` command against a dev
fixture, or `onboard replay` on a recorded run, which reaches the loop without
API calls. Generated code only runs through `onboard/sandbox.py`.

1. Read governing guidance, scientific decisions, and the reported code path.
   Separate the observed symptom from the user's proposed explanation.
2. Run a test or command that reaches the actual failure and asserts the specific
   wrong result. Prefer existing harnesses and independently synthetic fixtures.
   Pin seeds, configuration, and temporary outputs when helpful. If reproduction
   is unavailable, state what is missing and keep explanations as hypotheses.
3. Minimize the scenario one variable at a time, retaining the failure. Do not
   remove an important design factor just to make a scientific case simpler.
4. Rank plausible competing hypotheses and name the prediction that distinguishes
   each. Use as many as the evidence warrants, not a compulsory count.
5. Probe those predictions with targeted inspection or instrumentation. For a
   sandbox failure, check the mounted inputs and the container's real error.
   For a performance issue, measure a reproducible baseline before optimizing.
6. Turn the failing reproduction into a regression test at a surface that exposes
   the actual mechanism. Confirm failure for the intended reason, apply the
   smallest fix, rerun the test, and rerun the original scenario.
7. Run affected neighboring checks. Remove temporary instrumentation and scratch
   artifacts. Report the verified mechanism, evidence, and remaining uncertainty.

## Numerical and scientific failures

- Derive expectations from a worked example, specified invariant, analytic result,
  or trusted independent implementation. Old/new agreement is not a correctness
  oracle, though it can help localize a regression.
- Use the fastest deterministic loop available, plus slower integration or
  multi-seed statistical confirmation where necessary. A minutes-long reference
  fit is acceptable when seconds cannot establish the relevant fact.
- Check alignment, dtype/coercion, missingness, scale, contrast direction, and
  which rows each learned transform sees. Do not explain a failing AUC or p-value
  without verifying the implicated split, design, and data path were present.
- For flaky failures, report the reproduction rate and trial conditions rather
  than claiming deterministic proof from one lucky run.

Follow the project data policy. Never commit private payloads, measurements,
derived counts/metrics, paths, or names as a reproduction. Construct an
independently synthetic case; anonymization alone is insufficient. Keep private
diagnostics local and out of external prompts/messages. A debug request does
not authorize production instrumentation, remote writes, or publication.
