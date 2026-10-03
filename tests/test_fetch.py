"""`onboard fetch` freezes a deposit and records its source and hashes."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest

from onboard.fetch import FetchError, fetch_study, verify_frozen

BODIES = {
    "factors": b'{"1": {"local_sample_id": "01", "factors": "Group:a"}}',
    "data": b'{"1": {"analysis_id": "AN000001", "metabolite_name": "x", "DATA": {"01": "1"}}}',
    "summary": b'{"study_id": "ST000123", "study_title": "t", "license": "CC BY 4.0"}',
}


def opener(url: str) -> bytes:
    return BODIES[url.rsplit("/", 1)[1]]


def fixed_now() -> datetime:
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_fetch_writes_raw_files_and_records_hashes(tmp_path):
    record = fetch_study("ST000123", root=tmp_path, opener=opener, now=fixed_now)

    for part, body in BODIES.items():
        assert (tmp_path / "data" / "raw" / "ST000123" / f"{part}.json").read_bytes() == body
    sources = json.loads((tmp_path / "data" / "SOURCES.json").read_text())
    assert sources["studies"]["ST000123"] == record
    assert record["licence"] == "CC BY 4.0"
    assert record["retrieved_at"] == "2026-01-02T03:04:05+00:00"
    by_path = {entry["path"]: entry for entry in record["files"]}
    assert by_path["factors.json"]["sha256"] == hashlib.sha256(BODIES["factors"]).hexdigest()
    assert by_path["data.json"]["url"] == (
        "https://www.metabolomicsworkbench.org/rest/study/study_id/ST000123/data"
    )
    assert by_path["summary.json"]["bytes"] == len(BODIES["summary"])
    assert verify_frozen("ST000123", root=tmp_path) == []


def test_verify_frozen_reports_a_changed_file(tmp_path):
    fetch_study("ST000123", root=tmp_path, opener=opener, now=fixed_now)
    (tmp_path / "data" / "raw" / "ST000123" / "data.json").write_text("{}")

    problems = verify_frozen("ST000123", root=tmp_path)

    assert len(problems) == 1
    assert "data.json" in problems[0]


def test_verify_frozen_reports_an_unfetched_study(tmp_path):
    assert "not recorded" in verify_frozen("ST000999", root=tmp_path)[0]


@pytest.mark.parametrize("study_id", ["123", "ST12", "ST000123/../x"])
def test_fetch_rejects_malformed_study_ids(tmp_path, study_id):
    with pytest.raises(FetchError):
        fetch_study(study_id, root=tmp_path, opener=opener)


def test_fetch_rejects_a_non_json_response(tmp_path):
    with pytest.raises(FetchError, match="did not return JSON"):
        fetch_study("ST000123", root=tmp_path, opener=lambda url: b"<html>")
