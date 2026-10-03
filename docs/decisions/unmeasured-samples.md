# Unmeasured samples

**Status:** accepted

## Decision

Keep only samples measured in every selected analysis. A sample is measured in
an analysis if the analysis lists it, even with a blank value. List every
excluded sample and the reason in the converter's summary.

## Why

A blank cell in the pipeline's input means "measured, not detected". The
pipeline's imputation treats it as a value below the detection limit. Writing a
sample that an analysis never ran as blank would invent low values for every
metabolite in that analysis.

## Rejected

- Keeping every sample and leaving unmeasured cells blank.
- Imputing unmeasured analyses separately.

## Limits

Selecting fewer analyses keeps more samples. The converter does not choose
analyses for the user; the selection is a recorded parameter.

## Revisit when

The pipeline gains a separate marker for "not measured".
