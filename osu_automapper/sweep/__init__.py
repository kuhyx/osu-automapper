"""Reliability sweep: measure where the model is dependable and where it breaks.

The sweep exists to replace anecdotes with a table. It walks a grid of
(song x difficulty x gamemode x seed x adapter), generates each cell, and gates
the result **twice** -- once on the raw model output and once after ``repair`` --
so the report can distinguish "the model produced a clean map" from "the model
produced a repairable map".

Nothing here decides quality: every verdict is an exit code from the existing
check suite. See :mod:`osu_automapper.report`.
"""

from __future__ import annotations

from osu_automapper.sweep.model import SweepCell, SweepGrid, SweepOutcome, iter_cells
from osu_automapper.sweep.report import aggregate, to_markdown
from osu_automapper.sweep.runner import run_sweep

__all__ = [
    "SweepCell",
    "SweepGrid",
    "SweepOutcome",
    "aggregate",
    "iter_cells",
    "run_sweep",
    "to_markdown",
]
