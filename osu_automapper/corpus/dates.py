"""Estimate a mapset's submission year from its ``BeatmapSetID``.

A ``.osu`` file carries no submission date, and the local lazer library keeps no
osu! web metadata -- but ``add_year_token: true`` in ``v32.yaml`` means every
training sample carries a year token derived from ``submit_date``. Writing one
constant date for the whole corpus would train a single year token that nobody
ever asks for at inference (which defaults to ``--year 2023``), reproducing the
same silent no-op already measured for a ``gamemode=0`` adapter used in mania.

Set ids are allocated monotonically, so the id itself dates the set. The anchors
below are the smallest id observed in each calendar year across a real shard of
``project-riz/osu-beatmaps`` (2,979 id/date pairs) -- measured, not guessed.
"""

from __future__ import annotations

from bisect import bisect_right

# year -> smallest beatmapset_id first seen in that year.
YEAR_ANCHORS: dict[int, int] = {
    2007: 80,
    2008: 608,
    2009: 4842,
    2010: 11894,
    2011: 24799,
    2012: 42647,
    2013: 76830,
    2014: 143844,
    2015: 255431,
    2016: 406217,
    2017: 560952,
    2018: 720329,
    2019: 905046,
    2020: 1093906,
    2021: 1337354,
    2022: 1665761,
    2023: 1925527,
    2024: 2115140,
    2025: 2304964,
}

_YEARS = sorted(YEAR_ANCHORS)
_BOUNDS = [YEAR_ANCHORS[y] for y in _YEARS]
EARLIEST_YEAR = _YEARS[0]
LATEST_YEAR = _YEARS[-1]


def year_for_set_id(set_id: int) -> int:
    """Return the calendar year a mapset id was most likely submitted in.

    Ids below the first anchor predate it and are clamped to the earliest known
    year; ids beyond the last anchor are newer than the anchor table and are
    clamped to the latest.
    """
    if set_id < _BOUNDS[0]:
        return EARLIEST_YEAR
    return _YEARS[bisect_right(_BOUNDS, set_id) - 1]


def submit_date_for_set_id(set_id: int) -> str:
    """Render an estimated submission date in the corpus's date format.

    Only the year is meaningful -- it is all ``get_web_ranked_date`` reads back
    out -- so the day is fixed rather than invented with false precision.
    """
    return f"{year_for_set_id(set_id)}-01-01 00:00:00"
