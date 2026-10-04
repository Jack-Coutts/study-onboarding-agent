# Metabolite columns

**Status:** accepted

## Decision

Write metabolite columns in analysis priority order, then in record order within
each analysis. A metabolite's name is `metabolite_name`, else `refmet_name`, else
`unnamed`. A named metabolite found in several selected analyses is kept once,
from the first analysis in priority order, and the dropped copies are listed in
the summary, one entry per dropped record, so the summary shows how many
measurements were removed. `unnamed` features are never treated as the same metabolite.

Repeated header names are numbered as pandas 3 `read_csv` (C parser) numbers
them: the first copy keeps its name, and later copies become `name.1`,
`name.2`, and so on, skipping any number whose result is already a name in the
header row. The whole header row is numbered together, metadata columns
included.

## Why

- The same metabolite measured twice would enter the analysis as two features
  and count twice in any feature-level summary. Priority order is a recorded task
  parameter, so which copy survives is a choice a person made.
- Two features without a name carry no evidence that they are the same
  metabolite, so merging them would drop data on a guess.
- The pipeline reads `prepared.csv` with pandas. Numbering names the way pandas
  would means the pipeline sees exactly the names the converter wrote. Naive
  numbering can produce `Hexose.1` twice when the deposit already has a
  metabolite called `Hexose.1`, and pandas then renames one of them silently.

## Rejected

- Keeping every copy with a suffix naming its analysis. It changes names the
  pipeline and its outputs match on.
- Averaging copies across analyses. Different analyses can use different units
  and platforms.
- Numbering only the metabolite columns. A metabolite named `Batch` would then
  collide with the technical column.

## Limits

Matching across analyses uses the name as written, so `Alanine` and `alanine`
are different metabolites. Mapping names to identifiers (InChIKey, PubChem CID)
is a possible extension (spec section 24).

The numbering rule was checked against pandas 3.0.6 on 20,000 random header
rows, and is pinned in `tests/test_reference.py` with cases observed from
pandas. pandas' pure-Python helper `pandas.io.common.dedup_names` numbers
differently; the C parser is what `read_csv` uses by default.

## Revisit when

The pipeline reads its input with something other than pandas, or a deposit
format carries chemical identifiers for every feature.
