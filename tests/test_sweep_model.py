"""Grid enumeration and outcome serialisation."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from osu_automapper.parse import Mode
from osu_automapper.sweep.model import (
    DEFAULT_MANIA_KEYCOUNT,
    SweepCell,
    SweepGrid,
    SweepOutcome,
    iter_cells,
)


def _grid(
    songs: Sequence[Path] = (Path("a.mp3"),),
    difficulties: Sequence[float] = (4.0,),
    modes: Sequence[Mode] = (Mode.STANDARD,),
    seeds: Sequence[int] = (1,),
    adapters: Sequence[Path | None] = (None,),
    mania_keycount: int = DEFAULT_MANIA_KEYCOUNT,
) -> SweepGrid:
    """Build a grid, defaulting every axis to a single value."""
    return SweepGrid(
        songs=songs,
        difficulties=difficulties,
        modes=modes,
        seeds=seeds,
        adapters=adapters,
        mania_keycount=mania_keycount,
    )


def test_size_is_the_cartesian_product() -> None:
    grid = _grid(
        songs=[Path("a.mp3"), Path("b.mp3")],
        difficulties=[3.0, 4.0],
        modes=[Mode.STANDARD, Mode.MANIA],
        seeds=[1, 2, 3],
    )
    assert grid.size == 2 * 2 * 2 * 3
    assert len(list(iter_cells(grid))) == grid.size


def test_mania_cells_get_a_keycount_and_standard_does_not() -> None:
    grid = _grid(modes=[Mode.STANDARD, Mode.MANIA], mania_keycount=7)
    cells = {int(c.mode): c for c in iter_cells(grid)}
    assert cells[0].keycount is None
    assert cells[3].keycount == 7


def test_label_is_filesystem_safe_and_distinguishes_every_axis() -> None:
    grid = _grid(
        songs=[Path("song.mp3")],
        difficulties=[4.5],
        modes=[Mode.STANDARD],
        seeds=[7],
        adapters=[None, Path("/lora/checkpoint_11")],
    )
    labels = [c.label for c in iter_cells(grid)]
    assert labels == ["song_m0_d4.5_s7_base", "song_m0_d4.5_s7_checkpoint_11"]
    assert all("/" not in label for label in labels)


def test_iteration_is_song_major() -> None:
    grid = _grid(songs=[Path("a.mp3"), Path("b.mp3")], difficulties=[3.0, 4.0])
    songs = [c.song.name for c in iter_cells(grid)]
    assert songs == ["a.mp3", "a.mp3", "b.mp3", "b.mp3"]


def test_defect_and_star_error_derive_from_the_recorded_numbers() -> None:
    clean = SweepOutcome(
        label="x", song="s", difficulty=5.0, mode=0, seed=1, adapter="base", repaired_stars=5.4
    )
    assert clean.defect_fired is False
    assert clean.star_error is not None
    assert round(clean.star_error, 2) == 0.4

    broken = SweepOutcome(
        label="y", song="s", difficulty=5.0, mode=0, seed=1, adapter="base", objects_removed=3
    )
    assert broken.defect_fired is True
    assert broken.star_error is None


def test_outcome_round_trips_through_json() -> None:
    original = SweepOutcome(
        label="x",
        song="s.mp3",
        difficulty=5.0,
        mode=3,
        seed=2,
        adapter="base",
        generated=True,
        raw_failures=["object_gaps"],
    )
    assert SweepOutcome.from_json(original.to_json()) == original


def test_cell_label_includes_the_key_count_for_mania() -> None:
    cell = SweepCell(song=Path("s.mp3"), difficulty=5.0, mode=Mode.MANIA, seed=1, keycount=7)
    assert cell.label == "s_m3_k7_d5_s1_base"
