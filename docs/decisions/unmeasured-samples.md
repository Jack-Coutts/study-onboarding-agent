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

An analysis lists a sample if any of its records has the sample in `DATA`. A
listed sample missing from one record's `DATA` gets a blank cell for that
metabolite, which the pipeline reads as not detected. A deposit where that
happens often needs a closer look before its blanks are trusted.

## Revisit when

The pipeline gains a separate marker for "not measured".
