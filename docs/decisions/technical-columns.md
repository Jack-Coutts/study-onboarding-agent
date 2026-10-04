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

A sample is a control when its sample-type factor matches one of the task's
`control_sample_types`, case-insensitively. The control's `Sample type` cell
keeps the deposit's spelling (`Blank`, `pool`), and `qc_sample_types` in the
layout config lists those spellings, so the pipeline matches exactly what was
written. Controls are kept with a blank `Phenotype` and are not filtered by the
task's `keep` list.

Samples may spell a technical factor differently (`Sample type` in one,
`SAMPLE TYPE` in another). Those spellings name one column: a difference in
case is a formatting accident, not a conflict. If one sample gives two
spellings different values (`Batch:1 | batch:2`), that is a conflict, and the
converter stops as it does for conflicting duplicate records. This replaced an
earlier rule that stopped whenever two spellings appeared anywhere in a
deposit. That rule sent studies with inconsistent capitalisation to a person
without any evidence of a problem, and the task prompt never stated it.

## Revisit when

A deposit format records run metadata in a dedicated field.
