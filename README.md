# study-onboarding-agent

Can a coding agent safely write the code that brings a new public
metabolomics study into an analysis pipeline?

## Why this exists

My metabolomics analysis pipeline reads one input layout. Public deposits
never arrive in it. Each one names samples differently, marks QC and blank
injections in its own way, splits measurements across several analyses, and
records batch and run order only some of the time. So every new study needs a
small converter, and I have written several by hand.

Those converters look simple and are not. Most of the bugs I have fixed in
them were silent: an identifier read as a number, a sample that was never
measured treated as below the detection limit, a batch column filled in when
the deposit had none. Each produced a plausible table and a wrong analysis.

This repository tests whether an agent can write the next converter, and what
it takes to trust the result. The agent never grades its own work. It writes a
converter and its tests; a harness runs them in a sandbox with no network and
no credentials, checks the output against rules the agent cannot edit, and
lets the agent repair failures a limited number of times. An accepted
converter is ordinary code, so it re-runs later without a model.

The evaluation reuses what I already have. Studies I converted by hand give
expected outputs, and the bugs I fixed in those converters become deliberately
broken versions that the agent's tests have to catch.

## Status

The harness is built and tested against a scripted model client and the real
Docker sandbox. No live model run or evaluation has happened yet, so there are
no results to report. What is still missing (spec section 22):

- Real studies R1-R3 have not been chosen or frozen (`tasks/`).
- The reference converter was written from the spec here, because the
  pipeline's own converter is not in this repository. It should be compared
  with the pipeline's converter on R1-R3 before results that depend on it are
  trusted.
- No live run has ended `passed`, so `onboard rerun` and the injection report
  have only been exercised on scripted runs.

## Data

Only public deposits are used. See [docs/data_policy.md](docs/data_policy.md).

## What is here

- [docs/spec.md](docs/spec.md): what is built and how it is judged.
- [docs/decisions/](docs/decisions/index.md): conversion rules carried over from
  the hand-written converters, with their reasons.
- `onboard/`: the harness. It holds the agent loop, tools, sandbox runner,
  validator, manifests, re-runs, and evaluation.
- `contract/`: the pipeline's input rules, checked on a converter's output.
- `reference/`: the reference converter and eight broken variants, each with
  one mistake a real converter has made.
- `fixtures/`: synthetic deposits. Dev fixtures' expected outputs are shown to
  the agent; held-out ones are not.
- `sandbox/`: the container image and the isolation probe.
- `prompts/`: the system prompt and the task prompt, which states the output
  contract the agent is judged against.
- [.agents/skills/](.agents/skills/README.md): workflow instructions for coding
  agents working on this repository, adapted from the pipeline's own.
- [.amp/plugins/](.amp/plugins/pr-review.md): a review workflow that runs when a
  pull request is labelled `ready for review`.

## Running it

Needs Docker, and an Anthropic API key for live runs.

```bash
uv run onboard check-sandbox --build   # build the image, record its ID, run the probe
uv run onboard fetch ST000123          # freeze a public deposit into data/raw/
uv run onboard run fixtures/dev/D1/task.yaml   # one agent run on a dev-shaped task
uv run onboard rerun runs/<run-id>     # re-run the accepted converter, no model call
uv run onboard replay runs/<run-id>    # re-drive a run from its log, no API calls
uv run onboard eval                    # runs on tasks/R*.yaml plus hidden checks
```

A live run with Claude Opus 5.5 costs roughly $0.50-$1.50 at the default
limits in `config.yaml`. For cheap trial runs, DeepSeek's models work through
their Anthropic-compatible API, with their own key:

```bash
export DEEPSEEK_API_KEY=...
uv run onboard run fixtures/dev/D1/task.yaml --model deepseek-flash
```

Results from another provider measure that provider's model, not Claude, so
keep them apart from Claude runs when reporting.
Each run writes `runs/<run-id>/` with the manifest, log, every version, and a
report. A passed run is also copied to `studies/<ST>/`.

## Development

Needs [uv](https://docs.astral.sh/uv/). Webhook tests also need
[Bun](https://bun.sh).

```bash
make setup          # uv sync
make hooks          # run ruff before every commit
make check          # ruff, mypy, skill check, pytest
make docker-tests   # sandbox tests; `make check` skips them without Docker
make webhook-tests  # Bun tests for the review webhook
```

CI runs the same checks on every push to `main` and on every pull request, with
the sandbox tests in a separate job. Tests use a scripted model client, so CI
needs no API key.
