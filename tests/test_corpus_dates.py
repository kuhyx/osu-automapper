"""Dating a mapset from its id, so the year token is not a constant."""

from __future__ import annotations

from osu_automapper.corpus.dates import (
    EARLIEST_YEAR,
    LATEST_YEAR,
    YEAR_ANCHORS,
    submit_date_for_set_id,
    year_for_set_id,
)


def test_anchors_are_monotonic_in_both_year_and_id() -> None:
    years = sorted(YEAR_ANCHORS)
    ids = [YEAR_ANCHORS[y] for y in years]
    assert years == list(range(years[0], years[-1] + 1))
    assert ids == sorted(ids)


def test_each_anchor_dates_to_its_own_year() -> None:
    for year, set_id in YEAR_ANCHORS.items():
        assert year_for_set_id(set_id) == year


def test_an_id_between_anchors_takes_the_earlier_year() -> None:
    assert year_for_set_id(YEAR_ANCHORS[2016] + 1) == 2016
    assert year_for_set_id(YEAR_ANCHORS[2017] - 1) == 2016


def test_ids_outside_the_table_are_clamped_not_extrapolated() -> None:
    assert year_for_set_id(1) == EARLIEST_YEAR
    assert year_for_set_id(0) == EARLIEST_YEAR
    assert year_for_set_id(99_000_000) == LATEST_YEAR


def test_real_ids_land_in_the_year_they_were_measured_in() -> None:
    # Spot checks taken from the same corpus shard the anchors came from.
    assert year_for_set_id(80) == 2007
    assert year_for_set_id(223370) == 2014
    assert year_for_set_id(834254) == 2018
    assert year_for_set_id(1795684) == 2022
    assert year_for_set_id(2241525) == 2024


def test_the_rendered_date_is_parseable_and_year_accurate() -> None:
    from datetime import datetime

    text = submit_date_for_set_id(1795684)
    assert datetime.strptime(text, "%Y-%m-%d %H:%M:%S").year == 2022


def test_a_spread_of_ids_produces_a_spread_of_years() -> None:
    # The whole point: a constant date would train one year token.
    ids = [80, 100000, 500000, 1000000, 1500000, 2000000, 2400000]
    assert len({year_for_set_id(i) for i in ids}) >= 6
