"""The pipeline's input rules (spec section 6), applied without importing the pipeline.

The validator runs this on a converter's output for the task's deposit. It reads
the deposit itself and does not use the reference converter, so it is an
independent check: it decides which samples must be kept, which cells must be
blank, and how the layout must look, but not the measured values.

Violations name a rule so that tests and the agent can tell them apart.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SAMPLES = "Samples"
PHENOTYPE = "Phenotype"
TECHNICAL = ("Sample type", "Batch", "Injection order")
SUBJECT = "subject"
SUMMARY_KEYS = (
    "n_samples",
    "n_features",
    "phenotype_counts",
    "analyses",
    "extra_factor_keys",
    "excluded_samples",
    "duplicate_metabolites_dropped",
    "technical_columns_from_factors",
    "blank_technical_columns",
)
FIXED_CONFIG: dict[str, Any] = {
    "sample_metadata_header_row": 1,
    "feature_names_row": 1,
    "data_start_row": 3,
    "feature_metadata_label_column": 1,
    "sheet_name": None,
    "target_column": PHENOTYPE,
    "sample_column": SAMPLES,
    "sample_type_column": "Sample type",
    "batch_column": "Batch",
    "position_column": "Injection order",
}


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.detail}"


@dataclass(frozen=True)
class Deposit:
    samples: dict[str, dict[str, str]]
    conflicts: list[str]
    analyses: list[str]
    measured: dict[str, set[str]]
    features_per_analysis: dict[str, int]
    feature_names: list[str]
    feature_values: list[dict[str, str]]
    dropped: list[dict[str, str]]
    phenotype_key: str
    rename: dict[str, str]
    keep: list[str] | None
    control_types: set[str]
    # Every spelling of each technical factor; samples may spell it differently.
    technical_keys: dict[str, set[str]]

    @property
    def extra_keys(self) -> list[str]:
        reserved = {self.phenotype_key, *(k for keys in self.technical_keys.values() for k in keys)}
        keys = {key for factors in self.samples.values() for key in factors}
        return sorted(keys - reserved)

    @property
    def expected_header(self) -> list[str]:
        metadata = [SAMPLES, PHENOTYPE, *self.extra_keys, *TECHNICAL]
        return number_like_pandas(metadata + self.feature_names)

    def technical(self, sample: str, column: str) -> str:
        """The sample's value under any spelling of the column's factor.

        Two different values are a conflict, which load_deposit records."""
        factors = self.samples[sample]
        return next((factors[k] for k in sorted(self.technical_keys[column]) if k in factors), "")

    def sample_type(self, sample: str) -> str:
        return self.technical(sample, "Sample type")

    def is_control(self, sample: str) -> bool:
        return self.sample_type(sample).casefold() in self.control_types

    def phenotype(self, sample: str) -> str:
        raw = self.samples[sample].get(self.phenotype_key, "")
        return self.rename.get(raw, raw) if raw else ""

    def reason(self, sample: str) -> str | None:
        """Why a sample is excluded (spec 6.2, in its order), or None if it is kept."""
        if not self.is_control(sample):
            phenotype = self.phenotype(sample)
            if not phenotype:
                return "no phenotype"
            if self.keep is not None and phenotype not in self.keep:
                return f"phenotype not in keep: {phenotype}"
        for analysis in self.analyses:
            if sample not in self.measured[analysis]:
                return f"not measured in {analysis}"
        return None

    def must_keep(self, sample: str) -> bool:
        return self.reason(sample) is None


def _records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [r for r in document if isinstance(r, dict)]
    if isinstance(document, dict) and ("local_sample_id" in document or "DATA" in document):
        return [document]
    if isinstance(document, dict):
        return [r for r in document.values() if isinstance(r, dict)]
    return []


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _factors(text: str) -> tuple[dict[str, str], bool]:
    """The record's factors, and whether one key appears with two different values."""
    factors: dict[str, str] = {}
    conflicting = False
    for part in text.split("|"):
        if part.strip():
            key, _, value = part.partition(":")
            key, value = key.strip(), value.strip()
            conflicting |= key in factors and factors[key] != value
            factors[key] = value
    return factors, conflicting


def number_like_pandas(names: list[str]) -> list[str]:
    """Header names as pandas 3 `read_csv` (C parser) reads a row with repeats.

    Later copies become name.1, name.2, ..., skipping any result already in the row.
    """
    numbered = list(names)
    seen: dict[str, int] = {}
    for i, name in enumerate(numbered):
        column = name
        count = seen.get(column, 0)
        while count > 0:
            seen[name] = count + 1
            column = f"{name}.{count}"
            count = count + 1 if column in numbered else seen.get(column, 0)
        numbered[i] = column
        seen[column] = count + 1
    return numbered


def _name(record: dict[str, Any]) -> str:
    for key in ("metabolite_name", "refmet_name"):
        if _text(record.get(key)).strip():
            return _text(record.get(key))
    return ""


def load_deposit(factors_json: Path, data_json: Path, task_yaml: Path) -> Deposit:
    task = yaml.safe_load(task_yaml.read_text(encoding="utf-8")) or {}
    samples: dict[str, dict[str, str]] = {}
    conflicts = []
    for record in _records(json.loads(factors_json.read_text(encoding="utf-8"))):
        sample = _text(record.get("local_sample_id"))
        factors, conflicting = _factors(_text(record.get("factors")))
        if conflicting or (sample in samples and samples[sample] != factors):
            conflicts.append(sample)
        samples.setdefault(sample, factors)

    data = _records(json.loads(data_json.read_text(encoding="utf-8")))
    present = sorted({_text(r.get("analysis_id")) for r in data})
    analyses = [str(a) for a in task.get("analyses") or present]
    measured: dict[str, set[str]] = {a: set() for a in analyses}
    owner: dict[str, str] = {}
    features: Counter[str] = Counter()
    names: list[str] = []
    values: list[dict[str, str]] = []
    dropped: set[tuple[str, str, str]] = set()
    for analysis in analyses:
        for record in data:
            if _text(record.get("analysis_id")) != analysis:
                continue
            cells = record.get("DATA") or {}
            measured[analysis].update(_text(s) for s in cells)
            name = _name(record) or "unnamed"
            # Unnamed features are never the same metabolite (decisions/metabolite-columns.md).
            if name != "unnamed" and owner.setdefault(name, analysis) != analysis:
                dropped.add((name, analysis, owner[name]))
                continue
            features[analysis] += 1
            names.append(name)
            values.append({_text(k): _text(v) for k, v in cells.items()})

    keys = {key for factors in samples.values() for key in factors}
    technical = {c: {k for k in keys if k.casefold() == c.casefold()} for c in TECHNICAL}
    for sample, factors in samples.items():
        for spellings in technical.values():
            if len({factors[k] for k in spellings if k in factors}) > 1:
                conflicts.append(sample)
    keep = task.get("keep")
    return Deposit(
        samples=samples,
        conflicts=sorted(set(conflicts)),
        analyses=analyses,
        measured=measured,
        features_per_analysis=dict(features),
        feature_names=names,
        feature_values=values,
        dropped=[
            {"metabolite": m, "analysis_id": a, "kept_from": k} for m, a, k in sorted(dropped)
        ],
        phenotype_key=str(task.get("phenotype_key", "")),
        rename={str(k): str(v) for k, v in (task.get("map") or {}).items()},
        keep=[str(k) for k in keep] if keep is not None else None,
        control_types={str(t).casefold() for t in task.get("control_sample_types") or []},
        technical_keys=technical,
    )


def check_contract(
    output_dir: Path, factors_json: Path, data_json: Path, task_yaml: Path
) -> list[Violation]:
    """Every rule in spec section 6 that the output breaks for this deposit."""
    deposit = load_deposit(factors_json, data_json, task_yaml)
    if deposit.conflicts:
        if not (output_dir / "prepared.csv").exists():
            return []
        return [
            Violation(
                "conflicts",
                f"samples {deposit.conflicts} have conflicting factor values; the converter "
                "must stop with an error, not write output",
            )
        ]
    files = _load_outputs(output_dir)
    if isinstance(files, list):
        return files
    grid, summary, config = files
    return _Checker(deposit, grid, summary, config).run()


def _load_outputs(
    output_dir: Path,
) -> tuple[list[list[str]], dict[str, Any], dict[str, Any]] | list[Violation]:
    problems = []
    for name in ("prepared.csv", "summary.json", "config.yaml"):
        if not (output_dir / name).is_file():
            problems.append(Violation("files", f"{name} was not written"))
    if problems:
        return problems
    grid: list[list[str]] = []
    summary: Any = None
    config: Any = None
    try:
        with (output_dir / "prepared.csv").open(newline="", encoding="utf-8") as handle:
            grid = [list(row) for row in csv.reader(handle)]
    except (UnicodeDecodeError, csv.Error) as error:
        problems.append(Violation("files", f"prepared.csv is not a UTF-8 CSV: {error}"))
    try:
        summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        problems.append(Violation("files", f"summary.json is not valid UTF-8 JSON: {error}"))
    try:
        config = yaml.safe_load((output_dir / "config.yaml").read_text(encoding="utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        problems.append(Violation("files", f"config.yaml is not valid UTF-8 YAML: {error}"))
    if problems:
        return problems
    if not isinstance(summary, dict):
        problems.append(Violation("files", "summary.json must hold an object"))
    if not isinstance(config, dict):
        problems.append(Violation("files", "config.yaml must hold a mapping"))
    if len(grid) < 2:
        problems.append(Violation("layout", "prepared.csv needs a header row and a METHOD row"))
    return problems or (grid, summary, config)


class _Checker:
    def __init__(
        self,
        deposit: Deposit,
        grid: list[list[str]],
        summary: dict[str, Any],
        config: dict[str, Any],
    ) -> None:
        self.deposit = deposit
        self.header = grid[0]
        self.method = grid[1]
        self.rows = grid[2:]
        self.summary = summary
        self.config = config
        self.violations: list[Violation] = []

    def fail(self, rule: str, detail: str) -> None:
        self.violations.append(Violation(rule, detail))

    def run(self) -> list[Violation]:
        layout_ok = self.check_layout()
        self.check_rows()
        if layout_ok:
            self.check_cells()
            self.check_features()
            self.check_config()
            if self.header == self.deposit.expected_header:
                self.check_values()
        self.check_accounting()
        self.check_summary()
        return self.violations

    @property
    def n_metadata(self) -> int:
        return 2 + len(self.deposit.extra_keys) + len(TECHNICAL)

    # Metadata columns by position: their names may be numbered (a factor called
    # "Phenotype" is written as "Phenotype.1"), so they are not looked up by name.
    PHENOTYPE_AT = 1

    def extra_at(self, key: str) -> int:
        return 2 + self.deposit.extra_keys.index(key)

    def technical_at(self, column: str) -> int:
        return 2 + len(self.deposit.extra_keys) + TECHNICAL.index(column)

    def check_layout(self) -> bool:
        expected = self.deposit.expected_header
        n = self.n_metadata
        ok = True
        if self.header[:n] != expected[:n]:
            self.fail(
                "layout",
                f"row 1 must start {expected[:n]} (extra factor columns sorted by name, "
                f"repeated names numbered), got {self.header[:n]}",
            )
            ok = False
        if self.header[n:] != expected[n:]:
            self.fail(
                "feature_names",
                f"metabolite columns must be named {expected[n:]}, got {self.header[n:]}",
            )
        repeated = sorted(n for n, c in Counter(self.header).items() if c > 1)
        if repeated:
            self.fail("unique_names", f"header names {repeated} appear more than once")
        if len(self.method) != len(self.header):
            self.fail("layout", "row 2 must have one cell per header column")
            return False
        if self.method[0] != "METHOD" or any(self.method[1 : self.n_metadata]):
            self.fail("layout", "row 2 must be METHOD followed by blanks under metadata columns")
            ok = False
        for i, analysis in enumerate(self.method[self.n_metadata :], self.n_metadata):
            if analysis not in self.deposit.analyses:
                self.fail(
                    "layout",
                    f"column {self.header[i]!r} has analysis {analysis!r}, not one of the "
                    f"selected analyses {self.deposit.analyses}",
                )
                ok = False
        return ok

    def check_rows(self) -> None:
        ids = [row[0] if row else "" for row in self.rows]
        for n, row in enumerate(self.rows, 3):
            if len(row) != len(self.header):
                self.fail(
                    "layout", f"row {n} has {len(row)} cells; the header has {len(self.header)}"
                )
        unknown = [s for s in ids if s not in self.deposit.samples]
        if unknown:
            self.fail(
                "identifiers",
                f"sample IDs {unknown} are not written exactly as any local_sample_id",
            )
        if len(ids) != len(set(ids)):
            self.fail("rows", "a sample appears in more than one row")
        if ids != sorted(ids):
            self.fail("rows", "sample rows must be sorted by sample ID")

    def check_cells(self) -> None:
        d = self.deposit
        phenotype, sample_type = self.PHENOTYPE_AT, self.technical_at("Sample type")
        for row in self.rows:
            if len(row) != len(self.header) or row[0] not in d.samples:
                continue
            sample = row[0]
            if not d.must_keep(sample):
                reason = "not measured in every selected analysis"
                if all(sample in d.measured[a] for a in d.analyses):
                    reason = "it has no phenotype or its phenotype is outside keep"
                self.fail("kept_samples", f"sample {sample!r} must be excluded: {reason}")
                continue
            if d.is_control(sample):
                if row[phenotype]:
                    self.fail("controls", f"control sample {sample!r} must have a blank Phenotype")
                if row[sample_type] != d.sample_type(sample):
                    self.fail(
                        "sample_type",
                        f"sample {sample!r} must have Sample type {d.sample_type(sample)!r}",
                    )
            else:
                if row[phenotype] != d.phenotype(sample):
                    self.fail(
                        "phenotype",
                        f"sample {sample!r} must have Phenotype {d.phenotype(sample)!r} "
                        f"(the deposit's label after map), got {row[phenotype]!r}",
                    )
                if row[sample_type] != SUBJECT:
                    self.fail("sample_type", f"sample {sample!r} must have Sample type 'subject'")
            for column in ("Batch", "Injection order"):
                keys = sorted(d.technical_keys[column])
                want = d.technical(sample, column)
                got = row[self.technical_at(column)]
                if got != want:
                    source = (
                        f"factors {keys}" if keys else "nothing: the deposit has no such factor"
                    )
                    self.fail(
                        "technical",
                        f"sample {sample!r} {column} must be {want!r}, from {source}; got {got!r}",
                    )
            for key in d.extra_keys:
                if row[self.extra_at(key)] != d.samples[sample].get(key, ""):
                    self.fail("extra_factors", f"sample {sample!r} column {key!r} must match")

    def check_values(self) -> None:
        """Each metabolite cell is the deposit's value, as text; blank or missing stays blank."""
        n, wrong = self.n_metadata, 0
        for row in self.rows:
            if len(row) != len(self.header) or row[0] not in self.deposit.samples:
                continue
            for j, values in enumerate(self.deposit.feature_values):
                want, got = values.get(row[0], ""), row[n + j]
                if got != want:
                    wrong += 1
                    if wrong <= 20:
                        self.fail(
                            "values",
                            f"sample {row[0]!r}, column {self.header[n + j]!r} must be {want!r} "
                            f"(blank when the deposit's value is blank or absent), got {got!r}",
                        )

    def check_features(self) -> None:
        counts = Counter(self.method[self.n_metadata :])
        for analysis in self.deposit.analyses:
            want = self.deposit.features_per_analysis.get(analysis, 0)
            if counts[analysis] != want:
                self.fail(
                    "duplicates",
                    f"analysis {analysis} must contribute {want} metabolite columns, got "
                    f"{counts[analysis]}; a metabolite in several analyses is kept once, from "
                    "the first in priority order",
                )
        order = [self.deposit.analyses.index(a) for a in self.method[self.n_metadata :]]
        if order != sorted(order):
            self.fail("layout", "metabolite columns must follow the analysis priority order")

    def check_accounting(self) -> None:
        excluded = self.summary.get("excluded_samples")
        if not isinstance(excluded, dict):
            self.fail("accounting", "summary.json excluded_samples must be an object")
            return
        rows = {row[0] for row in self.rows if row}
        for sample in sorted(self.deposit.samples):
            if sample in rows and sample in excluded:
                self.fail("accounting", f"sample {sample!r} is both a row and excluded")
            elif sample not in rows and sample not in excluded:
                self.fail("accounting", f"sample {sample!r} is neither a row nor excluded")
            elif sample in excluded and self.deposit.must_keep(sample):
                self.fail(
                    "kept_samples",
                    f"sample {sample!r} must be kept: it is measured in every selected "
                    "analysis and is a control or has a phenotype in keep",
                )
        unknown = sorted(set(excluded) - set(self.deposit.samples))
        if unknown:
            self.fail("accounting", f"excluded_samples has unknown sample IDs {unknown}")

    def check_summary(self) -> None:
        missing = [key for key in SUMMARY_KEYS if key not in self.summary]
        if missing:
            self.fail("summary", f"summary.json is missing {missing}")
            return
        n_features = len(self.header) - self.n_metadata
        tech = self.deposit.technical_keys
        phenotype = self.PHENOTYPE_AT
        counts = Counter(row[phenotype] for row in self.rows if len(row) > phenotype)
        counts.pop("", None)
        expected = {
            "n_samples": len(self.rows),
            "n_features": n_features,
            "analyses": self.deposit.analyses,
            "extra_factor_keys": self.deposit.extra_keys,
            "phenotype_counts": dict(counts),
        }
        for key, want in expected.items():
            if self.summary[key] != want:
                self.fail("summary", f"summary.json {key} must be {want!r}")
        excluded = self.summary["excluded_samples"]
        if isinstance(excluded, dict):
            for sample, reason in sorted(excluded.items()):
                if sample in self.deposit.samples and reason != self.deposit.reason(sample):
                    self.fail(
                        "summary",
                        f"excluded_samples[{sample!r}] must be {self.deposit.reason(sample)!r}, "
                        f"got {reason!r}",
                    )
        dropped = self.summary["duplicate_metabolites_dropped"]
        if not isinstance(dropped, list) or sorted(dropped, key=_canonical) != sorted(
            self.deposit.dropped, key=_canonical
        ):
            self.fail(
                "summary",
                f"duplicate_metabolites_dropped must list {self.deposit.dropped}, got {dropped}",
            )
        from_factors = {c for c in TECHNICAL if tech[c]}
        blank = {c for c in ("Batch", "Injection order") if not tech[c]}
        if set(self.summary["technical_columns_from_factors"]) != from_factors:
            self.fail("summary", f"technical_columns_from_factors must be {sorted(from_factors)}")
        if set(self.summary["blank_technical_columns"]) != blank:
            self.fail("summary", f"blank_technical_columns must be {sorted(blank)}")

    def check_config(self) -> None:
        want = dict(FIXED_CONFIG, feature_start_column=self.n_metadata + 1)
        for key, value in want.items():
            if self.config.get(key, object()) != value:
                self.fail("config", f"config.yaml {key} must be {value!r}")
        sample_type = self.technical_at("Sample type")
        present = {row[sample_type] for row in self.rows if len(row) > sample_type} - {SUBJECT}
        got = self.config.get("qc_sample_types")
        if not isinstance(got, list) or set(got) != present:
            self.fail("config", f"config.yaml qc_sample_types must list {sorted(present)}")
