# Evaluation

`onboard eval` writes `results.md` and `results.json` here: one row per run, a
summary row, and every disagreement with the reference converter or a held-out
fixture.

`results.md` is the R1-R3 evaluation: two runs on each frozen task plus the
injection run, with `gpt-6.1-sol` through a local proxy. `practice-results.md`
holds the hidden checks on two practice runs (ST000001 and ST003412) made
before R1-R3 were frozen.
