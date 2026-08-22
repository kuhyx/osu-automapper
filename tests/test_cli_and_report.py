"""Tests for the report types, star-rating seam and CLI exit codes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from osu_automapper.cli import EXIT_ERROR, EXIT_FAILED, EXIT_OK, main
from osu_automapper.report import CheckResult, Report, Severity
from osu_automapper.stars import (
    RosuStarRating,
    StarRatingError,
    difficulty_within_tolerance,
)

from .conftest import MINIMAL_STD, _std_objects, write_map


class FakeRater:
    """Star-rating provider returning a fixed value."""

    def __init__(self, value: float) -> None:
        """Store the rating this provider will return."""
        self.value = value

    def rate(self, path: Path) -> float:
        """Return the canned rating."""
        return self.value


class FailingRater:
    """Star-rating provider that always fails."""

    def rate(self, path: Path) -> float:
        """Raise, to exercise the error branch."""
        raise StarRatingError("no rating available")


def test_check_result_blocking_semantics() -> None:
    assert CheckResult("a", False, "m").is_blocking
    assert not CheckResult("a", True, "m").is_blocking
    assert not CheckResult("a", False, "m", Severity.WARNING).is_blocking


def test_report_aggregates(tmp_path: Path) -> None:
    report = Report(path="x", mode=0)
    report.add(CheckResult("ok", True, "fine"))
    report.add(CheckResult("bad", False, "broken"))
    report.add(CheckResult("warn", False, "meh", Severity.WARNING))
    assert len(report.failures) == 1
    assert len(report.warnings) == 1
    assert not report.technically_rankable
    assert "NOT technically rankable" in report.to_text()


def test_report_json_roundtrip() -> None:
    report = Report(path="x", mode=3)
    report.add(CheckResult("ok", True, "fine"))
    payload = json.loads(report.to_json())
    assert payload["mode"] == 3
    assert payload["technically_rankable"] is True
    assert payload["results"][0]["name"] == "ok"


def test_difficulty_tolerance() -> None:
    assert difficulty_within_tolerance(5.4, 5.5)
    assert difficulty_within_tolerance(6.0, 5.5)
    assert not difficulty_within_tolerance(6.1, 5.5)


def test_cli_passes_valid_map(std_map: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", str(std_map)]) == EXIT_OK
    assert "technically rankable" in capsys.readouterr().out


def test_cli_fails_invalid_map(tmp_path: Path) -> None:
    path = write_map(tmp_path, MINIMAL_STD.format(objects=_std_objects(2)))
    assert main(["check", str(path)]) == EXIT_FAILED


def test_cli_parse_error_is_exit_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_map(tmp_path, "not a beatmap")
    assert main(["check", str(path)]) == EXIT_ERROR
    assert "error:" in capsys.readouterr().err


def test_cli_missing_file_is_exit_two(tmp_path: Path) -> None:
    assert main(["check", str(tmp_path / "nope.osu")]) == EXIT_ERROR


def test_cli_json_output(std_map: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", str(std_map), "--json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["technically_rankable"] is True


def test_cli_star_gate_within_tolerance(std_map: Path) -> None:
    assert main(["check", str(std_map), "--target-difficulty", "5.0"], FakeRater(5.2)) == EXIT_OK


def test_cli_star_gate_outside_tolerance(std_map: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["check", str(std_map), "--target-difficulty", "5.0"], FakeRater(9.0))
    assert code == EXIT_FAILED
    assert "9.00*" in capsys.readouterr().out


def test_cli_star_gate_custom_tolerance(std_map: Path) -> None:
    argv = ["check", str(std_map), "--target-difficulty", "5.0", "--tolerance", "4.0"]
    assert main(argv, FakeRater(9.0)) == EXIT_OK


def test_cli_star_gate_rater_failure(std_map: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["check", str(std_map), "--target-difficulty", "5.0"], FailingRater())
    assert code == EXIT_FAILED
    assert "no rating available" in capsys.readouterr().out


def test_cli_clock_rate_flag_accepted(std_map: Path) -> None:
    argv = ["check", str(std_map), "--target-difficulty", "5.0", "--clock-rate", "1.5"]
    assert main(argv, FakeRater(5.0)) == EXIT_OK


def test_rosu_rater_does_not_validate_input(tmp_path: Path) -> None:
    """rosu-pp returns a meaningless rating for junk rather than raising.

    This is why the CLI parses the map first: the star gate is only ever reached
    for a file that already parsed, so a bogus rating cannot be mistaken for one.
    """
    path = write_map(tmp_path, "not a beatmap at all")
    assert RosuStarRating().rate(path) >= 0.0


def test_rosu_rater_wraps_errors(tmp_path: Path) -> None:
    """A genuinely unreadable path surfaces as StarRatingError."""
    with pytest.raises(StarRatingError, match="cannot rate"):
        RosuStarRating().rate(tmp_path / "does_not_exist.osu")


def test_rosu_rater_rates_a_real_map(std_map: Path) -> None:
    assert RosuStarRating().rate(std_map) >= 0.0


def test_cli_check_osz_valid(tmp_path: Path) -> None:
    import zipfile

    path = tmp_path / "ok.osz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("map.osu", "osu file format v14\n\n[General]\nAudioFilename: s.mp3\n")
        archive.writestr("s.mp3", "audio")
    assert main(["check-osz", str(path)]) == EXIT_OK


def test_cli_check_osz_missing_audio(tmp_path: Path) -> None:
    import zipfile

    path = tmp_path / "bad.osz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("map.osu", "osu file format v14\n\n[General]\nAudioFilename: s.mp3\n")
    assert main(["check-osz", str(path)]) == EXIT_FAILED


def test_cli_check_osz_error(tmp_path: Path) -> None:
    assert main(["check-osz", str(tmp_path / "absent.osz")]) == EXIT_ERROR


def test_cli_check_osz_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import zipfile

    path = tmp_path / "ok.osz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("map.osu", "osu file format v14\n\n[General]\nAudioFilename: s.mp3\n")
        archive.writestr("s.mp3", "audio")
    assert main(["check-osz", str(path), "--json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["technically_rankable"] is True
