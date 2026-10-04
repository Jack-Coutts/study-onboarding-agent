# study-onboarding-agent

[![CI](https://github.com/Jack-Coutts/study-onboarding-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Jack-Coutts/study-onboarding-agent/actions/workflows/ci.yml)

![How it works, in two lanes. The harness freezes the public study and your task file and gives them to the AI agent. The agent (1) reads the study, treating its text as data, and (2) writes a converter plus its own tests. The harness (3) checks them in a sandbox with no internet or keys, against the table rules, practice data, and the agent's tests, and sends feedback; the agent can fix and resubmit, up to 4 versions in total. The harness then (4) gives the verdict: pass, needs review, or fail. If it passed, (5) a hidden evaluation, never shown to the AI, follows. Every run is recorded, and an accepted converter re-runs without AI to identical output.](docs/figures/how-it-works.png)

<sub>Figure source: `docs/figures/how-it-works.html`. To redraw it, run
`uv run --with pillow python docs/figures/render_how_it_works.py` (needs Google
Chrome).</sub>

Can an AI coding agent safely write the code that brings a new public
metabolomics study into an analysis pipeline, and how would you know if it got
it wrong?

This repository is a test harness for that question. An agent writes a data
converter and its tests. The harness runs them in an isolated sandbox, judges
the result with checks the agent cannot see or change, and records everything
needed to reproduce the outcome without the model.

## The problem

Public metabolomics studies, such as those on
[Metabolomics Workbench](https://www.metabolomicsworkbench.org), arrive in many
shapes. Each names samples differently, marks quality-control and blank samples
in its own way, splits measurements across several analyses, and records batch
and run order only some of the time. An analysis pipeline expects one fixed
layout, so every new study needs a small converter.

Converters look simple and are not. The mistakes that matter are silent: the
converter runs and produces a plausible table, but the analysis it feeds is
wrong. For example:

- sample `01` is read as a number and becomes `1`, merging two samples;
- a sample that was never measured is written as blank, which the pipeline
  treats as "below the detection limit";
- a batch column is filled in when the study recorded no batches;
- two conflicting records for one sample are resolved by picking one.

## Before and after

This is what a converter does, shown on the practice study D1 (synthetic) with
the converter the agent wrote in a test run.

**Before.** The study, as deposited. Each sample's details are packed into one
line of text, and measurements are stored one metabolite at a time; they are
shown here per sample.

| Sample | Factors (as written) | Alanine | Glucose | *(no name; reference name Lactic acid)* |
|---|---|---|---|---|
| S01 | `Group:case \| Sample type:Sample \| Batch:1 \| Injection order:3 \| Sex:F` | 1.5 | 10 | 0.5 |
| S02 | `Group:Healthy control \| Sample type:Sample \| Batch:1 \| Injection order:1 \| Sex:M` | 2.0 | 12.5 | 0.7 |
| S03 | `Group:case \| Sample type:Sample \| Batch:2 \| Injection order:5 \| Sex:M` | *blank* | 11 | 0.6 |
| QC1 | `Sample type:QC \| Batch:1 \| Injection order:2` | 1.8 | 11.2 | 0.6 |
| QC2 | `Sample type:QC \| Batch:2 \| Injection order:4` | 1.7 | *not listed* | 0.6 |
| S04 | `Group:unknown \| Sample type:Sample \| Batch:2 \| Injection order:6 \| Sex:F` | 2.2 | 9 | 0.4 |

The task file says the outcome is `Group`, renames "Healthy control" to
`control`, keeps only `control` and `case`, and marks `QC` samples as quality
controls.

**After.** The table the pipeline reads (`prepared.csv`):

| Samples | Phenotype | Sex | Sample type | Batch | Injection order | Alanine | Glucose | Lactic acid |
|---|---|---|---|---|---|---|---|---|
| METHOD | | | | | | AN000101 | AN000101 | AN000101 |
| QC1 | | | QC | 1 | 2 | 1.8 | 11.2 | 0.6 |
| QC2 | | | QC | 2 | 4 | 1.7 | | 0.6 |
| S01 | case | F | subject | 1 | 3 | 1.5 | 10 | 0.5 |
| S02 | control | M | subject | 1 | 1 | 2.0 | 12.5 | 0.7 |
| S03 | case | M | subject | 2 | 5 | | 11 | 0.6 |

What changed, and why each step matters:

- **One row per sample, one column per metabolite**, with the packed text split
  into columns. The `METHOD` row records which analysis each value came from.
- **S04 is dropped, with a reason.** Its group, `unknown`, is not one of the
  kept groups. The summary file records "phenotype not in keep: unknown", so
  the sample is accounted for rather than silently lost.
- **QC samples are kept** with a blank phenotype. They have no group, but the
  pipeline needs them to correct for instrument drift.
- **Blanks stay blank.** S03's Alanine was recorded as blank, and QC2 was
  measured in the analysis but has no Glucose entry. Writing `0` instead would
  tell the pipeline "measured, nothing found".
- **The unnamed metabolite** takes its reference name, Lactic acid.
- **Batch and run order** come only from the study's own records. When a study
  has none, those columns stay blank rather than being invented.

The converter also writes `summary.json`, which records what was kept and
excluded and why, and `config.yaml`, which tells the pipeline where each part
of the table is.

## How it works

The agent never grades its own work.

1. **Freeze the input.** `onboard fetch` downloads a public study and records
   the source URL, retrieval time, and a SHA-256 hash of each file.
2. **Give the agent a task.** A short task file holds the choices that need a
   person, such as which factor is the outcome. The task prompt states the
   output contract the agent is judged against.
3. **The agent works through four tools:** read the study a page at a time,
   submit a converter and its tests, ask for them to be validated, and finish.
   Text from the study is passed to the model as data, never as instructions.
4. **Validation runs in a sandbox.** Each submission runs in a fresh container
   with no network, no credentials, and a read-only view of its inputs. The
   harness then checks the output against the pipeline's input rules, compares
   it cell by cell with known answers on four practice datasets, and runs the
   agent's own tests. The agent sees these results and may repair its code a
   limited number of times.
5. **The harness decides the outcome.** When the agent says it is done, the
   harness re-runs every check itself. A run passes only if they all pass.
6. **Hidden evaluation follows.** After the run, results the agent never saw
   are measured:
   - agreement with a hand-written reference converter on real studies;
   - five held-out synthetic datasets with known pitfalls, including one whose
     text tries to instruct the model to cheat;
   - whether the agent's tests catch eight real mistakes, each planted in a
     copy of the reference converter.
7. **Every result is reproducible.** Each run saves its inputs, every code
   version, the full conversation, and a manifest of hashes. An accepted
   converter is ordinary code: `onboard rerun` runs it again with no model and
   checks that the output is byte-for-byte identical.

## What the evaluation reports

| Measure | Question it answers |
|---|---|
| Status | Did the run pass, stop for human review, or fail? |
| Matches reference | Is the output identical to the reference converter's on a real study? |
| Held-out fixtures correct (of 5) | Does the converter handle pitfalls it never saw? |
| Broken variants caught (of 8) | Would the agent's tests catch realistic mistakes? |
| Injection outcome | Did the model ignore, mention, or act on instructions hidden in study text? |
| Cost, tokens, time | What did the run take? |
| Re-run matches | Does the saved converter reproduce its output without a model? |

These results describe one model on a small set of studies. They do not show
that a converter is scientifically valid beyond the rules it is checked
against, or that a new run would write the same code.

## Status

The harness is complete and has been tested end to end on two real public
studies. It has not yet been evaluated as the spec intends.

**Tested:**

- The test suite passes in CI, including sandbox tests that run real containers.
- Two live runs on real public Metabolomics Workbench studies, using
  `gpt-6.1-sol` at high effort. Both passed on their first submission, and in
  the hidden checks both converters matched the reference converter on every
  cell, got 5 of 5 held-out fixtures right, had tests that caught 8 of 8
  broken variants, and re-ran without a model to identical output. See
  [eval/results.md](eval/results.md).
  - **ST000001:** 24 plant samples, one analysis, 102 metabolites.
  - **ST003412:** 147 cell and medium samples, two analyses, 160 metabolites,
    QC and blank samples under a `Sample Type` factor, and literal `NA` drug
    labels.
- The ST003412 agent's tests first failed on the reference converter, which
  exposed two rules the contract had left open. Both were decided in the
  agent's favour, and the reference converter, contract checker, prompt, and
  decision pages now agree: records that differ only in a technical factor's
  spelling (`Batch:01`, `BATCH:01`) are identical, and
  `duplicate_metabolites_dropped` lists each dropped record.

**Not yet tested:**

- **Claude.** No run has used a Claude model. The run above used GPT through
  an unofficial local proxy on a ChatGPT plan, so it is a practice run.
- **The real evaluation.** The three studies for evaluation (R1-R3) have not
  been chosen, so `onboard eval` has not run on them, with repeat runs, as
  section 17 of the spec describes.
- **Prompt injection.** The run with H5's injected text as the task has not
  been made, so there is no injection result.
- **Every rule on real data.** The two studies exercise QC and blank samples,
  case-varying factor names, literal `NA` labels, and two analyses. Neither
  has batch or run-order records, unmeasured samples, or a metabolite measured
  in two analyses, so those rules are tested only on synthetic fixtures.
- **The reference converter.** It was written from the
  [specification](docs/spec.md) because the pipeline's original converter is
  not in this repository. It should be compared with the original before
  results that depend on it are trusted.

One run on one easy study shows the harness works with a live model and a real
deposit. It does not show how well any model does in general.

## Safety model

Generated code is treated as untrusted. It runs only in a container started
with no network, a read-only file system, all Linux capabilities dropped, no
privilege escalation, a non-root user, and limits on memory, CPU, processes,
and time. No environment variables, API keys, home directory, Docker socket, or
copy of this repository are mounted. The harness copies back only regular
files from the output directory and never follows links the code created.
Before any run is allowed, `onboard check-sandbox` runs a probe inside the
container that must see these attempts fail: an HTTP request, writes to the
code, input, and root directories, finding a credential in the environment,
and starting 500 processes. It must also succeed at writing to the output and
temporary directories. The other protections (non-root user, dropped
capabilities, no privilege escalation, and the memory, CPU, and time limits)
are set on the container but not tested by the probe; a separate test checks
that a slow converter is stopped at its time limit.

A container shares the host's kernel, so it is not as strong a boundary as a
virtual machine. The design assumes an agent that makes mistakes or is misled
by text in a study, not one deliberately exploiting kernel bugs. For stronger
isolation, run the harness inside a disposable virtual machine or use a
sandboxed container runtime such as gVisor. Disk use by generated code is not
capped.

## Getting started

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), and
[Docker](https://www.docker.com). Live runs need an
Anthropic API key or a DeepSeek API key.

```bash
uv sync
uv run onboard check-sandbox --build   # build the sandbox image and verify isolation
```

Then:

```bash
export ANTHROPIC_API_KEY=...
uv run onboard run fixtures/dev/D1/task.yaml    # one agent run on a practice task
uv run onboard rerun runs/<run-id>              # re-run its converter without a model
```

Each run writes `runs/<run-id>/` with a `report.md` summary, the manifest, the
log, and every version the agent submitted. A passed converter is also saved
to `studies/<study-id>/` with notes on how to re-run it.

| Command | Purpose |
|---|---|
| `onboard fetch ST000123` | Download and freeze a public study |
| `onboard draft-task ST000123` | Pre-fill a task file from that study, for you to finish |
| `onboard check-sandbox [--build]` | Build or verify the sandbox and run the isolation probe |
| `onboard run TASK.yaml [--model M] [--effort E]` | One agent run |
| `onboard rerun DIR` | Re-run an accepted converter with no model call |
| `onboard replay RUN_DIR` | Re-drive a recorded run from its log with no API calls |
| `onboard eval` | Runs on the frozen real studies, then the hidden checks |

**Cost.** A run with Claude Opus 5.5, the default model, costs roughly
$0.50-$1.50 within the limits in [`config.yaml`](config.yaml), which also caps
spending per run. For cheaper trial runs, DeepSeek models are supported through
DeepSeek's Anthropic-compatible API, using only the DeepSeek key:

```bash
export DEEPSEEK_API_KEY=...
uv run onboard run fixtures/dev/D1/task.yaml --model deepseek-flash
```

GPT can also be used through a ChatGPT subscription, via a local
[CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) proxy such as the
[EasyCLIProxyAPI](https://github.com/router-for-me/EasyCLIProxyAPI) desktop
app:

1. Install EasyCLIProxyAPI and sign in with ChatGPT (Codex OAuth).
2. Set the proxy to listen on `127.0.0.1` only, so your subscription is not
   exposed to your network. Note its port; `config.yaml` assumes 8317.
3. Copy one of its client API keys, then run:

   ```bash
   export CLIPROXY_API_KEY=...
   uv run onboard run fixtures/dev/D1/task.yaml --model gpt-6.1-sol --effort high
   ```

`config.yaml` lists `gpt-5.5` and `gpt-6.1-sol`. For another model, add a line
for the name the proxy lists. The harness asks the proxy for adaptive thinking
explicitly, because the proxy ignores the effort setting without it.
This route is unofficial: the proxy presents itself to OpenAI as the Codex CLI,
and it translates every request between API formats. It suits cheap practice
runs. Usage counts against your ChatGPT plan, so the per-run cost limit does
not apply.

Results from another provider measure that provider's model, so report them
separately from Claude runs.

**Evaluating.** `onboard eval` needs three real studies, chosen and frozen as
described in [`tasks/`](tasks/README.md). It writes `eval/results.md`, which
lists every failure and every disagreement with the reference converter.

## Repository layout

| Path | Contents |
|---|---|
| [`docs/spec.md`](docs/spec.md) | What is built and how it is judged |
| [`docs/decisions/`](docs/decisions/index.md) | Each conversion rule, with its reasons and rejected alternatives |
| `onboard/` | The harness: agent loop, tools, sandbox runner, validation, records, evaluation |
| `contract/` | The pipeline's input rules, checked independently of the reference converter |
| `reference/` | The reference converter and eight broken variants |
| `fixtures/` | Synthetic datasets: four practice (`dev`) and five held-out |
| `sandbox/` | The container image and the isolation probe |
| `prompts/` | What the agent is told, including the output contract |
| `tests/` | Tests for the harness, using a scripted model client |

## Data

Only public studies and synthetic fixtures are used. Downloaded studies are
not committed; their sources and hashes are recorded in `data/SOURCES.json`.
See the [data policy](docs/data_policy.md).

## Development

```bash
make check          # ruff, mypy, skill check, and tests
make docker-tests   # sandbox tests; `make check` skips them without Docker
make hooks          # run ruff before every commit
make webhook-tests  # tests for the review webhook; needs Bun
```

CI runs these on every pull request, with the sandbox tests in a separate job.
Tests use a scripted model client, so they need no API key.

Coding agents working on this repository follow [AGENTS.md](AGENTS.md) and the
workflows in [`.agents/skills/`](.agents/skills/README.md). Pull requests
labelled `ready for review` get an automated review through an
[Amp plugin](.amp/plugins/pr-review.md).
