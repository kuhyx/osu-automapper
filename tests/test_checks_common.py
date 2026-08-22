"""Tests for the mode-independent checks."""

from __future__ import annotations

from pathlib import Path

from osu_automapper.checks.common import (
    check_audio_filename,
    check_drain_time,
    check_has_objects,
    check_has_uninherited_timing,
    check_inherited_after_uninherited,
    check_metadata_present,
    check_no_duplicate_timing_points,
    check_objects_snapped,
    check_preview_time,
)
from osu_automapper.parse import Beatmap, parse_beatmap
from osu_automapper.report import Severity

from .conftest import MINIMAL_STD, _std_objects, write_map


def _map(tmp_path: Path, text: str) -> Beatmap:
    return parse_beatmap(write_map(tmp_path, text))


def test_all_common_checks_pass_on_valid_map(std_map: Path) -> None:
    beatmap = parse_beatmap(std_map)
    for check in (
        check_has_objects,
        check_drain_time,
        check_metadata_present,
        check_audio_filename,
        check_preview_time,
        check_has_uninherited_timing,
        check_no_duplicate_timing_points,
        check_inherited_after_uninherited,
        check_objects_snapped,
    ):
        assert check(beatmap).passed, check.__name__


def test_has_objects_fails_when_empty(tmp_path: Path) -> None:
    assert not check_has_objects(_map(tmp_path, MINIMAL_STD.format(objects=""))).passed


def test_drain_time_fails_when_short(tmp_path: Path) -> None:
    assert not check_drain_time(_map(tmp_path, MINIMAL_STD.format(objects=_std_objects(3)))).passed


def test_metadata_fails_when_blank(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace("Title:Test Song", "Title:")
    result = check_metadata_present(_map(tmp_path, text))
    assert not result.passed and "Title" in result.message


def test_metadata_fails_on_model_placeholder(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace(
        "Title:Test Song", "Title:Unknown Title"
    )
    assert not check_metadata_present(_map(tmp_path, text)).passed


def test_audio_filename_missing_and_illegal(tmp_path: Path) -> None:
    base = MINIMAL_STD.format(objects=_std_objects())
    unset = base.replace("AudioFilename: audio.mp3", "AudioFilename:")
    assert not check_audio_filename(_map(tmp_path, unset)).passed
    wav = base.replace("audio.mp3", "audio.wav")
    assert not check_audio_filename(_map(tmp_path, wav)).passed


def test_preview_time_unset_fails(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace(
        "PreviewTime: 5000", "PreviewTime: -1"
    )
    assert not check_preview_time(_map(tmp_path, text)).passed


def test_uninherited_timing_required(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace(
        "0,500,4,2,0,60,1,0", "0,-100,4,2,0,60,0,0"
    )
    assert not check_has_uninherited_timing(_map(tmp_path, text)).passed


def test_duplicate_timing_points_detected(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace(
        "0,500,4,2,0,60,1,0", "0,500,4,2,0,60,1,0\n0,400,4,2,0,60,1,0"
    )
    assert not check_no_duplicate_timing_points(_map(tmp_path, text)).passed


def test_duplicate_inherited_points_detected(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace(
        "0,500,4,2,0,60,1,0",
        "0,500,4,2,0,60,1,0\n100,-100,4,2,0,60,0,0\n100,-50,4,2,0,60,0,0",
    )
    assert not check_no_duplicate_timing_points(_map(tmp_path, text)).passed


def test_inherited_before_uninherited_detected(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace(
        "0,500,4,2,0,60,1,0", "500,500,4,2,0,60,1,0\n100,-100,4,2,0,60,0,0"
    )
    assert not check_inherited_after_uninherited(_map(tmp_path, text)).passed


def test_inherited_ordering_without_uninherited_fails(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace(
        "0,500,4,2,0,60,1,0", "0,-100,4,2,0,60,0,0"
    )
    assert not check_inherited_after_uninherited(_map(tmp_path, text)).passed


def test_unsnapped_object_detected(tmp_path: Path) -> None:
    objects = _std_objects(80) + "\n256,192,40007,1,0,0:0:0:0:"
    assert not check_objects_snapped(_map(tmp_path, MINIMAL_STD.format(objects=objects))).passed


def test_triplet_snapping_accepted(tmp_path: Path) -> None:
    """1/12 of a 500 ms beat is 41.667 ms: legal, and must not be reported."""
    objects = _std_objects(80) + "\n256,192,42,1,0,0:0:0:0:"
    assert check_objects_snapped(_map(tmp_path, MINIMAL_STD.format(objects=objects))).passed


def test_object_before_first_red_line_is_unsnapped(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects="256,192,100,1,0,0:0:0:0:\n" + _std_objects(80)).replace(
        "0,500,4,2,0,60,1,0", "500,500,4,2,0,60,1,0"
    )
    assert not check_objects_snapped(_map(tmp_path, text)).passed


def test_snap_check_warns_without_timing(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace("0,500,4,2,0,60,1,0", "")
    result = check_objects_snapped(_map(tmp_path, text))
    assert not result.passed and result.severity is Severity.WARNING and not result.is_blocking


def test_snap_check_skips_nonpositive_beat_length(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace(
        "0,500,4,2,0,60,1,0", "0,0,4,2,0,60,1,0"
    )
    assert check_objects_snapped(_map(tmp_path, text)).passed


def test_snap_check_uses_latest_applicable_timing_point(tmp_path: Path) -> None:
    """An object after a second red line must snap against that later point."""
    text = MINIMAL_STD.format(objects=_std_objects(80) + "\n256,192,40600,1,0,0:0:0:0:").replace(
        "0,500,4,2,0,60,1,0", "0,500,4,2,0,60,1,0\n40000,400,4,2,0,60,1,0"
    )
    assert check_objects_snapped(_map(tmp_path, text)).passed
