---
name: researching-scientific-decisions
description: "Evaluates primary-source evidence for methodological choices and their limits. Use when researching statistical methods, scientific assumptions, library behavior, or proposed analysis defaults."
disable-model-invocation: true
license: MIT
metadata:
  upstream: https://github.com/mattpocock/skills/tree/d81f3a183412e71a5b1e84ca21bc1a35eea03a60/skills/engineering/research
  upstream-revision: d81f3a183412e71a5b1e84ca21bc1a35eea03a60
---

# Researching scientific decisions

Answer the methodological question with traceable evidence and visible limits.

Read the [repository workflow](../reference/repository.md) and the matching
page in `docs/decisions/`. Start from its references and committed evidence.
For conversion rules, compare the deposit documentation with the reference
converter in `reference/`; for evaluation design, read the evaluation sections
of `docs/spec.md` and the held-out fixtures.

1. Define the decision, estimand or intended result, assumptions, and alternatives.
   Read the existing decision record and relevant implementation/tests first.
   Check the user's premise rather than assuming it is correct.
2. Use primary papers, official documentation, authoritative source code, and
   committed synthetic benchmarks. Use search to locate evidence, not as a
   substitute for reading the source that supports the claim.
3. Match each source to the actual setting: data scale, outcome/design, sample
   dependence, missingness, batch/order structure, validation, and metric.
   Distinguish results the paper tested from extrapolations it does not support.
4. Look for contradictory evidence and competing interpretations. Read complete
   methods/tables when checking numerical or methodological claims; excerpts
   can omit the qualifications that change the conclusion.
5. Separate published support, implementation behavior, and empirical validity
   under a simulation's assumptions. Propose a synthetic benchmark for unresolved
   operational questions; do not claim to have executed it unless you did.
6. Return a recommendation with adjacent citations, assumptions, limitations,
   alternatives, and what would change the decision. State unknowns plainly.

Do not optimize scientific defaults against a repeatedly inspected held-out set
or headline AUC/discovery count. Define relevant validity criteria before
comparison and preserve calibration alongside power and error as appropriate.

Work directly unless useful bounded research satisfies the current tool's
delegation rules. Do not require a background agent. Every worker receives the
same privacy and evidence constraints; synthesized agreement is not replication.

A research request is read-only by default. Save notes only when requested or
needed for an authorized documentation change, using existing conventions.
Never store private-study-derived names, values, counts, metrics, or paths in
durable notes or send them to external sources. Public evidence is eligible only
when allowed by the repository policy. Update accepted decisions only when the
decision change is authorized, not merely because research found an alternative.
