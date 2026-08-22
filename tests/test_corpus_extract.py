"""Classifying and parsing lazer's extensionless blobs."""

from __future__ import annotations

from pathlib import Path

from osu_automapper.corpus.extract import (
    bpm_of,
    classify,
    is_audio,
    is_beatmap,
    iter_blobs,
    parse_beatmap_blob,
)

MAP = """osu file format v14

[General]
AudioFilename: audio.mp3
Mode: 0

[Metadata]
Title:Song
Artist:Band
Creator:mapper
Version:Insane
BeatmapSetID:4242

[Difficulty]
CircleSize:4
OverallDifficulty:8

[TimingPoints]
0,300,4,2,0,60,1,0
1000,-50,4,2,0,60,0,0

[HitObjects]
256,192,1000,1,0,0:0:0:0:
256,192,2000,2,0,L|300:300,1,100
256,192,3000,12,0,5000
"""


def _blob(tmp_path: Path, payload: bytes | str, name: str = "blob") -> Path:
    path = tmp_path / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_bytes(payload)
    return path


def test_signatures_identify_each_blob_kind() -> None:
    assert is_beatmap(b"osu file format v14") is True
    assert is_beatmap(b"ID3\x04") is False
    assert is_audio(b"ID3\x04") is True
    assert is_audio(b"OggS...") is True
    assert is_audio(b"RIFF....WAVE") is True
    assert is_audio(b"\x89PNG\r\n\x1a\n") is False


def test_blobs_are_classified_without_extensions(tmp_path: Path) -> None:
    assert classify(_blob(tmp_path, MAP, "a")) == "beatmap"
    assert classify(_blob(tmp_path, b"ID3\x04padding", "b")) == "audio"
    assert classify(_blob(tmp_path, b"\x89PNG\r\n\x1a\nrest", "c")) == "other"


def test_parsing_reads_metadata_and_counts_object_types(tmp_path: Path) -> None:
    parsed = parse_beatmap_blob(_blob(tmp_path, MAP))
    assert parsed is not None
    assert parsed.fields["Title"] == "Song"
    assert parsed.fields["BeatmapSetID"] == "4242"
    assert parsed.mode == 0
    assert parsed.object_count == 3
    assert parsed.circle_count == 1
    assert parsed.slider_count == 1
    assert parsed.spinner_count == 1
    assert parsed.first_object_ms == 1000
    assert parsed.last_object_ms == 3000


def test_a_map_with_no_objects_is_rejected(tmp_path: Path) -> None:
    text = MAP.split("[HitObjects]")[0] + "[HitObjects]\n"
    assert parse_beatmap_blob(_blob(tmp_path, text)) is None


def test_a_non_beatmap_blob_is_rejected(tmp_path: Path) -> None:
    assert parse_beatmap_blob(_blob(tmp_path, "just some text")) is None


def test_malformed_object_lines_are_skipped_not_fatal(tmp_path: Path) -> None:
    text = MAP + "garbage\n256,192,notatime,1,0\n"
    parsed = parse_beatmap_blob(_blob(tmp_path, text))
    assert parsed is not None
    assert parsed.object_count == 3


def test_mode_defaults_to_standard_when_absent(tmp_path: Path) -> None:
    parsed = parse_beatmap_blob(_blob(tmp_path, MAP.replace("Mode: 0\n", "")))
    assert parsed is not None
    assert parsed.mode == 0


def test_bpm_comes_from_the_first_uninherited_timing_point() -> None:
    assert bpm_of(MAP) == 200.0


def test_bpm_of_a_map_without_timing_points_is_zero() -> None:
    assert bpm_of("osu file format v14\n\n[HitObjects]\n") == 0.0
    assert bpm_of("osu file format v14\n\n[TimingPoints]\n\n[HitObjects]\n") == 0.0


def test_bpm_ignores_inherited_and_malformed_rows() -> None:
    # "broken" has no comma; "0,x,..." has one but a non-numeric beat length --
    # two different guards, so both rows are needed to cover them.
    text = (
        "[TimingPoints]\nbroken\n0,x,4,2,0,60,1,0\n"
        "0,-50,4,2,0,60,0,0\n0,500,4,2,0,60,1,0\n\n[HitObjects]\n"
    )
    assert bpm_of(text) == 120.0


def test_blob_iteration_is_recursive_and_ordered(tmp_path: Path) -> None:
    (tmp_path / "a" / "ab").mkdir(parents=True)
    (tmp_path / "a" / "ab" / "one").write_text("x")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "two").write_text("y")
    assert [p.name for p in iter_blobs(tmp_path)] == ["one", "two"]


def test_object_times_of_a_file_without_the_section_are_empty() -> None:
    from osu_automapper.corpus.extract import _object_times

    assert _object_times("osu file format v14\n[General]\n") == ([], [])


def test_a_zero_beat_length_does_not_divide_by_zero() -> None:
    text = "[TimingPoints]\n0,0,4,2,0,60,1,0\n\n[HitObjects]\n"
    assert bpm_of(text) == 0.0
