"""Tests for the standard and mania check suites, and the mode registry."""

from __future__ import annotations

from pathlib import Path

from osu_automapper.checks import checks_for, run_checks
from osu_automapper.checks.mania import (
    check_columns_in_range,
    check_hold_notes_ordered,
    check_keycount_sane,
    check_no_column_collisions,
    column_of,
)
from osu_automapper.checks.standard import (
    check_no_simultaneous_objects,
    check_object_gaps,
    check_positions_in_playfield,
    check_slider_velocity_finite,
)
from osu_automapper.parse import Beatmap, Mode, parse_beatmap

from .conftest import MINIMAL_MANIA, MINIMAL_STD, _mania_objects, _std_objects, write_map


def _map(tmp_path: Path, text: str) -> Beatmap:
    return parse_beatmap(write_map(tmp_path, text))


def test_standard_checks_pass_on_valid_map(std_map: Path) -> None:
    beatmap = parse_beatmap(std_map)
    for check in (
        check_positions_in_playfield,
        check_no_simultaneous_objects,
        check_object_gaps,
        check_slider_velocity_finite,
    ):
        assert check(beatmap).passed, check.__name__


def test_offscreen_object_detected(tmp_path: Path) -> None:
    objects = _std_objects(80) + "\n9999,192,40500,1,0,0:0:0:0:"
    assert not check_positions_in_playfield(
        _map(tmp_path, MINIMAL_STD.format(objects=objects))
    ).passed


def test_spinner_exempt_from_playfield(tmp_path: Path) -> None:
    objects = _std_objects(80) + "\n9999,9999,40500,8,0,41000"
    assert check_positions_in_playfield(_map(tmp_path, MINIMAL_STD.format(objects=objects))).passed


def test_simultaneous_objects_detected(tmp_path: Path) -> None:
    objects = _std_objects(80) + "\n300,192,39500,1,0,0:0:0:0:"
    assert not check_no_simultaneous_objects(
        _map(tmp_path, MINIMAL_STD.format(objects=objects))
    ).passed


def test_object_gap_too_small_after_circle(tmp_path: Path) -> None:
    objects = _std_objects(80) + "\n256,192,39505,1,0,0:0:0:0:"
    assert not check_object_gaps(_map(tmp_path, MINIMAL_STD.format(objects=objects))).passed


def test_object_gap_too_small_after_slider(tmp_path: Path) -> None:
    objects = "256,192,0,2,0,P|300:300|320:320,1,100\n256,192,15,1,0,0:0:0:0:\n" + _std_objects(
        80, 500
    )
    assert not check_object_gaps(_map(tmp_path, MINIMAL_STD.format(objects=objects))).passed


def test_slider_multiplier_invalid(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace(
        "SliderMultiplier:1.4", "SliderMultiplier:abc"
    )
    assert not check_slider_velocity_finite(_map(tmp_path, text)).passed


def test_slider_multiplier_nonpositive(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace(
        "SliderMultiplier:1.4", "SliderMultiplier:0"
    )
    assert not check_slider_velocity_finite(_map(tmp_path, text)).passed


def test_slider_multiplier_infinite(tmp_path: Path) -> None:
    text = MINIMAL_STD.format(objects=_std_objects()).replace(
        "SliderMultiplier:1.4", "SliderMultiplier:inf"
    )
    assert not check_slider_velocity_finite(_map(tmp_path, text)).passed


def test_mania_checks_pass_on_valid_map(mania_map: Path) -> None:
    beatmap = parse_beatmap(mania_map)
    for check in (
        check_keycount_sane,
        check_columns_in_range,
        check_hold_notes_ordered,
        check_no_column_collisions,
    ):
        assert check(beatmap).passed, check.__name__


def test_column_of_maps_x_to_columns() -> None:
    assert column_of(64, 4) == 0
    assert column_of(448, 4) == 3
    assert column_of(0, 0) == -1


def test_keycount_invalid(tmp_path: Path) -> None:
    text = MINIMAL_MANIA.format(objects=_mania_objects()).replace("CircleSize:4", "CircleSize:4.5")
    assert not check_keycount_sane(_map(tmp_path, text)).passed


def test_keycount_out_of_range(tmp_path: Path) -> None:
    text = MINIMAL_MANIA.format(objects=_mania_objects()).replace("CircleSize:4", "CircleSize:99")
    assert not check_keycount_sane(_map(tmp_path, text)).passed


def test_column_out_of_range_detected(tmp_path: Path) -> None:
    objects = _mania_objects() + "\n99999,192,40500,1,0,0:0:0:0:"
    assert not check_columns_in_range(_map(tmp_path, MINIMAL_MANIA.format(objects=objects))).passed


def test_column_checks_fail_on_zero_keycount(tmp_path: Path) -> None:
    text = MINIMAL_MANIA.format(objects=_mania_objects()).replace("CircleSize:4", "CircleSize:0")
    assert not check_columns_in_range(_map(tmp_path, text)).passed
    assert not check_no_column_collisions(_map(tmp_path, text)).passed


def test_bad_hold_note_detected(tmp_path: Path) -> None:
    objects = _mania_objects() + "\n64,192,40500,128,0,40000:0:0:0:0:"
    assert not check_hold_notes_ordered(
        _map(tmp_path, MINIMAL_MANIA.format(objects=objects))
    ).passed


def test_column_collision_detected(tmp_path: Path) -> None:
    objects = _mania_objects() + "\n64,192,0,1,0,0:0:0:0:"
    assert not check_no_column_collisions(
        _map(tmp_path, MINIMAL_MANIA.format(objects=objects))
    ).passed


def test_mania_allows_simultaneous_notes_in_different_columns(mania_map: Path) -> None:
    """A mania jump is legal; the standard collision rule must not apply to it."""
    beatmap = parse_beatmap(mania_map)
    assert check_no_column_collisions(beatmap).passed


def test_registry_dispatches_by_mode() -> None:
    assert checks_for(Mode.STANDARD) != checks_for(Mode.MANIA)
    assert len(checks_for(Mode.TAIKO)) < len(checks_for(Mode.STANDARD))
    assert len(checks_for(Mode.CATCH)) == len(checks_for(Mode.TAIKO))


def test_run_checks_builds_report(std_map: Path, mania_map: Path) -> None:
    std_report = run_checks(parse_beatmap(std_map))
    assert std_report.mode == 0 and std_report.technically_rankable
    mania_report = run_checks(parse_beatmap(mania_map))
    assert mania_report.mode == 3 and mania_report.technically_rankable
