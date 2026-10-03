---
name: documenting-decisions
description: "Clarifies domain terms and records source-backed decisions in the project's existing documentation. Use for grill-with-docs requests, scientific decision updates, terminology disputes, or rationale documentation."
disable-model-invocation: true
license: MIT
metadata:
  upstream: https://github.com/mattpocock/skills/tree/d81f3a183412e71a5b1e84ca21bc1a35eea03a60/skills/engineering/domain-modeling
  upstream-revision: d81f3a183412e71a5b1e84ca21bc1a35eea03a60
---

# Documenting decisions

Clarify the model and preserve the rationale in the existing source of truth.

Read the [repository workflow](../reference/repository.md). The source of truth
is `docs/decisions/`, not a new ADR directory. Follow the matching page's status,
decision, why, rejected alternatives, limits, revisit conditions, and references.
Use `docs/decisions/index.md` to find the owner of a scientific choice.

1. Read the current domain documentation, scientific decisions, guidance, and
   relevant code. Distinguish an overloaded term from a factual contradiction
   or an unresolved choice. Inspect facts yourself rather than interviewing
   the user about observable behavior.
2. Stress-test unclear distinctions with concrete safe scenarios. Examples
   include sample versus subject, observed versus imputed, raw versus log scale,
   fit versus apply, reference versus positive class, and inner versus outer fold.
3. For an explicit grilling request, ask focused rounds of prerequisite-ready
   questions, each with a recommendation and trade-off. Wait for answers to
   genuine user decisions; avoid a compulsory exhaustive interview for routine
   documentation work. Do not treat an interview as authorization to implement.
4. Update the existing record when the documentation/decision change is within
   scope. Preserve its format. Do not create `docs/adr/` or a glossary alongside
   an established decision system merely to satisfy this skill's conventions.
5. State status, decision, scientific assumptions, evidence, rejected alternatives,
   limits, and revisit conditions as the project requires. Preserve traceable
   file/test/benchmark references even if other planning templates avoid paths.
6. Run the repository's documentation/decision checker when applicable and report
   its actual result. Inspect scientific claims separately from link consistency.

In this repository, decision pages live in `docs/decisions/`. There is no
checker yet, so check their links and references by hand. Read the matching
page before changing the rule, and update it in the same change when the
decision changes. Do not apply the upstream rule that
only hard-to-reverse decisions deserve a record: reversible scientific defaults
can still materially alter inference.

If a glossary is useful, keep definitions generic and domain-focused. Capture
implementation detail and evidence in the owning document, not a glossary.
Never write private study/outcome names, measurements, derived counts/metrics,
or paths into durable docs. Use synthetic examples and policy-permitted public
sources. Preserve honest uncertainty and do not manufacture historical rationale
for a decision that lacks one. Publish or send questions externally only with
explicit authorization for the destination and content.
