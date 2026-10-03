"""The checked-in skills remain discoverable and their validator catches drift."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[1] / ".agents" / "skills"
spec = importlib.util.spec_from_file_location(
    "validate_repo_skills", SKILLS / "scripts" / "validate_skills.py"
)
assert spec is not None and spec.loader is not None
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def test_repository_skills_are_valid() -> None:
    count, problems = validator.validate(SKILLS)
    assert count > 0
    assert problems == []


@pytest.fixture
def skill_tree(tmp_path: Path) -> Path:
    directory = tmp_path / "testing-example"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        '---\nname: testing-example\ndescription: "Tests examples. Use for tests."\n'
        "---\n\n# Testing examples\n\nRead [notes](notes.md).\n"
    )
    (directory / "notes.md").write_text("# Notes\n")
    (tmp_path / "README.md").write_text("[Example](testing-example/SKILL.md)\n")
    return tmp_path


def test_validator_accepts_a_bundled_reference(skill_tree: Path) -> None:
    assert validator.validate(skill_tree) == (1, [])


def test_validator_accepts_a_docs_link_under_the_skills_tree(skill_tree: Path) -> None:
    docs = skill_tree / "docs"
    docs.mkdir()
    (docs / "policy.md").write_text("# Policy\n")
    skill = skill_tree / "testing-example" / "SKILL.md"
    skill.write_text(skill.read_text() + "\nRead [policy](../docs/policy.md).\n")
    assert validator.validate(skill_tree) == (1, [])


@pytest.mark.parametrize(
    ("frontmatter", "expected"),
    [
        ("name: another-name\ndescription: Example", "invalid or mismatched name"),
        ("name: testing-example\ndescription: 123", "invalid description"),
        ("[not, a, mapping]", "frontmatter must be a mapping"),
        ("name: [", "invalid YAML"),
        (
            "name: testing-example\ndescription: Example\nmcpServers: {}",
            "must not start MCP servers",
        ),
    ],
)
def test_validator_rejects_bad_frontmatter(
    skill_tree: Path, frontmatter: str, expected: str
) -> None:
    (skill_tree / "testing-example" / "SKILL.md").write_text(
        f"---\n{frontmatter}\n---\n\n# Example\n"
    )
    _, problems = validator.validate(skill_tree)
    assert any(expected in problem for problem in problems)


def test_validator_rejects_a_missing_reference(skill_tree: Path) -> None:
    (skill_tree / "testing-example" / "notes.md").unlink()
    _, problems = validator.validate(skill_tree)
    assert problems == ["testing-example/SKILL.md: disallowed or missing local link notes.md"]


def test_validator_rejects_a_link_outside_allowed_roots(skill_tree: Path) -> None:
    outside = skill_tree.parent / "outside.md"
    outside.write_text("# Outside\n")
    skill = skill_tree / "testing-example" / "SKILL.md"
    skill.write_text(skill.read_text() + f"\nRead [outside](../../{outside.name}).\n")
    _, problems = validator.validate(skill_tree)
    assert problems == [
        f"testing-example/SKILL.md: disallowed or missing local link ../../{outside.name}"
    ]


def test_validator_rejects_an_unindexed_skill(skill_tree: Path) -> None:
    (skill_tree / "README.md").write_text("# Empty index\n")
    _, problems = validator.validate(skill_tree)
    assert problems == ["testing-example/SKILL.md: not indexed in README.md"]


def test_validator_rejects_a_sibling_mcp_server(skill_tree: Path) -> None:
    (skill_tree / "testing-example" / "mcp.json").write_text("{}\n")
    _, problems = validator.validate(skill_tree)
    assert problems == ["testing-example/SKILL.md: this collection must not start MCP servers"]
