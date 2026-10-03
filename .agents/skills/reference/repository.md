# Repository workflow

These skills are adapted for this repository: a harness that has an agent
write converters for public metabolomics deposits and checks them outside the
agent's reach. Re-read the current project files; they override this
orientation. Paths in backticks are relative to the repository root. Any agent
with file and shell access can follow the instructions.

## Read before changing behaviour

Read `AGENTS.md`, `docs/spec.md`, `docs/data_policy.md`, and the matching page
indexed by `docs/decisions/index.md`. Do not create a competing decision
hierarchy or glossary.

Two kinds of code live here and need different care:

- **The harness** (`onboard/`, `contract/`, `sandbox/`): the loop, tools,
  sandbox runner, validator, and contract checker. Their job is to decide
  whether the agent under test succeeded, so a change that makes runs pass
  more easily needs evidence that it is correct, not just convenient.
- **Converters** (`reference/`, `studies/`): code that turns a deposit into
  pipeline input. The reference converter and its broken variants are the
  evaluation's ground truth; change them only with a reason recorded in the PR.

Held-out expected outputs must never reach the agent under test. Check any
change to tool results, prompts, or logging for that leak.

## Verification

Inspect `Makefile` for the current recipes. `make check` runs ruff, mypy, the
skill check, and pytest. Target pytest tests first, then broaden.

Tests use synthetic fixtures and a fake model client. Docker-backed tests skip
when Docker is unavailable, so report actual sandbox coverage explicitly rather
than inferring it from a green suite. Webhook tests need Bun
(`make webhook-tests`).

Live model runs cost money. Do not start one as part of a review or test run
unless asked.

## Privacy

Never commit private study data or anything derived from it. Public deposits
are frozen under `data/raw/` (git-ignored); only their sources and hashes are
committed. Credential redaction alone is not enough: keep API keys out of logs,
run directories, and anything that reaches the sandbox.
