"""Compare a converter's outputs with expected outputs.

Used for dev fixtures (diff returned to the agent), held-out fixtures, and the
reference output on real deposits (both hidden). prepared.csv is compared cell by
cell, aligning rows on the sample ID and columns on the header. summary.json and
config.yaml are compared after parsing; list order matters only where the
contract gives it meaning (`analyses`, which is in priority order).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

OUTPUT_FILES = ("prepared.csv", "summary.json", "config.yaml")
ORDERED_SUMMARY_LISTS = frozenset({"analyses"})
MAX_CELL_DIFFS = 50


def read_grid(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [list(row) for row in csv.reader(handle)]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _normalise(value: Any, ordered: bool) -> Any:
    if isinstance(value, list) and not ordered:
        return sorted(value, key=_canonical)
    return value


def diff_prepared(actual: Path, expected: Path) -> list[str]:
    want = read_grid(expected)
    try:
        got = read_grid(actual)
    except (UnicodeDecodeError, csv.Error) as error:
        return [f"prepared.csv is not a UTF-8 CSV: {error}"]
    if len(want) < 2:
        raise ValueError(f"{expected} has fewer than two rows")
    if len(got) < 2:
        return [f"prepared.csv has {len(got)} rows; the header and METHOD rows are required"]
    diffs: list[str] = []
    got_header, want_header = got[0], want[0]
    if got_header != want_header:
        diffs.append(f"prepared.csv header: expected {want_header}, got {got_header}")
    if got[1] != want[1]:
        diffs.append(f"prepared.csv row 2: expected {want[1]}, got {got[1]}")
    got_rows = {row[0]: row for row in got[2:] if row}
    want_rows = {row[0]: row for row in want[2:] if row}
    got_ids = [row[0] for row in got[2:] if row]
    want_ids = [row[0] for row in want[2:] if row]
    missing = [s for s in want_ids if s not in got_rows]
    extra = [s for s in got_ids if s not in want_rows]
    if missing:
        diffs.append(f"prepared.csv is missing sample rows {missing}")
    if extra:
        diffs.append(f"prepared.csv has unexpected sample rows {extra}")
    if len(got_ids) != len(set(got_ids)):
        diffs.append("prepared.csv has repeated sample rows")
    shared = [s for s in got_ids if s in want_rows]
    if not missing and not extra and got_ids != want_ids:
        diffs.append(f"prepared.csv sample order: expected {want_ids}, got {got_ids}")
    got_columns = {name: i for i, name in enumerate(got_header)}
    cell_diffs = 0
    for sample in shared:
        for j, column in enumerate(want_header):
            if column not in got_columns:
                continue
            want_cell = want_rows[sample][j] if j < len(want_rows[sample]) else ""
            got_row = got_rows[sample]
            k = got_columns[column]
            got_cell = got_row[k] if k < len(got_row) else ""
            if want_cell != got_cell:
                cell_diffs += 1
                if cell_diffs <= MAX_CELL_DIFFS:
                    diffs.append(
                        f"prepared.csv sample {sample!r}, column {column!r}: "
                        f"expected {want_cell!r}, got {got_cell!r}"
                    )
    if cell_diffs > MAX_CELL_DIFFS:
        diffs.append(f"... and {cell_diffs - MAX_CELL_DIFFS} more differing cells")
    return diffs


def _diff_mapping(name: str, got: Any, want: dict[str, Any], ordered: frozenset[str]) -> list[str]:
    if not isinstance(got, dict):
        return [f"{name} must hold a mapping, got {type(got).__name__}"]
    diffs = []
    for key in sorted(set(want) | set(got)):
        if key not in got:
            diffs.append(f"{name} is missing {key!r}")
        elif key not in want:
            diffs.append(f"{name} has unexpected key {key!r}")
        else:
            a = _normalise(got[key], key in ordered)
            b = _normalise(want[key], key in ordered)
            if _canonical(a) != _canonical(b):
                diffs.append(f"{name} {key!r}: expected {_canonical(b)}, got {_canonical(a)}")
    return diffs


def diff_summary(actual: Path, expected: Path) -> list[str]:
    try:
        got = json.loads(actual.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"summary.json is not valid JSON: {error}"]
    want = json.loads(expected.read_text(encoding="utf-8"))
    return _diff_mapping("summary.json", got, want, ORDERED_SUMMARY_LISTS)


def diff_config(actual: Path, expected: Path) -> list[str]:
    try:
        got = yaml.safe_load(actual.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        return [f"config.yaml is not valid YAML: {error}"]
    want = yaml.safe_load(expected.read_text(encoding="utf-8"))
    return _diff_mapping("config.yaml", got, want, frozenset())


def compare_outputs(actual_dir: Path, expected_dir: Path) -> list[str]:
    """Differences between a converter's output directory and the expected one."""
    diffs = []
    for name, differ in (
        ("prepared.csv", diff_prepared),
        ("summary.json", diff_summary),
        ("config.yaml", diff_config),
    ):
        if not (actual_dir / name).is_file():
            diffs.append(f"{name} was not written")
            continue
        diffs.extend(differ(actual_dir / name, expected_dir / name))
    return diffs


def compare_result(exit_code: int, stderr: str, output_dir: Path, expected_dir: Path) -> list[str]:
    """Compare one converter execution with a fixture's expectation.

    A fixture with expected/error.txt expects the converter to stop: a non-zero
    exit, no prepared.csv, and each line of error.txt somewhere in stderr.
    """
    error_file = expected_dir / "error.txt"
    if error_file.exists():
        diffs = []
        if exit_code == 0:
            diffs.append("expected the converter to stop with an error, but it exited 0")
        if (output_dir / "prepared.csv").exists():
            diffs.append("expected no prepared.csv, because the deposit cannot be converted")
        for needle in error_file.read_text(encoding="utf-8").splitlines():
            if needle.strip() and needle.strip() not in stderr:
                diffs.append(f"expected the error message to mention {needle.strip()!r}")
        return diffs
    if exit_code != 0:
        return [f"converter exited {exit_code}; expected it to succeed"]
    return compare_outputs(output_dir, expected_dir)


def cell_agreement(actual: Path, expected: Path) -> tuple[int, int]:
    """Matching data cells out of all expected data cells, aligned on sample and column."""
    want = read_grid(expected)
    try:
        got = read_grid(actual)
    except (UnicodeDecodeError, csv.Error, FileNotFoundError):
        got = []
    if not want:
        return 0, 0
    header = want[0]
    got_columns = {name: i for i, name in enumerate(got[0])} if got else {}
    got_rows = {row[0]: row for row in got[2:] if row}
    matching = total = 0
    for row in want[2:]:
        for j, column in enumerate(header):
            total += 1
            other = got_rows.get(row[0])
            k = got_columns.get(column)
            if other is not None and k is not None and k < len(other) and other[k] == row[j]:
                matching += 1
    return matching, total
