"""Validate the repository's portable, instructions-only skill collection."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _allowed_link_target(resolved: Path, skills_root: Path) -> bool:
    if not resolved.exists():
        return False
    skills_root = skills_root.resolve()
    resolved = resolved.resolve()
    try:
        resolved.relative_to(skills_root)
        return True
    except ValueError:
        pass
    try:
        relative = resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    return bool(relative.parts) and relative.parts[0] == "docs"


def validate(root: Path) -> tuple[int, list[str]]:
    problems: list[str] = []
    skills = sorted(root.glob("*/SKILL.md"))
    readme = root / "README.md"
    if not skills:
        problems.append("No skills found")
    if not readme.is_file():
        problems.append("Missing README.md")
    index = readme.read_text() if readme.is_file() else ""
    for path in skills:
        label = str(path.relative_to(root))
        text = path.read_text()
        parts = text.split("---\n", 2)
        if not text.startswith("---\n") or len(parts) != 3:
            problems.append(f"{label}: missing frontmatter")
            continue
        try:
            data = yaml.safe_load(parts[1])
        except yaml.YAMLError as error:
            problems.append(f"{label}: invalid YAML: {error}")
            continue
        if not isinstance(data, dict):
            problems.append(f"{label}: frontmatter must be a mapping")
            continue
        name = data.get("name")
        if (
            not isinstance(name, str)
            or not NAME.fullmatch(name)
            or len(name) > 64
            or name != path.parent.name
        ):
            problems.append(f"{label}: invalid or mismatched name")
        description = data.get("description")
        if not isinstance(description, str) or not 1 <= len(description) <= 1024:
            problems.append(f"{label}: invalid description")
        if len(text.splitlines()) >= 500:
            problems.append(f"{label}: skill must be under 500 lines")
        if "mcpServers" in data or (path.parent / "mcp.json").exists():
            problems.append(f"{label}: this collection must not start MCP servers")
        if f"({label})" not in index:
            problems.append(f"{label}: not indexed in README.md")
    for path in sorted(root.rglob("*.md")):
        if ".git" in path.relative_to(root).parts:
            continue
        for target in LINK.findall(path.read_text()):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            resolved = (path.parent / unquote(parsed.path)).resolve()
            if not _allowed_link_target(resolved, root):
                problems.append(
                    f"{path.relative_to(root)}: disallowed or missing local link {target}"
                )
    return len(skills), problems


if __name__ == "__main__":
    count, problems = validate(ROOT)
    for problem in problems:
        print(problem)
    if problems:
        sys.exit(1)
    print(f"Validated {count} skills: no problems")
