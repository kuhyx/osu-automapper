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


HUMAN_EVENTS = """osu file format v14

[General]
AudioFilename: a.mp3

[Metadata]
Creator:someone
Version:Insane
Tags:ranked mapper

[Events]
//Background and Video events
0,0,"bg.jpg",0,0
//Break Periods
2,80184,92805
//Storyboard Layer 0 (Background)
Sprite,Foreground,Centre,"SB\\HP bar.png",320,240
 M,0,80109,,322,406

[TimingPoints]
0,500,4,2,0,60,1,0

[HitObjects]
256,192,0,1,0,0:0:0:0:
"""

GENERATED_EVENTS = """osu file format v14

[General]
AudioFilename: a.mp3

[Metadata]
Creator:Mapperatorinator
Version:5.0
Tags:seed=42 difficulty=5.0

[Events]
//Background and Video events
//Break Periods

[TimingPoints]
0,500,4,2,0,60,1,0

[HitObjects]
256,192,0,1,0,0:0:0:0:
"""


def _events_of(text: str) -> list[str]:
    body = text.partition("[Events]")[2].partition("\n[")[0]
    return [line for line in body.splitlines() if line.strip()]


def test_the_events_section_cannot_identify_a_map_s_origin() -> None:
    from osu_automapper.blindtest.harness import _anonymise

    # A human map's backgrounds, breaks and storyboard would otherwise announce
    # it: the generated maps have none of them.
    human = _anonymise(HUMAN_EVENTS, "A")
    generated = _anonymise(GENERATED_EVENTS, "B")
    assert _events_of(human) == _events_of(generated)
    assert "bg.jpg" not in human
    assert "Sprite" not in human


def test_anonymising_preserves_the_rest_of_the_map() -> None:
    from osu_automapper.blindtest.harness import _anonymise

    result = _anonymise(HUMAN_EVENTS, "C")
    assert "[TimingPoints]" in result
    assert "256,192,0,1,0,0:0:0:0:" in result
    assert "Version:C" in result
    assert "Creator:blindtest" in result
    assert "ranked mapper" not in result


def test_a_map_without_an_events_section_is_left_alone() -> None:
    from osu_automapper.blindtest.harness import _strip_events

    text = "osu file format v14\n\n[HitObjects]\n256,192,0,1,0,0:0:0:0:\n"
    assert _strip_events(text) == text


def test_events_at_the_end_of_a_file_are_still_stripped() -> None:
    from osu_automapper.blindtest.harness import _strip_events

    text = 'osu file format v14\n\n[Events]\n0,0,"bg.jpg",0,0\n'
    assert "bg.jpg" not in _strip_events(text)


KIAI_MAP = """osu file format v14

[TimingPoints]
0,500,4,2,0,60,1,0
1000,-100,4,2,0,60,0,1
2000,-100,4,2,0,80,0,5
3000,malformed
3500,-100,4,2,0,60,0,notanumber
4000,-100,4,2,0,60,0,4

[HitObjects]
256,192,0,1,0,0:0:0:0:
"""


def _effects(text: str) -> list[str]:
    body = text.partition("[TimingPoints]")[2].partition("\n[")[0]
    return [line.split(",")[7] for line in body.splitlines() if len(line.split(",")) >= 8]


def test_kiai_is_cleared_because_it_flashes_the_playfield() -> None:
    from osu_automapper.blindtest.harness import _clear_kiai

    # Human maps kiai their chorus and generated maps never do, so the flag
    # alone would answer the question the test is asking.
    result = _clear_kiai(KIAI_MAP)
    numeric = [e for e in _effects(result) if e.lstrip("-").isdigit()]
    assert numeric
    assert all(int(e) % 2 == 0 for e in numeric)


def test_clearing_kiai_preserves_every_other_effect_bit() -> None:
    from osu_automapper.blindtest.harness import _clear_kiai

    # effects=5 is kiai (1) + omit-first-barline (4): only the kiai bit may go.
    assert "4" in _effects(_clear_kiai(KIAI_MAP))


def test_clearing_kiai_preserves_slider_velocity_and_volume() -> None:
    from osu_automapper.blindtest.harness import _clear_kiai

    result = _clear_kiai(KIAI_MAP)
    assert "1000,-100,4,2,0,60,0,0" in result
    assert "2000,-100,4,2,0,80,0,4" in result
    assert "3000,malformed" in result
    # Eight fields but a non-numeric effects value: kept verbatim rather than
    # crashing the pack build on one odd row.
    assert "3500,-100,4,2,0,60,0,notanumber" in result
    assert "256,192,0,1,0,0:0:0:0:" in result


def test_a_map_without_timing_points_is_left_alone() -> None:
    from osu_automapper.blindtest.harness import _clear_kiai

    text = "osu file format v14\n\n[HitObjects]\n256,192,0,1,0,0:0:0:0:\n"
    assert _clear_kiai(text) == text


def test_timing_points_at_the_end_of_a_file_are_still_cleared() -> None:
    from osu_automapper.blindtest.harness import _clear_kiai

    text = "osu file format v14\n\n[TimingPoints]\n0,500,4,2,0,60,1,1\n"
    assert _clear_kiai(text).rstrip().endswith(",0")
