"""Shard writing and the verification that re-reads it."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from osu_automapper.corpus.model import BeatmapEntry, MapsetSample
from osu_automapper.corpus.shards import ShardError, chunk, verify_shard, write_shard


def _entry() -> BeatmapEntry:
    """Build a single valid difficulty."""
    return BeatmapEntry(
        beatmap_id=1,
        beatmapset_id=2,
        mode=0,
        creator_id=3,
        creator="mapper",
        content="osu file format v14",
        difficultyrating=4.5,
        approved=1,
        approved_date="2020-01-01 00:00:00",
        submit_date="2020-01-01 00:00:00",
        version="Insane",
        artist="Artist",
        title="Title",
        bpm=180.0,
        total_length=120,
        hit_length=110,
        count_normal=300,
        count_slider=90,
        count_spinner=10,
        diff_size=4.0,
        diff_overall=8.0,
        diff_approach=9.0,
        diff_drain=5.0,
        max_combo=400,
    )


def _sample(key: str = "set:1") -> MapsetSample:
    return MapsetSample(key=key, audio_hash="abc", audio_length=120.0, beatmaps=[_entry()])


def _fake_encoder(_: Path) -> bytes:
    return b"OggS-fake-opus-payload"


def test_a_shard_pairs_one_json_and_one_opus_per_sample(tmp_path: Path) -> None:
    target = tmp_path / "data-000000.tar"
    written = write_shard([(_sample(), tmp_path / "a.mp3")], target, encoder=_fake_encoder)
    assert written == 1
    with tarfile.open(target) as archive:
        assert sorted(archive.getnames()) == ["000000.json", "000000.opus"]


def test_keys_are_zero_padded_and_sequential(tmp_path: Path) -> None:
    target = tmp_path / "s.tar"
    samples = [(_sample(f"set:{i}"), tmp_path / "a.mp3") for i in range(3)]
    write_shard(samples, target, encoder=_fake_encoder)
    with tarfile.open(target) as archive:
        keys = sorted({n.split(".")[0] for n in archive.getnames()})
    assert keys == ["000000", "000001", "000002"]


def test_the_written_json_matches_the_loader_s_expected_shape(tmp_path: Path) -> None:
    target = tmp_path / "s.tar"
    write_shard([(_sample(), tmp_path / "a.mp3")], target, encoder=_fake_encoder)
    with tarfile.open(target) as archive:
        handle = archive.extractfile("000000.json")
        assert handle is not None
        payload = json.loads(handle.read().decode())
    assert sorted(payload) == ["audio_hash", "audio_length", "beatmaps"]
    assert payload["beatmaps"][0]["content"].startswith("osu file format")


def test_an_unencodable_sample_is_skipped_not_fatal(tmp_path: Path) -> None:
    def flaky(path: Path) -> bytes:
        if path.name == "bad.mp3":
            raise ShardError("cannot encode")
        return b"ok"

    target = tmp_path / "s.tar"
    samples = [
        (_sample("a"), tmp_path / "bad.mp3"),
        (_sample("b"), tmp_path / "good.mp3"),
    ]
    assert write_shard(samples, target, encoder=flaky) == 1


def test_a_shard_with_nothing_in_it_is_not_left_behind(tmp_path: Path) -> None:
    def always_fails(_: Path) -> bytes:
        raise ShardError("no")

    target = tmp_path / "empty.tar"
    assert write_shard([(_sample(), tmp_path / "a.mp3")], target, encoder=always_fails) == 0
    assert not target.exists()


def test_verification_accepts_a_good_shard(tmp_path: Path) -> None:
    target = tmp_path / "s.tar"
    write_shard([(_sample(), tmp_path / "a.mp3")], target, encoder=_fake_encoder)
    count, problems = verify_shard(target)
    assert (count, problems) == (1, [])


def test_verification_catches_a_missing_audio_member(tmp_path: Path) -> None:
    target = tmp_path / "s.tar"
    payload = json.dumps(_sample().to_json_payload()).encode()
    with tarfile.open(target, "w") as archive:
        info = tarfile.TarInfo("000000.json")
        info.size = len(payload)
        import io

        archive.addfile(info, io.BytesIO(payload))
    _, problems = verify_shard(target)
    assert problems == ["000000: missing .opus"]


def test_verification_catches_a_sample_with_no_beatmaps(tmp_path: Path) -> None:
    import io

    target = tmp_path / "s.tar"
    payload = json.dumps({"audio_hash": "x", "audio_length": 1.0, "beatmaps": []}).encode()
    with tarfile.open(target, "w") as archive:
        for name, blob in (("000000.json", payload), ("000000.opus", b"x")):
            info = tarfile.TarInfo(name)
            info.size = len(blob)
            archive.addfile(info, io.BytesIO(blob))
    _, problems = verify_shard(target)
    assert problems == ["000000: no beatmaps"]


def test_verification_catches_a_field_the_loader_reads_with_brackets(tmp_path: Path) -> None:
    import io

    target = tmp_path / "s.tar"
    entry = _sample().to_json_payload()
    del entry["beatmaps"][0]["creator_id"]
    payload = json.dumps(entry).encode()
    with tarfile.open(target, "w") as archive:
        for name, blob in (("000000.json", payload), ("000000.opus", b"x")):
            info = tarfile.TarInfo(name)
            info.size = len(blob)
            archive.addfile(info, io.BytesIO(blob))
    _, problems = verify_shard(target)
    assert problems == ["000000[0]: missing creator_id"]


def test_verification_catches_a_missing_json_member(tmp_path: Path) -> None:
    import io

    target = tmp_path / "s.tar"
    with tarfile.open(target, "w") as archive:
        info = tarfile.TarInfo("000000.opus")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    _, problems = verify_shard(target)
    assert problems == ["000000: missing .json"]


def test_chunking_splits_into_runs() -> None:
    assert [list(c) for c in chunk([1, 2, 3, 4, 5], 2)] == [[1, 2], [3, 4], [5]]


def test_a_non_positive_chunk_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        list(chunk([1, 2], 0))


def test_real_ffmpeg_produces_decodable_mono_opus(tmp_path: Path) -> None:
    """Exercises the actual encoder: a wrong flag here only fails at train time."""
    import subprocess

    from osu_automapper.corpus.shards import encode_opus

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
            "sine=frequency=440:duration=1",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    payload = encode_opus(source, bitrate="32k")
    assert payload.startswith(b"OggS")

    encoded = tmp_path / "out.opus"
    encoded.write_bytes(payload)
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "stream=codec_name,channels",
            "-of",
            "csv=p=0",
            str(encoded),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "opus" in probe.stdout
    assert "1" in probe.stdout


def test_encoding_a_file_ffmpeg_cannot_read_raises(tmp_path: Path) -> None:
    from osu_automapper.corpus.shards import encode_opus

    broken = tmp_path / "not-audio.mp3"
    broken.write_text("this is not audio")
    with pytest.raises(ShardError, match="ffmpeg failed"):
        encode_opus(broken)
