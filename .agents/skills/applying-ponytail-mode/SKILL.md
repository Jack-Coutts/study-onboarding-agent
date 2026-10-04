---
name: applying-ponytail-mode
description: "Builds the smallest change that works: question whether code needs to exist, reuse what is here, prefer the standard library, delete before adding. Use when asked for ponytail, lazy mode, the simplest or minimal solution, or when reviewing a change for bloat. Never simplifies away the harness's judging code or safety checks."
disable-model-invocation: true
license: MIT
metadata:
  upstream: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/skills/ponytail/SKILL.md
  upstream-rule: https://github.com/DietrichGebert/ponytail/blob/c982cd411abb53323c4baa1baa3c2f020b8d0b08/.agents/rules/ponytail.md
  upstream-revision: c982cd411abb53323c4baa1baa3c2f020b8d0b08
---

# Applying ponytail mode

Work like a lazy senior developer: lazy means efficient, not careless. The best
code is the code never written.

Read the [repository workflow](../reference/repository.md) first. Understand
the problem before shortening the solution: read the task and the code it
touches, and trace the real flow end to end. A small diff in the wrong place is
a second bug.

## The ladder

Stop at the first rung that holds:

1. **Does this need to exist?** If the need is speculative, skip it and say so
   in one line.
2. **Is it already here?** Reuse the helper, type, or pattern that already
   lives in `onboard/`, `contract/`, or `tests/fakes.py`.
3. **Does the standard library do it?** Use it.
4. **Does an installed dependency solve it?** Use it. Do not add a dependency
   for what a few lines can do.
5. **Can it be one line?** Make it one line.
6. **Only then** write the minimum code that works.

A bug report names a symptom. Before editing, find every caller of the function
you are about to touch and fix the shared function once.

## Rules

- No abstraction nobody asked for: no interface with one implementation, no
  factory for one product, no config for a value that never changes.
- No scaffolding "for later". Deletion over addition; boring over clever.
- Fewest files, shortest working diff, once you understand the problem.
- Question a complex request in the same reply that ships the simple version:
  "Did X; Y covers it. Need the full X? Say so."
- When two standard-library options are the same size, take the one that is
  correct on edge cases.
- Mark a deliberate shortcut with a known ceiling with a `ponytail:` comment
  that names the ceiling and the upgrade path.
- Non-trivial logic leaves one runnable check behind: the smallest test that
  fails if the logic breaks. Follow
  [testing-scientific-code](../testing-scientific-code/SKILL.md) for what that
  test must distinguish.

## Never simplify away

These look like duplication or defensiveness but carry this repository's
guarantees:

- The contract checker re-reads the deposit instead of reusing the reference
  converter's parsing. The independence is the point.
- The validator, reference converter, broken variants, and held-out expected
  outputs decide whether the agent succeeded. AGENTS.md requires a separate
  justification for any change to them.
- Sandbox flags, output collection that refuses links, credential handling,
  and checks that keep held-out data from the model.
- Scientific guards: identifier handling, blanks versus zeros, conflicting
  records, and the rules in `docs/decisions/`.
- Input validation at trust boundaries, and error handling that prevents
  silent data loss.

If the user insists on the full version, build it without re-arguing.

## Output

Code first, then at most three short lines on what was skipped and when to add
it. An explanation the user asked for is not bloat; give it in full. When
reviewing for bloat, name each finding with its file and lines, the evidence
that nothing needs it, and the coverage that must remain, as
[reviewing-pr-simplicity](../reviewing-pr-simplicity/SKILL.md) describes.
