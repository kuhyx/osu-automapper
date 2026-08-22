"""The ``sweep`` subcommand: argument handling, dry runs, and exit codes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from osu_automapper.cli import main
from osu_automapper.sweep.model import SweepGrid, SweepOutcome


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the whole package at a throwaway data root."""
    monkeypatch.setenv("OSU_AUTOMAPPER_DATA", str(tmp_path))
    (tmp_path / "songs").mkdir()
    (tmp_path / "songs" / "a.mp3").write_bytes(b"not really audio")
    return tmp_path


def test_dry_run_prints_the_grid_without_generating(
    data_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["sweep", "--dry-run", "--difficulties", "4", "--gamemodes", "0", "--seeds", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert "grid: 1 cells" in out
    assert "a_m0_d4_s1_base" in out
    assert not (data_root / "sweep").exists()


def test_missing_songs_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OSU_AUTOMAPPER_DATA", str(tmp_path))
    code = main(["sweep", "--dry-run"])
    assert code == 2
    assert "no songs" in capsys.readouterr().err


def test_adapters_always_include_the_base_model(
    data_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "sweep",
            "--dry-run",
            "--difficulties",
            "4",
            "--gamemodes",
            "0",
            "--seeds",
            "1",
            "--lora-paths",
            "/lora/checkpoint_11",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "grid: 2 cells" in out
    assert "_base" in out
    assert "_checkpoint_11" in out


def _stub_sweep(monkeypatch: pytest.MonkeyPatch, outcomes: list[SweepOutcome]) -> None:
    """Replace the real runner so the command can be tested without inference."""
    from osu_automapper import commands

    def fake(
        grid: SweepGrid,
        results_dir: Path,
        out_root: Path,
        on_result: Callable[[SweepOutcome], None] | None = None,
    ) -> list[SweepOutcome]:
        """Stand in for the real runner."""
        results_dir.mkdir(parents=True, exist_ok=True)
        for outcome in outcomes:
            if on_result is not None:
                on_result(outcome)
        return outcomes

    monkeypatch.setattr(commands, "run_sweep", fake)


def _outcome(
    *,
    label: str = "c",
    song: str = "a.mp3",
    difficulty: float = 4.0,
    mode: int = 0,
    seed: int = 1,
    adapter: str = "base",
    generated: bool = True,
    error: str = "",
    raw_passed: bool = True,
    repaired_passed: bool = True,
    repaired_failures: list[str] | None = None,
    repaired_stars: float | None = 5.0,
    objects_removed: int = 0,
    objects: int = 400,
) -> SweepOutcome:
    """Build an outcome, defaulting to a clean passing cell."""
    return SweepOutcome(
        label=label,
        song=song,
        difficulty=difficulty,
        mode=mode,
        seed=seed,
        adapter=adapter,
        generated=generated,
        error=error,
        raw_passed=raw_passed,
        repaired_passed=repaired_passed,
        repaired_failures=repaired_failures or [],
        repaired_stars=repaired_stars,
        objects_removed=objects_removed,
        objects=objects,
    )


def test_a_completed_sweep_writes_its_report_and_exits_zero(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_sweep(monkeypatch, [_outcome()])
    code = main(["sweep", "--difficulties", "4", "--gamemodes", "0", "--seeds", "1"])
    assert code == 0
    assert "# Reliability sweep" in (data_root / "sweep" / "REPORT.md").read_text()
    assert "pass" in capsys.readouterr().out


def test_a_failed_cell_makes_the_command_exit_one(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_sweep(monkeypatch, [_outcome(generated=False, repaired_passed=False)])
    code = main(["sweep", "--difficulties", "4", "--gamemodes", "0", "--seeds", "1"])
    assert code == 1
    assert "gen-fail" in capsys.readouterr().out


def test_a_gated_failure_is_reported_as_fail(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_sweep(monkeypatch, [_outcome(repaired_passed=False)])
    code = main(["sweep", "--difficulties", "4", "--gamemodes", "0", "--seeds", "1"])
    assert code == 0
    assert "FAIL" in capsys.readouterr().out


def test_the_report_path_can_be_chosen(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_sweep(monkeypatch, [_outcome()])
    target = tmp_path / "custom.md"
    code = main(
        [
            "sweep",
            "--difficulties",
            "4",
            "--gamemodes",
            "0",
            "--seeds",
            "1",
            "--report",
            str(target),
        ]
    )
    assert code == 0
    assert target.exists()


def test_explicit_songs_override_the_data_root(
    data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    song = tmp_path / "chosen.mp3"
    song.write_bytes(b"x")
    main(
        [
            "sweep",
            "--dry-run",
            "--difficulties",
            "4",
            "--gamemodes",
            "0",
            "--seeds",
            "1",
            "--songs",
            str(song),
        ]
    )
    assert "chosen_m0_d4_s1_base" in capsys.readouterr().out
