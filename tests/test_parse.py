"""Tests for the beatmap reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from osu_automapper.parse import (
    Beatmap,
    BeatmapParseError,
    HitObject,
    Mode,
    TimingPoint,
    _parse_hit_object,
    _parse_kv,
    _parse_timing_point,
    parse_beatmap,
)

from .conftest import MINIMAL_STD, _std_objects, write_map


def test_parses_valid_map(std_map: Path) -> None:
    beatmap = parse_beatmap(std_map)
    assert beatmap.format_version == 14
    assert beatmap.mode is Mode.STANDARD
    assert len(beatmap.hit_objects) == 80
    assert beatmap.audio_filename == "audio.mp3"
    assert beatmap.preview_time == 5000
    assert beatmap.circle_size == 4.0


def test_missing_header_raises(tmp_path: Path) -> None:
    path = write_map(tmp_path, "just some text\n")
    with pytest.raises(BeatmapParseError, match="missing 'osu file format'"):
        parse_beatmap(path)


def test_unreadable_path_raises(tmp_path: Path) -> None:
    with pytest.raises(BeatmapParseError, match="cannot read"):
        parse_beatmap(tmp_path / "absent.osu")


def test_unparseable_version_falls_back_to_zero(tmp_path: Path) -> None:
    path = write_map(tmp_path, "osu file format vXX\n\n[General]\nMode: 0\n")
    assert parse_beatmap(path).format_version == 0


def test_comments_and_blank_lines_ignored(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects(2))
    path = write_map(tmp_path, text.replace("[HitObjects]", "// a comment\n\n[HitObjects]"))
    assert len(parse_beatmap(path).hit_objects) == 2


def test_unknown_section_ignored(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects(2)) + "\n[Colours]\nCombo1 : 1,2,3\n"
    assert len(parse_beatmap(write_map(tmp_path, text)).hit_objects) == 2


def test_editor_section_is_parsed_without_error(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects(2)).replace(
        "[Metadata]", "[Editor]\nBeatDivisor: 4\n\n[Metadata]"
    )
    assert parse_beatmap(write_map(tmp_path, text)).mode is Mode.STANDARD


def test_malformed_lines_are_skipped(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects="garbage\n256,192,0,1,0:0:0:0:\n1,2")
    beatmap = parse_beatmap(write_map(tmp_path, text))
    assert len(beatmap.hit_objects) == 1


def test_kv_line_without_colon_skipped(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects(2)).replace(
        "[Metadata]", "[Metadata]\nnocolonhere\n"
    )
    assert parse_beatmap(write_map(tmp_path, text)).metadata["Title"] == "Test Song"


def test_invalid_mode_falls_back_to_standard(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects(2)).replace("Mode: 0", "Mode: abc")
    assert parse_beatmap(write_map(tmp_path, text)).mode is Mode.STANDARD


def test_invalid_preview_time_is_minus_one(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects(2)).replace(
        "PreviewTime: 5000", "PreviewTime: x"
    )
    assert parse_beatmap(write_map(tmp_path, text)).preview_time == -1


def test_invalid_circle_size_defaults(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects(2)).replace("CircleSize:4", "CircleSize:oops")
    assert parse_beatmap(write_map(tmp_path, text)).circle_size == 5.0


def test_parse_kv_returns_none_without_colon() -> None:
    assert _parse_kv("nocolon") is None


def test_parse_timing_point_variants() -> None:
    assert _parse_timing_point("1") is None
    assert _parse_timing_point("a,b") is None
    short = _parse_timing_point("0,500")
    assert short is not None and short.uninherited is True
    inherited = _parse_timing_point("0,-100,4,2,0,60,0,0")
    assert inherited is not None and inherited.uninherited is False


def test_parse_hit_object_variants() -> None:
    assert _parse_hit_object("1,2") is None
    assert _parse_hit_object("a,b,c,d") is None
    obj = _parse_hit_object("256,192,1000,1,0")
    assert obj is not None and obj.time == 1000


def test_timing_point_bpm() -> None:
    assert TimingPoint(0.0, 500.0, True).bpm == 120.0
    assert TimingPoint(0.0, -100.0, False).bpm is None
    assert TimingPoint(0.0, 0.0, True).bpm is None


def test_hit_object_type_flags() -> None:
    circle = HitObject(0, 0, 0, 1, "")
    slider = HitObject(0, 0, 0, 2, "")
    spinner = HitObject(0, 0, 0, 8, "0,0,0,8,0,5000")
    hold = HitObject(0, 0, 0, 128, "0,0,0,128,0,5000:0:0:0:0:")
    assert circle.is_circle and not circle.is_slider
    assert slider.is_slider
    assert spinner.is_spinner and spinner.end_time == 5000
    assert hold.is_hold and hold.end_time == 5000
    assert circle.end_time == 0


def test_hit_object_end_time_edge_cases() -> None:
    assert HitObject(0, 0, 7, 8, "0,0,7,8,0").end_time == 7
    assert HitObject(0, 0, 7, 8, "0,0,7,8,0,notanumber").end_time == 7


def test_drain_time_empty_map(tmp_path: Path) -> None:
    beatmap = Beatmap(path=tmp_path / "x.osu", format_version=14)
    assert beatmap.drain_time_seconds == 0.0
    assert beatmap.audio_filename == ""


def test_section_content_before_any_header_is_ignored(tmp_path: Path) -> None:
    """Lines before the first [Section] belong to no section and are dropped."""
    text = "osu file format v14\nstray line\n\n[General]\nMode: 0\n"
    assert parse_beatmap(write_map(tmp_path, text)).mode is Mode.STANDARD


def test_editor_keys_are_read_but_not_stored(tmp_path: Path) -> None:
    """[Editor] is a key/value section with no destination dict of its own."""
    text = MINIMAL_STD.format(objects=_std_objects(2)).replace(
        "[Metadata]", "[Editor]\nBeatDivisor: 4\nBookmarks: 1,2\n\n[Metadata]"
    )
    beatmap = parse_beatmap(write_map(tmp_path, text))
    assert "BeatDivisor" not in beatmap.general
    assert "BeatDivisor" not in beatmap.metadata
    assert "BeatDivisor" not in beatmap.difficulty
    assert beatmap.metadata["Title"] == "Test Song"


def test_content_in_unhandled_section_is_dropped(tmp_path: Path) -> None:
    """[Events] lines match no destination and must fall through harmlessly."""
    text = MINIMAL_STD.format(objects=_std_objects(2)).replace(
        "[TimingPoints]", '[Events]\n0,0,"bg.jpg",0,0\n2,100,200\n\n[TimingPoints]'
    )
    beatmap = parse_beatmap(write_map(tmp_path, text))
    assert len(beatmap.hit_objects) == 2
    assert len(beatmap.timing_points) == 1


def test_malformed_timing_point_line_is_skipped(tmp_path: Path) -> None:
    """A junk [TimingPoints] line is dropped without killing the parse."""
    text = MINIMAL_STD.format(objects=_std_objects(2)).replace(
        "0,500,4,2,0,60,1,0", "0,500,4,2,0,60,1,0\ngarbage timing line\nx,y"
    )
    beatmap = parse_beatmap(write_map(tmp_path, text))
    assert len(beatmap.timing_points) == 1
