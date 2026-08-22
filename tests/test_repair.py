"""Tests for artifact repair."""

from __future__ import annotations

from pathlib import Path

import pytest

from osu_automapper.cli import main
from osu_automapper.repair import RepairError, repair_file, repair_text

HEAD = """osu file format v14

[General]
AudioFilename: a.mp3

[HitObjects]
"""


def _map(objects: list[str]) -> str:
    return HEAD + "\n".join(objects) + "\n"


def test_strips_stacked_zero_cluster() -> None:
    text = _map(["256,192,0,1,0", "300,200,0,1,0", "256,192,13947,1,0", "260,190,14113,1,0"])
    repaired, result = repair_text(text)
    assert result.removed == 2
    assert result.first_real_time == 13947
    assert result.changed
    assert ",0,1,0" not in repaired.split("[HitObjects]")[1]


def test_leaves_single_object_at_zero_alone() -> None:
    """One object at 0 is a legitimate map start, not the artifact signature."""
    text = _map(["256,192,0,1,0", "256,192,500,1,0"])
    _, result = repair_text(text)
    assert not result.changed
    assert result.first_real_time == 500


def test_leaves_healthy_map_untouched() -> None:
    text = _map(["256,192,1000,1,0", "256,192,1500,1,0"])
    repaired, result = repair_text(text)
    assert not result.changed
    assert repaired == text


def test_map_with_only_zero_objects_is_not_stripped() -> None:
    """With no later objects there is no evidence of an artifact."""
    text = _map(["256,192,0,1,0", "300,200,0,1,0"])
    _, result = repair_text(text)
    assert not result.changed
    assert result.first_real_time is None


def test_malformed_object_lines_are_ignored() -> None:
    """Both shapes of junk: too few fields, and a non-numeric timestamp."""
    text = _map(
        [
            "garbage",
            "256,192,notatime,1,0",
            "256,192,0,1,0",
            "300,200,0,1,0",
            "256,192,9000,1,0",
        ]
    )
    _, result = repair_text(text)
    assert result.removed == 2


def test_missing_hitobjects_section_raises() -> None:
    with pytest.raises(RepairError, match="no \\[HitObjects\\]"):
        repair_text("osu file format v14\n\n[General]\n")


def test_repair_file_in_place(tmp_path: Path) -> None:
    path = tmp_path / "m.osu"
    path.write_text(_map(["1,1,0,1,0", "2,2,0,1,0", "3,3,5000,1,0"]))
    result = repair_file(path)
    assert result.removed == 2
    assert ",0,1,0" not in path.read_text().split("[HitObjects]")[1]


def test_repair_file_to_output(tmp_path: Path) -> None:
    source = tmp_path / "m.osu"
    source.write_text(_map(["1,1,0,1,0", "2,2,0,1,0", "3,3,5000,1,0"]))
    original = source.read_text()
    destination = tmp_path / "out.osu"
    assert repair_file(source, destination).removed == 2
    assert source.read_text() == original
    assert destination.exists()


def test_repair_file_output_written_even_when_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "m.osu"
    source.write_text(_map(["1,1,1000,1,0"]))
    destination = tmp_path / "copy.osu"
    assert not repair_file(source, destination).changed
    assert destination.read_text() == source.read_text()


def test_repair_file_unreadable_raises(tmp_path: Path) -> None:
    with pytest.raises(RepairError, match="cannot read"):
        repair_file(tmp_path / "absent.osu")


def test_cli_repair_changed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "m.osu"
    path.write_text(_map(["1,1,0,1,0", "2,2,0,1,0", "3,3,5000,1,0"]))
    assert main(["repair", str(path)]) == 0
    assert "removed 2 object(s)" in capsys.readouterr().out


def test_cli_repair_unchanged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "m.osu"
    path.write_text(_map(["1,1,1000,1,0"]))
    assert main(["repair", str(path)]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_cli_repair_with_output(tmp_path: Path) -> None:
    source = tmp_path / "m.osu"
    source.write_text(_map(["1,1,0,1,0", "2,2,0,1,0", "3,3,5000,1,0"]))
    destination = tmp_path / "out.osu"
    assert main(["repair", str(source), "--output", str(destination)]) == 0
    assert destination.exists()


def test_cli_repair_error(tmp_path: Path) -> None:
    assert main(["repair", str(tmp_path / "absent.osu")]) == 2
