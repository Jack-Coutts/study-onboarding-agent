# Tasks

Held-out tasks R1-R3 go here as `R1.yaml`, `R2.yaml`, and `R3.yaml`, one per
public Workbench study, chosen and frozen as spec section 17.1 describes. None
is chosen yet, so `onboard eval` stops and says so.

Each file is a task file (spec section 5.2) whose `study_id` has been fetched
with `onboard fetch`. `onboard draft-task ST…` writes a starting point,
`draft-ST….yaml`, listing the study's factors and analyses. Choose the outcome
(every `CHOOSE`), then save it as `R1.yaml`, `R2.yaml`, or `R3.yaml`. Runs
refuse a file that still has a `CHOOSE` value. Record the study IDs, task files, and hashes before the
first evaluation run, and do not change prompts or tools after seeing results.
