---
name: unslopping-writing
description: "Edits prose into plain, precise writing while preserving technical meaning and uncertainty. Use for unslop requests, documentation, reports, agent instructions, and verbose replies."
license: MIT
metadata:
  upstream: https://github.com/cursor/plugins/tree/c47b12849e43f18d5c374c7069c744cc55b0ea00/pstack/skills/unslop
  upstream-revision: c47b12849e43f18d5c374c7069c744cc55b0ea00
---

# Unslopping writing

Write plainly. Remove empty language without changing the claim.

Read the [repository workflow](../reference/repository.md). Apply this to the
README, the spec, decision pages, agent instructions, evaluation reports,
and user-facing summaries. Keep the decision pages' established structure
intact.

## Process

1. Identify the audience, purpose, and facts the text must preserve. For an edit,
   preserve the author's intended meaning rather than adding a new argument.
2. Replace filler, vague attribution, rhetorical flourishes, and abstract praise
   with concrete statements. Name a source when one exists; never invent one.
3. Split sentences that require backtracking. Prefer active voice and ordinary
   words. Use complete sentences, not missing articles or symbol shorthand.
4. Keep consistent names. Avoid synonym cycling, forced groups of three,
   unnecessary bold labels, decorative emojis, and generic closing sentences.
5. Check that the edit preserves numbers, signs, units, formulas, citations,
   scope, assumptions, limitations, and confidence. Then deliver the text.

## Scientific and technical exceptions

- Keep precise terms such as vector, significance, bias, and calibration when
  they carry their technical meaning. Remove metaphorical jargon, not concepts.
- Remove stacked hedges, not warranted uncertainty. "May be biased when batches
  separate outcomes" must not become an unconditional "is biased".
- A result is measured only when the evidence supports it. Do not turn a
  prediction, interpretation, association, or hypothesis into a causal fact.
- Preserve accurate scientific why-comments and citations. Shortening prose is
  not permission to remove reasoning that code cannot express.
- Use punctuation and parentheses when they improve clarity. Prefer sentence
  case headings, but respect publication and repository style requirements.

## Examples

- "This robust framework ensures seamless preprocessing" becomes
  "Each training fold fits its own imputer and scaler", if the code does so.
- "Could potentially possibly affect calibration" becomes "May affect
  calibration", not "Breaks calibration".
- "Parser rejects date → exit 2, no write" becomes "The parser rejects the date,
  exits with code 2, and writes no output."

Apply the repository's privacy policy before quoting results or logs. A request
to improve wording does not authorize publishing the text or inspecting private
data. State a material factual gap instead of disguising it with fluent prose.
