"""Tests for path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from osu_automapper.config import DEFAULT_DATA_ROOT, DEFAULT_MAPPERATORINATOR_HOME, Paths


def test_defaults_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAPPERATORINATOR_HOME", raising=False)
    monkeypatch.delenv("OSU_AUTOMAPPER_DATA", raising=False)
    paths = Paths.from_env()
    assert paths.mapperatorinator_home == DEFAULT_MAPPERATORINATOR_HOME
    assert paths.data_root == DEFAULT_DATA_ROOT


def test_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MAPPERATORINATOR_HOME", str(tmp_path / "upstream"))
    monkeypatch.setenv("OSU_AUTOMAPPER_DATA", str(tmp_path / "data"))
    paths = Paths.from_env()
    assert paths.mapperatorinator_home == tmp_path / "upstream"
    assert paths.data_root == tmp_path / "data"


def test_derived_paths(tmp_path: Path) -> None:
    paths = Paths(mapperatorinator_home=tmp_path / "up", data_root=tmp_path / "data")
    assert paths.python == tmp_path / "up" / ".venv" / "bin" / "python"
    assert paths.inference_script == tmp_path / "up" / "inference.py"
    assert paths.hf_home == tmp_path / "data" / "hf"
    assert paths.songs == tmp_path / "data" / "songs"
    assert paths.out == tmp_path / "data" / "out"
    assert paths.blindtest == tmp_path / "data" / "blindtest"
