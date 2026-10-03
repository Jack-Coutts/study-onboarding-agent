---
name: tracing-decisions
description: "Reconstructs historical rationale from decision records, Git, and related discussions with calibrated confidence. Use for why questions, threshold origins, rejected alternatives, or regression history."
disable-model-invocation: true
license: MIT
metadata:
  upstream: https://github.com/cursor/plugins/tree/c47b12849e43f18d5c374c7069c744cc55b0ea00/pstack/skills/why
  upstream-revision: c47b12849e43f18d5c374c7069c744cc55b0ea00
---

# Tracing decisions

Explain the recorded rationale without inventing author intent from current code.

Read the [repository workflow](../reference/repository.md). Begin with
`docs/decisions/index.md` and the relevant page's cited tests, sources, and PRs.
Check `git rev-parse --is-shallow-repository`; if true, fetch full history with
`git fetch --quiet --unshallow origin` before Git history analysis. If unavailable,
report incomplete history rather than interpreting missing evidence as intent.

1. Anchor the question in the relevant symbols, source locations, and present
   behavior. Read the matching decision page, tests, benchmarks, and comments.
2. Inspect focused Git history, including patches and renames. Check shallow
   history and follow the environment's fetch rules before drawing conclusions
   from missing commits. Read substantive PR/issue discussion when relevant.
   If a commit links an agent conversation and the current agent can access it,
   read it when pertinent. Otherwise report that evidence as unavailable.
3. Expand to other sources only when a concrete gap warrants it and access is
   authorized. Do not sweep chat, observability, and warehouses by default.
   Connected tools are capabilities, not permission to expose private content.
4. Reconcile chronology and contradictions. A recent cleanup message may not
   explain the original method. The currently documented decision may supersede
   historical rationale; present that distinction rather than choosing a tidy story.
5. Report the answer, adjacent citations, confidence, relevant rejected
   alternatives, and what remains unknown. If a change is being considered,
   identify what to preserve, change, avoid, and verify without implementing it.

## Confidence

- **Direct:** a source explicitly states the rationale. Cite its actual text.
- **Supported:** multiple indirect sources converge. Show the inference chain.
- **Inferred:** a reasonable interpretation without explicit supporting rationale.
  Label it as an interpretation.
- **Speculative:** several explanations fit the limited evidence. Name the
  hypothesis and missing evidence.
- **Unknown:** the searched sources did not answer the question. Say which
  relevant sources were checked, without inventing coverage.

Code establishes what happens, not why someone chose it. A commit establishes
what changed, not necessarily that the change worked or was scientifically sound.
Do not turn absence of recorded objections into proof of validity. Preserve
conflicting evidence and the distinction between historical intent and present
scientific support. Keep private identifiers, metrics, paths, names, and content
out of externally shared answers; use permitted citations and safe summaries.
