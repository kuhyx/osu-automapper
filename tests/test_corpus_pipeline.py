"""The corpus pipeline and its CLI command, without touching a real library."""

from __future__ import annotations

import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from osu_automapper.cli import main
from osu_automapper.corpus.build import AudioCandidate
from osu_automapper.corpus.pipeline import (
    BuildStats,
    assemble,
    collect,
    probe_audio,
    write_corpus,
)

MAP = """osu file format v14

[General]
AudioFilename: audio.mp3
Mode: {mode}

[Metadata]
Title:Song
Artist:Band
Creator:mapper
Version:{version}
BeatmapSetID:{set_id}

[Difficulty]
CircleSize:4

[TimingPoints]
0,300,4,2,0,60,1,0

[HitObjects]
256,192,1000,1,0,0:0:0:0:
256,192,20000,1,0,0:0:0:0:
"""


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """Build a miniature stand-in for lazer's blob store."""
    root = tmp_path / "files"
    (root / "a" / "ab").mkdir(parents=True)
    (root / "a" / "ab" / "map1").write_text(MAP.format(mode=0, version="Easy", set_id=1))
    (root / "a" / "ab" / "map2").write_text(MAP.format(mode=0, version="Hard", set_id=1))
    (root / "a" / "ab" / "mania").write_text(MAP.format(mode=3, version="4K", set_id=2))
    # Real encoded audio: the command path uses ffprobe, which correctly
    # rejects a hand-made header, so a fake blob would make it find nothing.
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=30",
            "-f",
            "mp3",
            str(root / "a" / "ab" / "song"),
        ],
        check=True,
        capture_output=True,
    )
    (root / "a" / "ab" / "cover").write_bytes(b"\x89PNG\r\n\x1a\n")
    return root


def _prober(path: Path) -> AudioCandidate | None:
    if path.name != "song":
        return None
    return AudioCandidate(path=path, duration=60.0, artist="Band", title="Song")


def test_collect_splits_beatmaps_from_audio_and_honours_gamemode(library: Path) -> None:
    beatmaps, audio = collect(library, _prober, gamemode=0)
    assert sorted(b.fields["Version"] for b in beatmaps) == ["Easy", "Hard"]
    assert [a.path.name for a in audio] == ["song"]

    mania, _ = collect(library, _prober, gamemode=3)
    assert [b.fields["Version"] for b in mania] == ["4K"]


def test_assemble_groups_difficulties_and_counts_what_it_saw(library: Path) -> None:
    beatmaps, audio = collect(library, _prober, gamemode=0)
    samples, stats = assemble(beatmaps, audio, rater=lambda _: 4.0)
    assert stats.beatmaps == 2
    assert stats.mapsets == 1
    assert stats.samples == 1
    assert len(samples[0][0].beatmaps) == 2


def test_assemble_reports_mapsets_it_could_not_match_to_audio(library: Path) -> None:
    beatmaps, _ = collect(library, _prober, gamemode=0)
    samples, stats = assemble(beatmaps, [], rater=lambda _: 4.0)
    assert samples == []
    assert stats.unmatched == 1


def test_assemble_honours_a_limit(library: Path) -> None:
    (library / "a" / "ab" / "map3").write_text(MAP.format(mode=0, version="Easy", set_id=99))
    beatmaps, audio = collect(library, _prober, gamemode=0)
    assert len(beatmaps) == 3

    unlimited, _ = assemble(beatmaps, audio, rater=lambda _: 4.0)
    limited, stats = assemble(beatmaps, audio, rater=lambda _: 4.0, limit=1)
    assert len(unlimited) == 2
    assert stats.samples == 1
    assert len(limited) == 1


def test_write_corpus_splits_into_shards_and_verifies_each(
    library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from osu_automapper.corpus import shards

    monkeypatch.setattr(shards, "encode_opus", lambda path, bitrate="96k": b"OggS-x")
    beatmaps, audio = collect(library, _prober, gamemode=0)
    samples, stats = assemble(beatmaps, audio, rater=lambda _: 4.0)
    destination = tmp_path / "out"
    result = write_corpus(samples * 3, destination, stats, shard_size=2)
    assert result.shards == 2
    assert result.problems == []
    assert sorted(p.name for p in destination.glob("*.tar")) == [
        "data-000000.tar",
        "data-000001.tar",
    ]
    with tarfile.open(destination / "data-000000.tar") as archive:
        assert len(archive.getnames()) == 4


def test_write_corpus_skips_a_shard_it_could_not_fill(
    library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from osu_automapper.corpus import shards

    def refuse(path: Path, bitrate: str = "96k") -> bytes:
        raise shards.ShardError("no encoder")

    monkeypatch.setattr(shards, "encode_opus", refuse)
    beatmaps, audio = collect(library, _prober, gamemode=0)
    samples, stats = assemble(beatmaps, audio, rater=lambda _: 4.0)
    result = write_corpus(samples, tmp_path / "out", stats, shard_size=2)
    assert result.shards == 0


def test_build_stats_serialise_for_the_manifest() -> None:
    payload = json.loads(BuildStats(beatmaps=5, mapsets=2, samples=2, shards=1).to_json())
    assert payload["beatmaps"] == 5
    assert payload["problems"] == []


def test_probe_audio_rejects_a_file_ffprobe_cannot_read(tmp_path: Path) -> None:
    broken = tmp_path / "nope"
    broken.write_text("not audio")
    assert probe_audio(broken) is None


def test_probe_audio_reads_a_real_file(tmp_path: Path) -> None:
    import subprocess

    source = tmp_path / "tone.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    candidate = probe_audio(source)
    assert candidate is not None
    assert 1.5 < candidate.duration < 2.5


def test_the_command_reports_a_missing_library(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["corpus", "--library", str(tmp_path / "absent"), "--dry-run"])
    assert code == 2
    assert "no lazer library" in capsys.readouterr().err


def test_the_command_dry_runs_without_writing(
    library: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "shards"
    code = main(["corpus", "--library", str(library), "--output", str(destination), "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "would write" in out
    assert not destination.exists()


def test_the_command_writes_and_verifies_shards(
    library: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from osu_automapper.corpus import shards

    monkeypatch.setattr(shards, "encode_opus", lambda path, bitrate="96k": b"OggS-x")
    destination = tmp_path / "shards"
    code = main(["corpus", "--library", str(library), "--output", str(destination)])
    out = capsys.readouterr().out
    assert code == 0
    assert "every shard verified" in out
    assert (destination / "data-000000.tar").exists()
    assert json.loads((tmp_path / "manifest.json").read_text())["samples"] == 1


def test_the_command_fails_when_nothing_is_usable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "files"
    empty.mkdir()
    code = main(["corpus", "--library", str(empty)])
    assert code == 2
    assert "nothing to write" in capsys.readouterr().err


def test_probe_audio_survives_ffprobe_returning_nonsense(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess as sp

    class Result:
        returncode = 0
        stdout = "{not json"

    monkeypatch.setattr(sp, "run", lambda *a, **k: Result())
    assert probe_audio(tmp_path / "any") is None


def test_probe_audio_rejects_a_zero_length_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess as sp

    class Result:
        returncode = 0
        stdout = json.dumps({"format": {"duration": "0"}})

    monkeypatch.setattr(sp, "run", lambda *a, **k: Result())
    assert probe_audio(tmp_path / "any") is None


def test_a_mapset_no_difficulty_of_which_passes_the_filter_is_dropped(library: Path) -> None:
    # Collect as mania, then assemble as standard: nothing can survive, which is
    # what `filter_web_beatmaps` would do at train time.
    beatmaps, audio = collect(library, _prober, gamemode=3)
    samples, stats = assemble(beatmaps, audio, rater=lambda _: 4.0, gamemode=0)
    assert samples == []
    assert stats.samples == 0


def test_an_audio_blob_the_prober_rejects_is_skipped(library: Path) -> None:
    # A second audio blob that probes as unusable must not become a candidate,
    # and must not stop the scan either.
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=1",
            "-f",
            "mp3",
            str(library / "a" / "ab" / "other-song"),
        ],
        check=True,
        capture_output=True,
    )
    _, audio = collect(library, _prober, gamemode=0)
    assert [a.path.name for a in audio] == ["song"]


def test_an_unratable_map_still_makes_it_into_the_corpus(
    library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # rosu-pp cannot rate every map; a rating failure must cost the star value,
    # not the map.
    from osu_automapper import stars
    from osu_automapper.corpus import shards
    from osu_automapper.stars import StarRatingError

    def unratable(self: object, path: Path) -> float:
        raise StarRatingError("nope")

    monkeypatch.setattr(stars.RosuStarRating, "rate", unratable)
    monkeypatch.setattr(shards, "encode_opus", lambda path, bitrate="96k": b"OggS-x")
    destination = tmp_path / "shards"
    assert main(["corpus", "--library", str(library), "--output", str(destination)]) == 0
    with tarfile.open(destination / "data-000000.tar") as archive:
        handle = archive.extractfile("000000.json")
        assert handle is not None
        payload = json.loads(handle.read().decode())
    assert payload["beatmaps"][0]["difficultyrating"] == 0.0


def test_a_shard_that_fails_verification_fails_the_command(
    library: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from osu_automapper.corpus import pipeline, shards

    monkeypatch.setattr(shards, "encode_opus", lambda path, bitrate="96k": b"OggS-x")
    monkeypatch.setattr(pipeline, "verify_shard", lambda path: (1, ["000000: missing .opus"]))
    code = main(["corpus", "--library", str(library), "--output", str(tmp_path / "shards")])
    assert code == 1
    assert "PROBLEM" in capsys.readouterr().err
