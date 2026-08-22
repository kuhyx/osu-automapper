"""Star-rating access behind a protocol.

The real implementation shells out to ``rosu_pp_py``. Keeping it behind a protocol
is what lets the difficulty gate be branch-covered without a native dependency in
the test run.

"Within +-0.5 stars" is meaningless unless the ruleset is pinned, so the defaults
are stated explicitly: lazer, no mods, 1.0x clock rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DEFAULT_TOLERANCE = 0.5


class StarRatingError(Exception):
    """Raised when a star rating cannot be computed."""


class StarRatingProvider(Protocol):
    """Anything that can rate a beatmap file."""

    def rate(self, path: Path) -> float:
        """Return the star rating for ``path``."""
        ...


@dataclass(frozen=True)
class RosuStarRating:
    """Star rating via ``rosu_pp_py``, with the ruleset pinned."""

    lazer: bool = True
    clock_rate: float = 1.0
    mods: int = 0

    def rate(self, path: Path) -> float:
        """Compute the star rating, raising :class:`StarRatingError` on failure."""
        # rosu-pp-py is a hard dependency (see pyproject), so an import guard here
        # would be an unreachable branch pretending to be defensive.
        import rosu_pp_py

        try:
            beatmap = rosu_pp_py.Beatmap(path=str(path))
            difficulty = rosu_pp_py.Difficulty(
                lazer=self.lazer, clock_rate=self.clock_rate, mods=self.mods
            )
            return float(difficulty.calculate(beatmap).stars)
        except Exception as exc:
            raise StarRatingError(f"cannot rate {path}: {exc}") from exc


def difficulty_within_tolerance(
    actual: float, target: float, tolerance: float = DEFAULT_TOLERANCE
) -> bool:
    """Return True when ``actual`` is within ``tolerance`` stars of ``target``."""
    return abs(actual - target) <= tolerance
