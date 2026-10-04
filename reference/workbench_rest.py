"""Reference converter: a Metabolomics Workbench REST deposit to the pipeline input layout.

This is the correctness baseline for the harness (spec section 13). It implements
the output contract in docs/spec.md section 6 and the decision pages under
docs/decisions/. It uses only the standard library and PyYAML, so it runs in the
sandbox image and on the host.

Usage:
    python workbench_rest.py --factors F --data D --task T --output DIR
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SAMPLES = "Samples"
PHENOTYPE = "Phenotype"
SAMPLE_TYPE = "Sample type"
BATCH = "Batch"
INJECTION_ORDER = "Injection order"
TECHNICAL = (SAMPLE_TYPE, BATCH, INJECTION_ORDER)
SUBJECT = "subject"
UNNAMED = "unnamed"


class ConversionError(Exception):
    """The deposit cannot be converted without a human decision."""


@dataclass(frozen=True)
class Task:
    phenotype_key: str
    rename: dict[str, str]
    keep: list[str] | None
    analyses: list[str] | None
    control_sample_types: list[str]


@dataclass(frozen=True)
class Feature:
    name: str
    analysis_id: str
    values: dict[str, str]


def _identifier(value: Any) -> str:
    """Identifiers are text, exactly as the deposit writes them (decisions/identifiers.md)."""
    return "" if value is None else str(value)


def _value(value: Any) -> str:
    return "" if value is None else str(value)


def _records(document: Any, required_key: str) -> list[dict[str, Any]]:
    """Workbench REST returns a mapping of "1", "2", ... to records, or one bare record."""
    if isinstance(document, list):
        records = document
    elif isinstance(document, dict) and required_key in document:
        records = [document]
    elif isinstance(document, dict):
        records = list(document.values())
    else:
        raise ConversionError(f"expected records with {required_key!r}, got {type(document)}")
    for record in records:
        if not isinstance(record, dict) or required_key not in record:
            raise ConversionError(f"every record needs {required_key!r}; found {record!r}")
    return records


def _string_list(value: Any, name: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ConversionError(f"task {name} must be a list")
    return [str(item) for item in value]


def load_task(path: Path) -> Task:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw.get("phenotype_key"):
        raise ConversionError("task.yaml must set phenotype_key")
    rename = raw.get("map") or {}
    if not isinstance(rename, dict):
        raise ConversionError("task map must be a mapping")
    return Task(
        phenotype_key=str(raw["phenotype_key"]),
        rename={str(k): str(v) for k, v in rename.items()},
        keep=_string_list(raw.get("keep"), "keep"),
        analyses=_string_list(raw.get("analyses"), "analyses"),
        control_sample_types=_string_list(raw.get("control_sample_types"), "control_sample_types")
        or [],
    )


def parse_factors(text: str, sample_id: str) -> dict[str, str]:
    """Parse "Key:value | Key2:value2". A value may itself contain ':'."""
    factors: dict[str, str] = {}
    for part in text.split("|"):
        if not part.strip():
            continue
        key, _, value = part.partition(":")
        key, value = key.strip(), value.strip()
        if key in factors and factors[key] != value:
            raise ConversionError(
                f"sample {sample_id!r} gives factor {key!r} two values in one record: {text!r}"
            )
        factors[key] = value
    return factors


def read_samples(records: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Sample ID to factors. Identical duplicates collapse; conflicting ones stop the run."""
    samples: dict[str, dict[str, str]] = {}
    first_record: dict[str, int] = {}
    for number, record in enumerate(records, 1):
        sample_id = _identifier(record.get("local_sample_id"))
        if not sample_id:
            raise ConversionError(f"factor record {number} has no local_sample_id")
        factors = parse_factors(_value(record.get("factors")), sample_id)
        if sample_id in samples:
            if samples[sample_id] != factors:
                raise ConversionError(
                    f"conflicting factor records for sample {sample_id!r}: "
                    f"record {first_record[sample_id]} has {samples[sample_id]}, "
                    f"record {number} has {factors}"
                )
            continue
        samples[sample_id] = factors
        first_record[sample_id] = number
    return samples


def technical_keys(samples: dict[str, dict[str, str]]) -> dict[str, set[str]]:
    """Every spelling of each technical column's factor, matched case-insensitively.

    Samples may spell a factor differently (`Batch`, `batch`); they name one column.
    """
    keys = {key for factors in samples.values() for key in factors}
    return {column: {k for k in keys if k.casefold() == column.casefold()} for column in TECHNICAL}


def _technical(sample_id: str, factors: dict[str, str], keys: set[str]) -> str:
    """The sample's value for a technical column; two different values stop the run."""
    values = {factors[key] for key in keys if key in factors}
    if len(values) > 1:
        named = sorted(key for key in keys if key in factors)
        raise ConversionError(
            f"sample {sample_id!r} gives factors {named} different values: {sorted(values)}"
        )
    return values.pop() if values else ""


def number_repeated(names: list[str]) -> list[str]:
    """Number repeated headers as pandas read_csv does, never reusing a name in the row.

    The first copy keeps its name; later copies become name.1, name.2, ..., skipping
    any number that would collide with a name already in the header row.
    """
    names = list(names)
    counts: dict[str, int] = {}
    for i, name in enumerate(names):
        column = name
        count = counts.get(column, 0)
        while count > 0:
            counts[name] = count + 1
            column = f"{name}.{count}"
            count = count + 1 if column in names else counts.get(column, 0)
        names[i] = column
        counts[column] = count + 1
    return names


def _feature_name(record: dict[str, Any]) -> str:
    for key in ("metabolite_name", "refmet_name"):
        name = _value(record.get(key))
        if name.strip():
            return name
    return UNNAMED


def select_features(
    records: list[dict[str, Any]], analyses: list[str]
) -> tuple[list[Feature], list[dict[str, str]], dict[str, set[str]]]:
    """Features in priority order, the cross-analysis duplicates dropped, and who was measured.

    A named metabolite in several selected analyses is kept from the first analysis
    in priority order. Unnamed features are never treated as the same metabolite.
    """
    by_analysis: dict[str, list[dict[str, Any]]] = {analysis: [] for analysis in analyses}
    for record in records:
        analysis = _identifier(record.get("analysis_id"))
        if analysis in by_analysis:
            by_analysis[analysis].append(record)
    measured: dict[str, set[str]] = {}
    owner: dict[str, str] = {}
    features: list[Feature] = []
    dropped: dict[tuple[str, str], str] = {}
    for analysis in analyses:
        measured[analysis] = set()
        for record in by_analysis[analysis]:
            data = record.get("DATA") or {}
            if not isinstance(data, dict):
                raise ConversionError(f"DATA in analysis {analysis} must be a mapping")
            values = {_identifier(sample): _value(value) for sample, value in data.items()}
            measured[analysis].update(values)
            name = _feature_name(record)
            if name != UNNAMED and owner.setdefault(name, analysis) != analysis:
                dropped[(name, analysis)] = owner[name]
                continue
            features.append(Feature(name=name, analysis_id=analysis, values=values))
    dropped_list = [
        {"metabolite": name, "analysis_id": analysis, "kept_from": kept}
        for (name, analysis), kept in sorted(dropped.items())
    ]
    return features, dropped_list, measured


def prepare(factors_json: Path, data_json: Path, task_yaml: Path, output_dir: Path) -> None:
    """Write prepared.csv, summary.json, and config.yaml to output_dir."""
    task = load_task(Path(task_yaml))
    factor_records = _records(
        json.loads(Path(factors_json).read_text(encoding="utf-8")), "local_sample_id"
    )
    data_records = _records(json.loads(Path(data_json).read_text(encoding="utf-8")), "analysis_id")
    samples = read_samples(factor_records)

    if not any(task.phenotype_key in factors for factors in samples.values()):
        raise ConversionError(f"no sample has the phenotype factor {task.phenotype_key!r}")
    tech = technical_keys(samples)
    reserved = {task.phenotype_key, *(key for keys in tech.values() for key in keys)}
    extra_keys = sorted(
        {key for factors in samples.values() for key in factors if key not in reserved}
    )

    present = sorted({_identifier(record.get("analysis_id")) for record in data_records})
    analyses = task.analyses if task.analyses is not None else present
    unknown = [analysis for analysis in analyses if analysis not in present]
    if unknown or not analyses:
        raise ConversionError(f"analyses {unknown or analyses} are not in the deposit")
    features, dropped, measured = select_features(data_records, analyses)

    controls = {kind.casefold() for kind in task.control_sample_types}
    rows: list[list[str]] = []
    excluded: dict[str, str] = {}
    phenotypes: Counter[str] = Counter()
    control_types: set[str] = set()
    for sample_id in sorted(samples):
        sample_factors = samples[sample_id]
        sample_type = _technical(sample_id, sample_factors, tech[SAMPLE_TYPE])
        is_control = sample_type.casefold() in controls
        raw_phenotype = sample_factors.get(task.phenotype_key, "")
        phenotype = task.rename.get(raw_phenotype, raw_phenotype)
        if is_control:
            phenotype = ""
        elif not raw_phenotype:
            excluded[sample_id] = "no phenotype"
            continue
        elif task.keep is not None and phenotype not in task.keep:
            excluded[sample_id] = f"phenotype not in keep: {phenotype}"
            continue
        missing = [analysis for analysis in analyses if sample_id not in measured[analysis]]
        if missing:
            excluded[sample_id] = f"not measured in {missing[0]}"
            continue
        if is_control:
            control_types.add(sample_type)
        else:
            phenotypes[phenotype] += 1
        rows.append(
            [
                sample_id,
                phenotype,
                *(sample_factors.get(key, "") for key in extra_keys),
                sample_type if is_control else SUBJECT,
                _technical(sample_id, sample_factors, tech[BATCH]),
                _technical(sample_id, sample_factors, tech[INJECTION_ORDER]),
                *(feature.values.get(sample_id, "") for feature in features),
            ]
        )

    metadata = [SAMPLES, PHENOTYPE, *extra_keys, SAMPLE_TYPE, BATCH, INJECTION_ORDER]
    header = number_repeated(metadata + [feature.name for feature in features])
    method_row = ["METHOD", *([""] * (len(metadata) - 1)), *(f.analysis_id for f in features)]

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "prepared.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows([header, method_row, *rows])

    summary = {
        "n_samples": len(rows),
        "n_features": len(features),
        "phenotype_counts": dict(sorted(phenotypes.items())),
        "analyses": analyses,
        "extra_factor_keys": extra_keys,
        "excluded_samples": excluded,
        "duplicate_metabolites_dropped": dropped,
        "technical_columns_from_factors": [c for c in TECHNICAL if tech[c]],
        "blank_technical_columns": [c for c in (BATCH, INJECTION_ORDER) if not tech[c]],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    config = {
        "sample_metadata_header_row": 1,
        "feature_names_row": 1,
        "data_start_row": 3,
        "feature_start_column": len(metadata) + 1,
        "feature_metadata_label_column": 1,
        "sheet_name": None,
        "target_column": PHENOTYPE,
        "sample_column": SAMPLES,
        "sample_type_column": SAMPLE_TYPE,
        "batch_column": BATCH,
        "position_column": INJECTION_ORDER,
        "qc_sample_types": sorted(control_types),
    }
    (output / "config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a Workbench REST deposit to the pipeline input layout."
    )
    parser.add_argument("--factors", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        prepare(args.factors, args.data, args.task, args.output)
    except ConversionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
