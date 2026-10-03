"""Every fixture has its inputs and either expected outputs or an expected error."""

from __future__ import annotations

import json

import pytest
import yaml

from onboard.fixtures import INPUT_FILES, list_fixtures

ALL = list_fixtures("dev") + list_fixtures("heldout")


def test_fixture_sets_match_the_spec():
    assert [f.id for f in list_fixtures("dev")] == ["D1", "D2", "D3", "D4"]
    assert [f.id for f in list_fixtures("heldout")] == ["H1", "H2", "H3", "H4", "H5"]


@pytest.mark.parametrize("fixture", ALL, ids=[f.id for f in ALL])
def test_fixture_loads(fixture):
    for name in INPUT_FILES:
        assert (fixture.directory / name).is_file(), name
    json.loads(fixture.factors.read_text())
    json.loads(fixture.data.read_text())
    task = yaml.safe_load(fixture.task.read_text())
    assert task["phenotype_key"]
    if fixture.expects_error:
        assert not (fixture.expected / "prepared.csv").exists()
    else:
        for name in ("prepared.csv", "summary.json", "config.yaml"):
            assert (fixture.expected / name).is_file(), name
