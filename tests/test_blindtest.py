"""Tests for the blind-test harness."""

from __future__ import annotations

from pathlib import Path

import pytest

from osu_automapper.blindtest import BlindTest, build_blindtest, score_blindtest
from osu_automapper.blindtest.harness import LABELS


def test_build_labels_and_hides_origin() -> None:
    real = [Path("r1.osu"), Path("r2.osu")]
    generated = [Path("g1.osu")]
    test = build_blindtest(real, generated, seed=1)
    assert [e.label for e in test.entries] == list(LABELS[:3])
    assert sum(1 for e in test.entries if e.generated) == 1


def test_shuffle_is_seed_reproducible() -> None:
    args = ([Path("r1.osu"), Path("r2.osu")], [Path("g1.osu"), Path("g2.osu")])
    first = build_blindtest(*args, seed=7)
    second = build_blindtest(*args, seed=7)
    assert [e.source for e in first.entries] == [e.source for e in second.entries]


def test_too_many_maps_rejected() -> None:
    many = [Path(f"m{i}.osu") for i in range(len(LABELS) + 1)]
    with pytest.raises(ValueError, match="at most"):
        build_blindtest(many, [])


def test_json_roundtrip() -> None:
    test = build_blindtest([Path("r.osu")], [Path("g.osu")], seed=3)
    restored = BlindTest.from_json(test.to_json())
    assert restored.answer_key == test.answer_key
    assert restored.created == test.created


def test_scoring_counts_only_known_labels() -> None:
    test = build_blindtest([Path("r.osu")], [Path("g.osu")], seed=3)
    key = test.answer_key
    guesses = dict(key)
    guesses["Z"] = True  # not part of this test
    correct, total = score_blindtest(test, guesses)
    assert (correct, total) == (2, 2)


def test_scoring_detects_wrong_guesses() -> None:
    test = build_blindtest([Path("r.osu")], [Path("g.osu")], seed=3)
    flipped = {label: not value for label, value in test.answer_key.items()}
    correct, total = score_blindtest(test, flipped)
    assert (correct, total) == (0, 2)


def test_partial_guesses_are_scored() -> None:
    test = build_blindtest([Path("r.osu")], [Path("g.osu")], seed=3)
    first = next(iter(test.answer_key))
    correct, total = score_blindtest(test, {first: test.answer_key[first]})
    assert (correct, total) == (1, 1)
