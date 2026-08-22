"""Grid definition and per-cell results.

Pure data plus one generator: no IO happens here, so the shape of a sweep can be
inspected (and tested) without a GPU.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from osu_automapper.parse import Mode

# Mania needs a key count; standard must not receive one. Keeping the default
# here rather than at the call site means every cell for mania is comparable.
DEFAULT_MANIA_KEYCOUNT = 4


@dataclass(frozen=True)
class SweepCell:
    """One generation to perform: a single point of the grid."""

    song: Path
    difficulty: float
    mode: Mode
    seed: int
    lora_path: Path | None = None
    keycount: int | None = None

    @property
    def label(self) -> str:
        """Filesystem-safe identity of this cell, stable across runs.

        Used as both the output directory name and the result filename, which is
        what makes a sweep resumable: a cell whose JSON already exists is skipped.
        """
        adapter = self.lora_path.name if self.lora_path is not None else "base"
        keys = f"_k{self.keycount}" if self.keycount is not None else ""
        return (
            f"{self.song.stem}_m{int(self.mode)}{keys}_d{self.difficulty:g}_s{self.seed}_{adapter}"
        )


@dataclass(frozen=True)
class SweepGrid:
    """The full cartesian product to sweep."""

    songs: Sequence[Path]
    difficulties: Sequence[float]
    modes: Sequence[Mode]
    seeds: Sequence[int]
    adapters: Sequence[Path | None] = (None,)
    mania_keycount: int = DEFAULT_MANIA_KEYCOUNT

    @property
    def size(self) -> int:
        """How many generations this grid implies."""
        return (
            len(self.songs)
            * len(self.difficulties)
            * len(self.modes)
            * len(self.seeds)
            * len(self.adapters)
        )


def iter_cells(grid: SweepGrid) -> Iterator[SweepCell]:
    """Enumerate the grid.

    Ordered song-major so that a partial sweep still covers the full difficulty
    range of the songs it reached, rather than every song at one difficulty.
    """
    for song in grid.songs:
        for mode in grid.modes:
            for difficulty in grid.difficulties:
                for seed in grid.seeds:
                    for adapter in grid.adapters:
                        yield SweepCell(
                            song=song,
                            difficulty=difficulty,
                            mode=mode,
                            seed=seed,
                            lora_path=adapter,
                            keycount=grid.mania_keycount if mode is Mode.MANIA else None,
                        )


@dataclass
class SweepOutcome:
    """Everything measured about one cell.

    ``raw_*`` describes the model's untouched output; ``repaired_*`` describes it
    after ``repair`` stripped the known t=0 artifact. Both are recorded because
    the difference between them *is* the defect rate.
    """

    label: str
    song: str
    difficulty: float
    mode: int
    seed: int
    adapter: str
    generated: bool = False
    error: str = ""
    raw_passed: bool = False
    raw_failures: list[str] = field(default_factory=list)
    raw_stars: float | None = None
    repaired_passed: bool = False
    repaired_failures: list[str] = field(default_factory=list)
    repaired_stars: float | None = None
    objects_removed: int = 0
    objects: int = 0
    duration_seconds: float = 0.0

    @property
    def defect_fired(self) -> bool:
        """True when the stacked-at-zero artifact was present in the raw output."""
        return self.objects_removed > 0

    @property
    def star_error(self) -> float | None:
        """Signed distance from the requested difficulty, after repair."""
        if self.repaired_stars is None:
            return None
        return self.repaired_stars - self.difficulty

    def to_json(self) -> str:
        """Serialise for the per-cell result file."""
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> SweepOutcome:
        """Rebuild an outcome written by a previous run."""
        return cls(**json.loads(text))
