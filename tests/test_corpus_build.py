"""Grouping lazer blobs into the mapset samples the loader expects."""

from __future__ import annotations

from pathlib import Path

from osu_automapper.corpus.build import (
    AudioCandidate,
    build_sample,
    group_by_set,
    match_audio,
)
from osu_automapper.corpus.extract import ParsedBeatmap


def _parsed(
    *,
    set_id: str = "123",
    version: str = "Insane",
    artist: str = "Artist",
    title: str = "Title",
    mode: str = "0",
    last: int = 60_000,
    path: Path | None = None,
) -> ParsedBeatmap:
    fields = {
        "Mode": mode,
        "Artist": artist,
        "Title": title,
        "Version": version,
        "Creator": "mapper",
        "BeatmapSetID": set_id,
        "CircleSize": "4",
        "OverallDifficulty": "8",
        "ApproachRate": "9",
        "HPDrainRate": "5",
        "Tags": "a b",
    }
    text = (
        "osu file format v14\n\n[TimingPoints]\n0,300,4,2,0,60,1,0\n\n"
        "[HitObjects]\n256,192,0,1,0,0:0:0:0:\n"
    )
    return ParsedBeatmap(
        path=path or Path("/blob/x"),
        text=text,
        fields=fields,
        object_count=400,
        circle_count=300,
        slider_count=90,
        spinner_count=10,
        last_object_ms=last,
        first_object_ms=1000,
    )


def test_maps_sharing_a_set_id_become_one_sample() -> None:
    grouped = group_by_set([_parsed(version="Easy"), _parsed(version="Hard")])
    assert list(grouped) == ["set:123"]
    assert len(grouped["set:123"]) == 2


def test_maps_without_a_set_id_group_by_artist_and_title() -> None:
    grouped = group_by_set(
        [
            _parsed(set_id="-1", title="Song A"),
            _parsed(set_id="-1", title="Song A", version="Hard"),
            _parsed(set_id="0", title="Song B"),
        ]
    )
    assert sorted(grouped) == ["name:Artist::Song A", "name:Artist::Song B"]
    assert len(grouped["name:Artist::Song A"]) == 2


def test_audio_must_be_long_enough_to_contain_the_map() -> None:
    beatmaps = [_parsed(last=120_000)]
    too_short = AudioCandidate(path=Path("/a"), duration=60.0)
    long_enough = AudioCandidate(path=Path("/b"), duration=125.0)
    assert match_audio(beatmaps, [too_short]) is None
    assert match_audio(beatmaps, [too_short, long_enough]) is long_enough


def test_absurdly_long_audio_is_rejected() -> None:
    beatmaps = [_parsed(last=60_000)]
    album = AudioCandidate(path=Path("/album"), duration=3600.0)
    assert match_audio(beatmaps, [album]) is None


def test_matching_tags_win_over_a_closer_duration() -> None:
    beatmaps = [_parsed(last=60_000, artist="Artist", title="Title")]
    untagged = AudioCandidate(path=Path("/close"), duration=61.0)
    tagged = AudioCandidate(path=Path("/tagged"), duration=90.0, artist="Artist", title="Title")
    assert match_audio(beatmaps, [untagged, tagged]) is tagged


def test_the_closest_duration_wins_when_nothing_is_tagged() -> None:
    beatmaps = [_parsed(last=60_000)]
    near = AudioCandidate(path=Path("/near"), duration=62.0)
    far = AudioCandidate(path=Path("/far"), duration=100.0)
    assert match_audio(beatmaps, [near, far]) is near


def test_matching_nothing_is_not_an_error() -> None:
    assert match_audio([], [AudioCandidate(path=Path("/a"), duration=10.0)]) is None
    assert match_audio([_parsed()], []) is None


def test_a_sample_carries_every_field_the_loader_reads() -> None:
    audio = AudioCandidate(path=Path("/audio/blob"), duration=180.0)
    sample = build_sample("set:123", [_parsed()], audio, rater=lambda _: 5.25)
    assert sample is not None
    payload = sample.to_json_payload()
    assert payload["audio_length"] == 180.0
    entry = payload["beatmaps"][0]
    for required in ("beatmap_id", "beatmapset_id", "mode", "creator_id", "content"):
        assert entry[required] is not None
    for filtered in ("approved", "difficultyrating", "approved_date", "submit_date"):
        assert filtered in entry
    assert entry["difficultyrating"] == 5.25
    assert entry["bpm"] == 200.0


def test_difficulties_of_one_set_share_a_set_id_but_not_a_beatmap_id() -> None:
    audio = AudioCandidate(path=Path("/audio"), duration=180.0)
    sample = build_sample(
        "set:123", [_parsed(version="Easy"), _parsed(version="Hard")], audio, rater=lambda _: 3.0
    )
    assert sample is not None
    entries = sample.to_json_payload()["beatmaps"]
    assert entries[0]["beatmapset_id"] == entries[1]["beatmapset_id"]
    assert entries[0]["beatmap_id"] != entries[1]["beatmap_id"]


def test_a_rating_failure_does_not_drop_the_map() -> None:
    def broken(_: Path) -> float:
        raise RuntimeError("no rating")

    audio = AudioCandidate(path=Path("/audio"), duration=180.0)
    sample = build_sample("set:1", [_parsed()], audio, rater=broken)
    assert sample is not None
    assert sample.to_json_payload()["beatmaps"][0]["difficultyrating"] == 0.0


def test_an_empty_mapset_produces_nothing() -> None:
    audio = AudioCandidate(path=Path("/audio"), duration=10.0)
    assert build_sample("set:1", [], audio, rater=lambda _: 1.0) is None


def test_unparseable_difficulty_fields_fall_back_to_defaults() -> None:
    beatmap = _parsed()
    beatmap.fields["CircleSize"] = "not-a-number"
    audio = AudioCandidate(path=Path("/audio"), duration=180.0)
    sample = build_sample("set:1", [beatmap], audio, rater=lambda _: 1.0)
    assert sample is not None
    assert sample.to_json_payload()["beatmaps"][0]["diff_size"] == 4.0


def test_usability_mirrors_the_loader_s_own_filter() -> None:
    audio = AudioCandidate(path=Path("/audio"), duration=180.0)
    std = build_sample("set:1", [_parsed(mode="0")], audio, rater=lambda _: 4.0)
    mania = build_sample("set:2", [_parsed(mode="3")], audio, rater=lambda _: 4.0)
    assert std is not None
    assert mania is not None
    assert std.is_usable(gamemodes=(0,), statuses=(1, 2)) is True
    assert mania.is_usable(gamemodes=(0,), statuses=(1, 2)) is False
    assert std.is_usable(gamemodes=(0,), statuses=(4,)) is False


def test_a_mapset_is_dated_from_its_real_osu_id() -> None:
    # v32 trains an add_year_token, so a constant date would collapse the whole
    # corpus onto one year token and mismatch inference (which defaults to 2023).
    audio = AudioCandidate(path=Path("/audio"), duration=180.0)
    old = build_sample("set:80", [_parsed()], audio, rater=lambda _: 4.0)
    new = build_sample("set:2241525", [_parsed()], audio, rater=lambda _: 4.0)
    assert old is not None
    assert new is not None
    assert old.to_json_payload()["beatmaps"][0]["submit_date"].startswith("2007")
    assert new.to_json_payload()["beatmaps"][0]["submit_date"].startswith("2024")


def test_a_mapset_without_an_id_keeps_the_fallback_date() -> None:
    from osu_automapper.corpus.build import FALLBACK_DATE

    audio = AudioCandidate(path=Path("/audio"), duration=180.0)
    sample = build_sample("name:Artist::Title", [_parsed()], audio, rater=lambda _: 4.0)
    assert sample is not None
    assert sample.to_json_payload()["beatmaps"][0]["submit_date"] == FALLBACK_DATE


def test_a_non_numeric_set_key_does_not_crash_dating() -> None:
    from osu_automapper.corpus.build import FALLBACK_DATE

    audio = AudioCandidate(path=Path("/audio"), duration=180.0)
    sample = build_sample("set:notanumber", [_parsed()], audio, rater=lambda _: 4.0)
    assert sample is not None
    assert sample.to_json_payload()["beatmaps"][0]["submit_date"] == FALLBACK_DATE
