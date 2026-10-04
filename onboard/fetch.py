"""`onboard fetch`: download and freeze one Workbench deposit (spec section 5.1).

The agent never runs this. It writes the raw files to data/raw/<ST>/ (git-ignored)
and records where they came from, when, and their hashes in data/SOURCES.json.
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from onboard.config import ROOT
from onboard.hashing import sha256_bytes, sha256_file

URL = "https://www.metabolomicsworkbench.org/rest/study/study_id/{study_id}/{part}"
PARTS = ("factors", "data", "summary")
STUDY_ID = re.compile(r"^ST\d{6}$")

Opener = Callable[[str], bytes]


class FetchError(RuntimeError):
    pass


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "study-onboarding-agent"})
    with urllib.request.urlopen(request, timeout=120) as response:
        body: bytes = response.read()
        return body


def _licence(summary: Any) -> str | None:
    if isinstance(summary, dict):
        for key in ("license", "licence"):
            if summary.get(key):
                return str(summary[key])
    return None


def raw_dir(study_id: str, root: Path = ROOT) -> Path:
    return root / "data" / "raw" / study_id


def load_sources(root: Path = ROOT) -> dict[str, Any]:
    path = root / "data" / "SOURCES.json"
    if not path.exists():
        return {"studies": {}}
    sources: dict[str, Any] = json.loads(path.read_text())
    return sources


def fetch_study(
    study_id: str,
    root: Path = ROOT,
    opener: Opener = _download,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Download the three endpoints, write them, and record them in SOURCES.json."""
    if not STUDY_ID.fullmatch(study_id):
        raise FetchError(f"study ID must look like ST000123, not {study_id!r}")
    target = raw_dir(study_id, root)
    target.mkdir(parents=True, exist_ok=True)
    retrieved_at = now().isoformat(timespec="seconds")
    files = []
    summary: Any = None
    for part in PARTS:
        url = URL.format(study_id=study_id, part=part)
        body = opener(url)
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as error:
            raise FetchError(f"{url} did not return JSON: {error}") from None
        if not parsed:
            raise FetchError(f"{url} returned an empty response")
        if part == "summary":
            summary = parsed
        path = target / f"{part}.json"
        path.write_bytes(body)
        files.append(
            {
                "path": f"{part}.json",
                "url": url,
                "bytes": len(body),
                "sha256": sha256_bytes(body),
                "retrieved_at": retrieved_at,
            }
        )
    record = {"retrieved_at": retrieved_at, "licence": _licence(summary), "files": files}
    sources = load_sources(root)
    sources.setdefault("studies", {})[study_id] = record
    sources_path = root / "data" / "SOURCES.json"
    sources_path.parent.mkdir(parents=True, exist_ok=True)
    sources_path.write_text(json.dumps(sources, indent=2, sort_keys=True) + "\n")
    return record


def verify_frozen(study_id: str, root: Path = ROOT) -> list[str]:
    """Problems with the frozen copy: missing files or hashes that differ from SOURCES.json."""
    record = load_sources(root).get("studies", {}).get(study_id)
    if record is None:
        return [f"{study_id} is not recorded in data/SOURCES.json; run `onboard fetch {study_id}`"]
    problems = []
    for entry in record["files"]:
        path = raw_dir(study_id, root) / entry["path"]
        if not path.exists():
            problems.append(f"{path} is missing")
        elif sha256_file(path) != entry["sha256"]:
            problems.append(f"{path} does not match the hash recorded when it was fetched")
    return problems
