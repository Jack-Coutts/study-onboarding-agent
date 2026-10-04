# Task: write a converter for study {{STUDY_ID}}

The deposit is frozen. Read it with `inspect_deposit`. The task file is:

```yaml
{{TASK_YAML}}
```

`phenotype_key` is the factor used as the outcome label. `map` (optional) renames
labels. `keep` (optional) lists the outcome values to keep, after renaming.
`analyses` (optional) lists the analyses to use, in priority order; without it,
use every analysis in the deposit, sorted by analysis ID.
`control_sample_types` lists the sample types that mark QC, pooled QC, and blank
samples.

## What to write

`prepare.py` must define

```python
def prepare(factors_json: Path, data_json: Path, task_yaml: Path, output_dir: Path) -> None:
    """Write prepared.csv, summary.json, and config.yaml to output_dir."""
```

and must also run as
`python prepare.py --factors F --data D --task T --output DIR`.

It must handle any Workbench REST deposit, not only this study: it is also run
on development fixtures and on other deposits you will not see. Allowed imports:
the standard library, `pandas`, `numpy`, and `pyyaml`. It runs with no network,
a read-only file system except `output_dir` and `/tmp`, and a time limit.

`test_prepare.py` is a pytest suite for your converter. It must import
`from prepare import prepare`, build its own small deposits in `tmp_path`, and
not read the real deposit or any fixture (only your two files are available
when it runs). It must pass against your converter. It is also run against
converters with realistic mistakes, and it should fail against each of them.

## Inputs

- `factors.json`: records with `local_sample_id`, `mb_sample_id`,
  `sample_source`, and `factors`, a string such as
  `Genotype:wild type | Treatment:Control`. Split on `|`, then on the first `:`;
  strip spaces around keys and values. A value may contain `:`.
- `data.json`: one record per metabolite per analysis, with `analysis_id`,
  `metabolite_name`, `refmet_name`, `units`, and `DATA`, a mapping from sample
  ID to value. Values are strings and may be blank.
- Either file may be a JSON object mapping "1", "2", ... to records, a list of
  records, or a single bare record.

## Output contract

The converter writes three files to `output_dir`.

### prepared.csv

- Row 1: `Samples`, `Phenotype`, extra factor columns (sorted by name),
  `Sample type`, `Batch`, `Injection order`, then one column per metabolite.
- Row 2: `METHOD` in the first cell, blanks under the metadata columns, then
  the analysis ID under each metabolite.
- Row 3 onwards: one row per kept sample, sorted by sample ID as text.

Rules:

1. Identifiers are written exactly as in the deposit, as text. `01` and `1` are
   different samples. Whitespace inside an identifier is kept.
2. If two factor records share a `local_sample_id` but disagree on any factor,
   or one record gives the same factor two different values, stop and write
   nothing. Called as a function, `prepare` raises an exception whose message
   names the sample. Run from the command line, it prints that message to
   stderr and exits with a non-zero code. Identical duplicate records collapse
   to one.
3. Extra factor columns are every factor key in `factors.json` except the
   phenotype key and the technical factors in rule 4. A sample without that
   factor gets a blank cell.
4. `Sample type`, `Batch`, and `Injection order` come only from factors with
   the same name, matched case-insensitively. Samples may spell a factor
   differently (`Batch` in one, `batch` in another); those spellings are one
   column. If one sample gives two spellings different values, stop as in
   rule 2. `Batch` and `Injection order` are blank when no such factor exists;
   never invent them.
5. A sample is a control if its sample-type factor matches one of
   `control_sample_types`, case-insensitively. A control's `Sample type` cell is
   the deposit's value as written; every other sample's is `subject`.
6. Controls are kept with a blank `Phenotype`, whatever their phenotype factor
   says, and `keep` does not apply to them.
7. Other samples get `Phenotype` = the phenotype factor's value after `map`.
   A sample without a phenotype (factor missing or blank) is excluded. A sample
   whose renamed phenotype is not in `keep` (when `keep` is given) is excluded.
   A literal label such as `NA` is a label, not missing.
8. A sample is measured in an analysis if any of that analysis's records lists
   it in `DATA`, even with a blank value. A sample not measured in every
   selected analysis is excluded. Never write it with blank values.
9. Metabolite columns follow the analyses in priority order, and record order
   within each analysis. A metabolite's name is `metabolite_name`, else
   `refmet_name`, else `unnamed` (a name that is empty or only spaces counts as
   missing).
10. A named metabolite in several selected analyses is kept once, from the first
    analysis in priority order; the copies in later analyses are dropped and
    listed. `unnamed` features never count as the same metabolite.
11. Repeated header names are numbered as pandas `read_csv` numbers them: the
    first keeps its name, and later copies become `name.1`, `name.2`, ...,
    skipping any number whose result is already a name in the header row. The
    whole header row, including metadata columns, is numbered together.
12. Write only the three output files, as regular files directly in
    `output_dir`. Links and subdirectories are ignored.
13. A cell is the deposit's value for that sample, as text. A blank value, or a
    sample missing from that metabolite's `DATA` while measured in the
    analysis, is written blank.

Exclusion reasons are exactly one of these, checked in this order:

- `no phenotype`
- `phenotype not in keep: <renamed phenotype>`
- `not measured in <first selected analysis that does not list the sample>`

### summary.json

An object with:

- `n_samples`: number of rows written.
- `n_features`: number of metabolite columns.
- `phenotype_counts`: label to count, over kept non-control samples.
- `analyses`: the selected analyses, in priority order.
- `extra_factor_keys`: the extra factor columns, sorted.
- `excluded_samples`: sample ID to reason.
- `duplicate_metabolites_dropped`: a list of
  `{"metabolite": name, "analysis_id": analysis it was dropped from, "kept_from": analysis kept}`.
- `technical_columns_from_factors`: which of `Sample type`, `Batch`,
  `Injection order` came from a factor.
- `blank_technical_columns`: which of `Batch`, `Injection order` are blank
  because no factor exists.

Every distinct `local_sample_id` in `factors.json` appears either as a row in
`prepared.csv` or as a key in `excluded_samples`, never both and never neither.
List order matters only for `analyses`.

### config.yaml

```yaml
sample_metadata_header_row: 1
feature_names_row: 1
data_start_row: 3
feature_start_column: <first metabolite column, 1-based>
feature_metadata_label_column: 1
sheet_name: null
target_column: Phenotype
sample_column: Samples
sample_type_column: Sample type
batch_column: Batch
position_column: Injection order
qc_sample_types: [<distinct Sample type values of the kept controls>]
```

## Checks

`validate_converter` runs your version on this deposit and on development
fixtures, checks the output against the contract, compares the fixtures with
their expected outputs, and runs your tests. If the deposit cannot be converted
without a human decision (for example, the phenotype key is absent, or records
conflict), finish with `needs_review` and explain. `finish` must name a
submitted version, so submit your converter first even then. Excluded samples are a
normal result, not a reason for `needs_review`.
