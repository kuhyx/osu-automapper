"""Sweep execution: resumption, double gating, and failure handling.

No GPU and no real inference: the generator is injected, so every branch of the
runner is exercised by writing files the way upstream would.
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from osu_automapper.generate import GenerationError, GenerationRequest
from osu_automapper.parse import Mode
from osu_automapper.stars import StarRatingError
from osu_automapper.sweep.model import SweepGrid, SweepOutcome
from osu_automapper.sweep.runner import SweepError, run_sweep
from tests.conftest import MINIMAL_STD, _std_objects


class FakeRating:
    """Deterministic star rating."""

    def __init__(self, value: float = 4.2, fail: bool = False) -> None:
        """Rate every map ``value``, or fail when ``fail`` is set."""
        self.value = value
        self.fail = fail

    def rate(self, path: Path) -> float:
        """Return the fixed rating, or raise."""
        if self.fail:
            raise StarRatingError("no rating")
        return self.value


def _map_text(*, stacked_at_zero: int = 0) -> str:
    objects = _std_objects()
    if stacked_at_zero:
        prefix = "\n".join("256,192,0,1,0,0:0:0:0:" for _ in range(stacked_at_zero))
        objects = prefix + "\n" + objects
    return MINIMAL_STD.format(objects=objects)


def _writer(text: str, *, as_osz: bool = False) -> Callable[[GenerationRequest], Path]:
    """Build a generator that writes ``text`` where upstream would."""

    def generate(request: GenerationRequest) -> Path:
        request.output_path.mkdir(parents=True, exist_ok=True)
        if as_osz:
            archive = request.output_path / "out.osz"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("beatmap.osu", text)
        else:
            (request.output_path / "beatmap.osu").write_text(text, encoding="utf-8")
        return request.output_path

    return generate


def _grid() -> SweepGrid:
    return SweepGrid(songs=[Path("song.mp3")], difficulties=[4.0], modes=[Mode.STANDARD], seeds=[1])


def test_clean_output_passes_both_gates(tmp_path: Path) -> None:
    outcomes = run_sweep(
        _grid(),
        tmp_path / "results",
        tmp_path / "out",
        generator=_writer(_map_text()),
        provider=FakeRating(),
    )
    assert len(outcomes) == 1
    assert outcomes[0].generated is True
    assert outcomes[0].raw_passed is True
    assert outcomes[0].repaired_passed is True
    assert outcomes[0].defect_fired is False
    assert outcomes[0].objects > 0


def test_the_t_zero_defect_shows_up_as_raw_fail_and_repaired_pass(tmp_path: Path) -> None:
    outcomes = run_sweep(
        _grid(),
        tmp_path / "results",
        tmp_path / "out",
        generator=_writer(_map_text(stacked_at_zero=5)),
        provider=FakeRating(),
    )
    outcome = outcomes[0]
    # Six, not five: the baseline fixture's own first object also sits at t=0.
    assert outcome.objects_removed == 6
    assert outcome.defect_fired is True
    assert outcome.raw_passed is False
    assert outcome.repaired_passed is True


def test_output_is_found_inside_an_osz(tmp_path: Path) -> None:
    outcomes = run_sweep(
        _grid(),
        tmp_path / "results",
        tmp_path / "out",
        generator=_writer(_map_text(), as_osz=True),
        provider=FakeRating(),
    )
    assert outcomes[0].generated is True


def test_results_are_written_per_cell_and_reused_on_resume(tmp_path: Path) -> None:
    calls: list[str] = []

    def counting(request: GenerationRequest) -> Path:
        calls.append(request.output_path.name)
        return _writer(_map_text())(request)

    results = tmp_path / "results"
    run_sweep(_grid(), results, tmp_path / "out", generator=counting, provider=FakeRating())
    assert len(list(results.glob("*.json"))) == 1
    assert len(calls) == 1

    # Second pass must reuse the file rather than regenerate.
    outcomes = run_sweep(
        _grid(), results, tmp_path / "out", generator=counting, provider=FakeRating()
    )
    assert len(calls) == 1
    assert outcomes[0].generated is True


def test_generation_failure_is_recorded_not_raised(tmp_path: Path) -> None:
    def failing(request: GenerationRequest) -> Path:
        raise GenerationError("cuda oom")

    outcomes = run_sweep(
        _grid(), tmp_path / "results", tmp_path / "out", generator=failing, provider=FakeRating()
    )
    assert outcomes[0].generated is False
    assert "cuda oom" in outcomes[0].error


def test_missing_output_is_recorded_as_an_error(tmp_path: Path) -> None:
    def empty(request: GenerationRequest) -> Path:
        request.output_path.mkdir(parents=True, exist_ok=True)
        return request.output_path

    outcomes = run_sweep(
        _grid(), tmp_path / "results", tmp_path / "out", generator=empty, provider=FakeRating()
    )
    assert outcomes[0].generated is False
    assert "no .osu" in outcomes[0].error


def test_an_osz_without_a_beatmap_is_an_error(tmp_path: Path) -> None:
    def bad_osz(request: GenerationRequest) -> Path:
        request.output_path.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(request.output_path / "out.osz", "w") as zf:
            zf.writestr("readme.txt", "nothing here")
        return request.output_path

    outcomes = run_sweep(
        _grid(), tmp_path / "results", tmp_path / "out", generator=bad_osz, provider=FakeRating()
    )
    assert outcomes[0].generated is False
    assert "no .osu inside" in outcomes[0].error


def test_unparseable_output_is_recorded(tmp_path: Path) -> None:
    outcomes = run_sweep(
        _grid(),
        tmp_path / "results",
        tmp_path / "out",
        generator=_writer("not a beatmap at all"),
        provider=FakeRating(),
    )
    assert outcomes[0].generated is True
    assert outcomes[0].error != ""


def test_a_rating_failure_leaves_stars_unset_without_failing_the_cell(tmp_path: Path) -> None:
    outcomes = run_sweep(
        _grid(),
        tmp_path / "results",
        tmp_path / "out",
        generator=_writer(_map_text()),
        provider=FakeRating(fail=True),
    )
    assert outcomes[0].raw_stars is None
    assert outcomes[0].repaired_stars is None
    assert outcomes[0].repaired_passed is True


def test_progress_callback_fires_once_per_new_cell(tmp_path: Path) -> None:
    seen: list[SweepOutcome] = []
    run_sweep(
        _grid(),
        tmp_path / "results",
        tmp_path / "out",
        generator=_writer(_map_text()),
        provider=FakeRating(),
        on_result=seen.append,
    )
    assert len(seen) == 1


def test_repair_error_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from osu_automapper.repair import RepairError
    from osu_automapper.sweep import runner

    def boom(path: Path, output: Path | None = None) -> None:
        raise RepairError("unwritable")

    monkeypatch.setattr(runner, "repair_file", boom)
    outcomes = run_sweep(
        _grid(),
        tmp_path / "results",
        tmp_path / "out",
        generator=_writer(_map_text()),
        provider=FakeRating(),
    )
    assert "repair/gate failed" in outcomes[0].error


def test_sweep_error_is_available_for_callers() -> None:
    assert issubclass(SweepError, Exception)


def test_object_count_of_a_file_without_an_object_section_is_zero(tmp_path: Path) -> None:
    # Not reachable through run_sweep -- parsing rejects such a file first -- but
    # the guard keeps _object_count safe for any future caller.
    from osu_automapper.sweep.runner import _object_count

    path = tmp_path / "headless.osu"
    path.write_text("osu file format v14\n\n[General]\n", encoding="utf-8")
    assert _object_count(path) == 0
