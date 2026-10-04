# Tasks

Held-out tasks R1-R3 are `R1.yaml`, `R2.yaml`, and `R3.yaml`, one per public
Workbench study, chosen and frozen as spec section 17.1 describes. They were
frozen before any agent ran on them; their deposits' hashes are in
`data/SOURCES.json`.

| Task | Study | Why it was chosen |
|---|---|---|
| R1 | ST003435, zebrafish embryos and medium, 49 samples | QC and blank samples marked by a `Sample Type` factor; two analyses |
| R2 | ST004133, mouse plasma, 62 samples | four analyses with metabolites measured in more than one; injection order recorded |
| R3 | ST002977, fecal transplant, 76 samples | no batch or run order; blank samples; 19 samples missing from the second chosen analysis; a 9 MB deposit |

Before freezing, the reference converter's output for each was inspected:
R1 keeps all 49 samples (7 drug groups plus 5 QC and blank controls); R2 keeps
all 62 (46 high-fat, 16 chow) with injection order filled and 51 duplicate
metabolite records dropped; R3 keeps 57 (24 before and 24 after transplant,
plus 9 blanks), excludes 19 not measured in AN004889, and drops 191 duplicate
records. The practice studies ST000001 and ST003412 were not reused, because
the rules changed after ST003412's results were seen.

`ST000001.yaml` and `ST003412.yaml` are worked examples, not evaluation
slots: the tasks used for the practice runs reported in `eval/results.md`.
Both were drafted with `onboard draft-task`.

Each file is a task file (spec section 5.2) whose `study_id` has been fetched
with `onboard fetch`. `onboard draft-task ST…` writes a starting point,
`draft-ST….yaml`, listing the study's factors and analyses. Choose the outcome
(every `CHOOSE`), then save it as `R1.yaml`, `R2.yaml`, or `R3.yaml`. Runs
refuse a file that still has a `CHOOSE` value. Record the study IDs, task files, and hashes before the
first evaluation run, and do not change prompts or tools after seeing results.
