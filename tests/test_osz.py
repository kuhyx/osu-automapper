"""Tests for .osz archive validation."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from osu_automapper.osz import OszError, check_osz_importable, read_osz

BEATMAP = "osu file format v14\n\n[General]\nAudioFilename: song.mp3\n"


def _write_osz(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return path


def test_valid_archive_passes(tmp_path: Path) -> None:
    path = _write_osz(tmp_path / "ok.osz", {"map.osu": BEATMAP, "song.mp3": "audio"})
    assert all(r.passed for r in check_osz_importable(path))


def test_missing_audio_detected(tmp_path: Path) -> None:
    path = _write_osz(tmp_path / "bad.osz", {"map.osu": BEATMAP})
    results = {r.name: r for r in check_osz_importable(path)}
    assert not results["osz_audio_present"].passed
    assert "song.mp3" in results["osz_audio_present"].message


def test_archive_without_beatmap_detected(tmp_path: Path) -> None:
    path = _write_osz(tmp_path / "empty.osz", {"song.mp3": "audio"})
    results = {r.name: r for r in check_osz_importable(path)}
    assert not results["osz_has_beatmap"].passed


def test_beatmap_without_audio_line(tmp_path: Path) -> None:
    path = _write_osz(tmp_path / "noaudio.osz", {"map.osu": "osu file format v14\n"})
    results = {r.name: r for r in check_osz_importable(path)}
    assert results["osz_audio_present"].passed


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(OszError, match="no such archive"):
        read_osz(tmp_path / "absent.osz")


def test_non_zip_raises(tmp_path: Path) -> None:
    path = tmp_path / "junk.osz"
    path.write_text("not a zip")
    with pytest.raises(OszError, match="not a valid zip"):
        read_osz(path)
