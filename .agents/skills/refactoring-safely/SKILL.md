---
name: refactoring-safely
description: "Preserves behavior while changing code structure and proves equivalence. Use for refactors, shared-helper migrations, deduplication, module moves, and scientific pipeline restructuring."
disable-model-invocation: true
license: MIT
metadata:
  upstream: https://github.com/cursor/plugins/blob/c47b12849e43f18d5c374c7069c744cc55b0ea00/pstack/skills/poteto-mode/playbooks/refactoring.md
  upstream-revision: c47b12849e43f18d5c374c7069c744cc55b0ea00
---

# Refactoring safely

Change structure while holding the observable contract fixed.

Read the [repository workflow](../reference/repository.md) and
`docs/spec.md`. The harness already has owners: model calls in
`onboard/model_client.py`, tool handling in `onboard/tools.py`, execution in
`onboard/sandbox.py`, and judgement in `onboard/validate.py`. Inspect them
before extracting another layer. For contract changes, pin
`contract/input_contract.py` and its tests.

1. Read the owning code, callers, guidance, and scientific decisions. Name what
   must remain unchanged and the concrete complexity the refactor removes.
2. Run existing coverage before moving code. Add a characterization test or
   equivalence harness for uncovered behavior. Lint and types are not behavior
   pins. Keep baseline results safe and synthetic.
3. State the target ownership and data shape. Reuse existing helpers; do not add
   indirection simply to rename complexity. Explore alternatives only when a
   consequential design remains unsettled.
4. Move in small steps, rerunning the pins. Follow references in strings,
   registries, configuration, documentation, and serialized outputs as well as
   imports. Keep unrelated fixes and behavior changes outside the refactor.
5. Compare actual old/new results where the change warrants it. Normalize only
   irrelevant nondeterminism such as timestamps or temporary directory names.
   Explain any numerical tolerance independently of the observed difference.
6. Run affected integration paths and broader checks. Report the structural
   improvement, unchanged contract, equivalence evidence, and verification gaps.

## Scientific behavior pins

When relevant, preserve retained samples/features and their order, exact ID
semantics, zero/missing handling, data scale, contrast direction, positive class,
grouped split membership, fold-local fitting, numerical results, warnings,
CLI/config behavior, output schemas, and manifest meaning. Seeded algorithms
can change when row order changes; do not dismiss that as cosmetic.

A known bug discovered during characterization remains a separate behavior
change. Do not make the existing implementation the oracle for scientific
correctness; use equivalence only to prove the structural change preserved it.

## Deletion and compatibility

Delete genuinely obsolete internal paths after migrating all internal consumers.
Preserve supported external CLI/config/output contracts unless the user requested
their removal. Use an explicit migration when atomic replacement cannot stay
verifiable. Keep meaningful numerical guards, citations, and scientific
why-comments. Do not erase them under a blanket "internal code is trusted" rule.

Respect other worktree changes. A refactor does not authorize history rewriting,
discarding someone else's edits, automatic commits, pushes, or opening a PR.
