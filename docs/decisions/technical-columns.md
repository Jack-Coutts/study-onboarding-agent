# Technical columns

**Status:** accepted

## Decision

Fill `Sample type`, `Batch`, and `Injection order` from deposit factors with the
same name, matched case-insensitively. When a deposit has no such factor, leave
`Batch` and `Injection order` blank and record that in the summary. `Sample
type` defaults to `subject`, except for samples whose sample-type factor marks
them as QC, pooled QC, or blank.

## Why

The pipeline uses batch and injection order for drift correction and as a
batch term in differential abundance. An invented value is worse than none:
it makes the correction run on a structure that does not exist, with no error.

## Rejected

- Using one batch for the whole study when none is recorded.
- Inferring injection order from sample identifiers or file order.

## Limits

Matching on factor names misses a deposit that records run order under another
name. Such a mapping is a study-specific parameter, written down in the study's
processing notes.

## Revisit when

A deposit format records run metadata in a dedicated field.
