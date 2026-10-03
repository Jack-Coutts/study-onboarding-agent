# Identifiers

**Status:** accepted

## Decision

Read and write sample, subject, and feature identifiers as text, exactly as the
deposit writes them. If two records share a sample identifier but disagree on
any factor, stop with an error that names both records.

## Why

- `01` and `1` are different identifiers in a deposit. Numeric parsing merges
  them, and spreadsheet round trips can drop leading zeros or turn long
  identifiers into floats.
- When duplicate records disagree, picking one makes the result depend on
  record order. Stopping is the only choice that cannot be silently wrong.

## Rejected

- Normalising identifiers (trimming zeros, changing case). It changes what the
  pipeline joins on.
- Keeping the first or last of conflicting records.

## Limits

Identical duplicate records are collapsed to one. One record that gives the
same factor two different values (`Group:case | Group:control`) also stops the
run; the same value repeated is accepted. Whitespace around an
identifier is not trimmed; a deposit that relies on that needs a decision of its
own.

## Revisit when

A deposit format stores identifiers as typed numbers with no text form.
