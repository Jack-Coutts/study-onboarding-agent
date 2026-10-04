# Agent skills

Repository-specific adaptations of pstack and Matt Pocock workflows. They were
first written for the metabolomics pipeline these converters feed, and are
adapted here for the onboarding harness. These are portable Markdown instructions, not
plugins: they install no tools, start no MCP servers, and grant no permission
to publish or change shared state.

## Using the skills with any agent

Read `AGENTS.md` first, then the relevant `SKILL.md` below and its linked
[repository workflow](reference/repository.md). Paths in backticks are relative
to the repository root. Agents that support `.agents/skills/` can discover the
skills natively. Others can read the files directly; no Amp, Cursor, Claude,
particular model, or multi-agent facility is required.

For example, ask an agent to "Read
`.agents/skills/testing-scientific-code/SKILL.md` and use it for this change."
Ask for poteto-mode to apply the router, or unslop to apply the prose skill.
These are natural-language triggers, not guaranteed slash-command aliases.

## Skills

| Skill | Use it for |
| --- | --- |
| [applying-poteto-mode](applying-poteto-mode/SKILL.md) | An explicitly requested, evidence-first engineering workflow |
| [applying-ponytail-mode](applying-ponytail-mode/SKILL.md) | The smallest change that works, and reviewing changes for bloat, without cutting safety checks |
| [unslopping-writing](unslopping-writing/SKILL.md) | Plain, precise prose without losing technical meaning or uncertainty |
| [diagnosing-bugs](diagnosing-bugs/SKILL.md) | Minimal reproductions and hypothesis-driven debugging |
| [testing-scientific-code](testing-scientific-code/SKILL.md) | Test-first correctness, leakage invariants, and statistical validation |
| [refactoring-safely](refactoring-safely/SKILL.md) | Behavior-preserving structural changes with equivalence evidence |
| [assessing-blast-radius](assessing-blast-radius/SKILL.md) | Downstream scientific, integration, and output-contract risks |
| [designing-codebase-interfaces](designing-codebase-interfaces/SKILL.md) | Caller contracts, ownership, and consequential interface choices |
| [researching-scientific-decisions](researching-scientific-decisions/SKILL.md) | Primary-source evidence for methodological choices |
| [tracing-decisions](tracing-decisions/SKILL.md) | Historical rationale with calibrated confidence |
| [reviewing-scientific-code](reviewing-scientific-code/SKILL.md) | Local diffs, branches, and uncommitted changes (not GitHub PRs) |
| [documenting-decisions](documenting-decisions/SKILL.md) | Domain clarification and source-backed decision records |
| [planning-scientific-changes](planning-scientific-changes/SKILL.md) | Verifiable specifications and dependent implementation slices |

### Choosing a review skill

- **GitHub pull request** (number, URL, or automated review workflow):
  [reviewing-prs](reviewing-prs/SKILL.md) first. Optional follow-up:
  [reviewing-pr-simplicity](reviewing-pr-simplicity/SKILL.md).
- **Local branch, working tree, or non-PR diff:**
  [reviewing-scientific-code](reviewing-scientific-code/SKILL.md).

| Skill | Use it for |
| --- | --- |
| [reviewing-prs](reviewing-prs/SKILL.md) | Pinned PR reviews, safe test execution, and authorized review delivery |
| [reviewing-pr-simplicity](reviewing-pr-simplicity/SKILL.md) | A separate follow-up simplicity review after scientific feedback |

Each skill is independently usable. `applying-poteto-mode` routes to the others
when needed; it does not load the whole collection for every task or change the
agent's model. Skills are versioned with this repository, not installed into
anyone's global account. The gerund names describe the work each skill performs.

## Adaptation choices

- Repository guidance and permissions remain authoritative. External writes
  require explicit authorization; an overnight task is not permission to publish.
- Scientific claims need appropriate evidence, not merely a successful run.
  Small deterministic tests and multi-seed benchmarks answer different questions.
- Private study data and anything derived from it stays out of this repository
  and out of external messages. Durable examples use synthetic inputs or public
  deposits, as the data policy allows.
- Existing decision records, numerical tests, runtime guards, and accurate
  scientific explanations are preserved. There is no comment-deletion pass.
- Parallel agents and alternative designs are used only when they earn their
  cost and the current agent's tool rules allow them. There are no fixed workers
  or models; a single agent can perform every workflow.
- Prose rules preserve formulas, terminology, units, citations, and uncertainty.
  Punctuation is not a correctness gate.

The shared repository workflow points to the spec, decision records, data
policy, owners, and checks. Keep those project files authoritative rather
than treating a skill's description of them as a replacement.

## Sources and licenses

The thirteen new skills are edited adaptations, not verbatim upstream installations.
Their frontmatter records sources and pinned revisions. The existing PR workflows
record their own sources in their bodies.

- [pstack](https://github.com/cursor/plugins/tree/c47b12849e43f18d5c374c7069c744cc55b0ea00/pstack), by Lauren Tan.
- [Matt Pocock's skills](https://github.com/mattpocock/skills/tree/d81f3a183412e71a5b1e84ca21bc1a35eea03a60).
- [ponytail](https://github.com/DietrichGebert/ponytail/tree/c982cd411abb53323c4baa1baa3c2f020b8d0b08), by Dietrich Gebert.

All three sources use the MIT license. Their notices are retained in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## Validation

Run from this repository's root:

```bash
make skill-check
# or: uv run python .agents/skills/scripts/validate_skills.py
```

The validator checks frontmatter, names, descriptions, bundled Markdown links,
README coverage, and the instructions-only packaging contract. It does not
prove an agent will follow the instructions or validate scientific methods.
