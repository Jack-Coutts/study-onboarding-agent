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

Early. The build spec is in [docs/spec.md](docs/spec.md). Nothing is
implemented yet.

## Data

Only public deposits are used. See [docs/data_policy.md](docs/data_policy.md).
