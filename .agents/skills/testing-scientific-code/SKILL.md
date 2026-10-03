---
name: testing-scientific-code
description: "Uses test-first development and independent oracles for scientific code. Use for TDD, numerical regression fixes, preprocessing or validation changes, and statistical benchmark design."
disable-model-invocation: true
license: MIT
metadata:
  upstream: https://github.com/mattpocock/skills/tree/d81f3a183412e71a5b1e84ca21bc1a35eea03a60/skills/engineering/tdd
  upstream-revision: d81f3a183412e71a5b1e84ca21bc1a35eea03a60
---

# Testing scientific code

Write tests that distinguish plausible wrong implementations from the contract.

Read the [repository workflow](../reference/repository.md). Follow the existing
pytest patterns under `tests/`: fixtures for run directories, the fake model
client, and the sandbox; `pytest.mark.parametrize` over fixtures and broken
variants. Shared helpers and Docker availability handling live in
`tests/conftest.py`. Use `uv run pytest <test-path>` for the red/green loop.

## Before the first test

Read repository guidance, relevant scientific decisions, and nearby tests.
Identify the risky behavior and the narrowest useful test surface. Use existing
interfaces and pytest conventions. State consequential assumptions; choose
routine test surfaces yourself rather than asking permission for every test.

For each subtle rule, name a plausible mistake and choose an input where it
changes the answer. Favor asymmetric groups, unequal spacing, reordered IDs,
both sides of thresholds, and deliberately distinct training/test distributions.

## Red, green, then safe refactoring

1. Derive the expected value independently from the specification, a worked
   example, known generating truth, an analytic identity, or a trusted reference.
   Do not obtain expectations by copying the implementation's own calculation.
2. Write one focused test. Run it before the behavior change and confirm that
   it fails because of the intended missing or wrong behavior, not bad setup.
3. Make the smallest correct implementation change. Run the test and relevant
   neighboring checks. Never weaken the expectation just to obtain green.
4. Repeat for the next meaningful behavior. Refactor only against passing
   behavior pins; keep scientific method changes separate from structural edits.

## Use the right evidence layer

- **Deterministic correctness:** finite worked examples, input rejection,
  row/column alignment, units, contrast signs, schemas, and boundary cases.
  Set numerical tolerances from the method's precision requirements, not the
  observed discrepancy. Do not require exact bits where approximation is intended.
- **Learning-scope invariants:** assert subject separation and fit membership,
  not merely headline performance. In fold-local workflows, imputation, scaling,
  clustering, feature selection, and tuning must see only permitted rows.
  Honor documented exceptions for transforms learned solely from independent QCs.
  Targeted instrumentation is valid when output scores cannot expose leakage.
- **Integration:** exercise real entry points and real sandbox execution
  using safe synthetic inputs. Mock unavailable-process and error paths, but
  retain real Docker-gated tests. Report skips and unverified integration explicitly.
- **Statistical validity:** use known null and signal regimes across seeds,
  uncertainty intervals, and relevant sensitivity cases. Evaluate calibration,
  false discoveries, power, effect error, exclusions, and aborts as appropriate.
  Freeze the protocol before comparing; do not tune against the evaluation set.

Use metamorphic or property tests when their relationships are scientifically
justified. If fuzzing is requested, generate accepted inputs that exercise the
risky transformation, not mostly invalid cases that test only rejection.

Preserve useful kernel and statistical tests even if higher-level coverage is
added. Remove a test only after its guarantee is demonstrably redundant or no
longer required. "Did not crash" and a green linter do not prove correct results.
Durable fixtures and evidence must be independently synthetic or otherwise
permitted by the project policy, never private-study-derived.
