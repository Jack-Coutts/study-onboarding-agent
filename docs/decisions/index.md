# Decisions

Each page records one choice about how a deposit becomes pipeline input: the
decision, why, what was rejected, its limits, and when to revisit it. Read the
matching page before changing the behaviour it covers, and update it in the
same change when the decision changes.

| Page | Decides |
| --- | --- |
| [Identifiers](identifiers.md) | Sample, subject, and feature identifiers are text, and conflicting records stop the run |
| [Unmeasured samples](unmeasured-samples.md) | A sample missing from a selected analysis is excluded, not written as missing |
| [Technical columns](technical-columns.md) | Batch and injection order come only from the deposit, never invented |
| [Metabolite columns](metabolite-columns.md) | Order, names, cross-analysis duplicates, and header numbering of metabolite columns |
