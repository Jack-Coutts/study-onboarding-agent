# Studies

`onboard run` copies each accepted converter here as `studies/<ST>/`, with its
tests, task file, manifest, and `PROCESSING.md`. `onboard rerun studies/<ST>`
re-runs it without a model call.


Converters here are kept exactly as they were accepted, so their hashes and
the evaluation that produced them stay valid. A limitation found in review:
the converters accepted before this rule was added (ST000001, ST003412, and
R1-R3's ST003435, ST004133, ST002977) write an empty result instead of
stopping when a task selects no analyses or an unknown one. The harness now
refuses such a task before a run or evaluation starts.
