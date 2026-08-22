"""Write mapsets as webdataset ``.tar`` shards.

The layout is copied from a real shard of ``project-riz/osu-beatmaps``: each
sample is a ``<key>.json`` / ``<key>.opus`` pair, keys zero-padded and ordered,
647 mapsets per shard upstream. Getting this wrong fails inside training rather
than here, so ``verify_shard`` re-reads what was written.
"""

from __future__ import annotations

import io
import json
import subprocess
import tarfile
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from osu_automapper.corpus.model import MapsetSample

DEFAULT_SHARD_SIZE = 256
OPUS_BITRATE = "96k"


class ShardError(Exception):
    """Raised when a shard cannot be produced."""


AudioEncoder = Callable[[Path], bytes]


def encode_opus(source: Path, bitrate: str = OPUS_BITRATE) -> bytes:
    """Transcode any ffmpeg-readable audio to mono opus.

    Mono because the loader casts to ``num_channels=1`` anyway, and opus because
    that is the column name the loader reads -- ``datasets`` decodes by content,
    but a corpus that is interchangeable with upstream's is worth the certainty.

    Raises:
        ShardError: when ffmpeg is missing or fails.

    """
    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-i",
        str(source),
        "-ac",
        "1",
        "-c:a",
        "libopus",
        "-b:a",
        bitrate,
        "-f",
        "ogg",
        "pipe:1",
    ]
    try:
        result = subprocess.run(command, capture_output=True, check=False)
    except FileNotFoundError as exc:  # pragma: no cover - environment guard
        raise ShardError("ffmpeg is not installed") from exc
    if result.returncode != 0 or not result.stdout:
        raise ShardError(f"ffmpeg failed on {source}: {result.stderr.decode()[-300:]}")
    return result.stdout


def _add_member(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    """Append one in-memory member to an open tar."""
    info = tarfile.TarInfo(name=name)
    info.size = len(payload)
    archive.addfile(info, io.BytesIO(payload))


def write_shard(
    samples: Sequence[tuple[MapsetSample, Path]],
    destination: Path,
    encoder: AudioEncoder | None = None,
) -> int:
    """Write one ``.tar`` shard, returning how many samples it holds.

    A sample whose audio cannot be encoded is skipped rather than aborting the
    build -- one unreadable file should not cost an hour of work.
    """
    encode = encoder if encoder is not None else encode_opus
    destination.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with tarfile.open(destination, "w") as archive:
        for sample, audio_path in samples:
            try:
                audio = encode(audio_path)
            except ShardError:
                continue
            key = f"{written:06d}"
            payload = json.dumps(sample.to_json_payload()).encode("utf-8")
            _add_member(archive, f"{key}.json", payload)
            _add_member(archive, f"{key}.opus", audio)
            written += 1
    if written == 0:
        destination.unlink(missing_ok=True)
    return written


def chunk(items: Sequence[object], size: int) -> Iterable[Sequence[object]]:
    """Split ``items`` into consecutive runs of at most ``size``."""
    if size < 1:
        raise ValueError("shard size must be positive")
    for start in range(0, len(items), size):
        yield items[start : start + size]


def verify_shard(path: Path) -> tuple[int, list[str]]:
    """Re-read a shard, returning its sample count and any problems found.

    Checks the loader's own preconditions: paired members, parseable json, a
    non-empty ``beatmaps`` list, and the fields upstream reads with ``[]``.
    """
    problems: list[str] = []
    with tarfile.open(path) as archive:
        names = archive.getnames()
        keys = sorted({name.split(".", 1)[0] for name in names})
        for key in keys:
            if f"{key}.json" not in names:
                problems.append(f"{key}: missing .json")
                continue
            if f"{key}.opus" not in names:
                problems.append(f"{key}: missing .opus")
                continue
            handle = archive.extractfile(f"{key}.json")
            if handle is None:  # pragma: no cover - tarfile guarantees a member
                problems.append(f"{key}: unreadable .json")
                continue
            payload = json.loads(handle.read().decode("utf-8"))
            beatmaps = payload.get("beatmaps") or []
            if not beatmaps:
                problems.append(f"{key}: no beatmaps")
                continue
            for index, beatmap in enumerate(beatmaps):
                missing = [
                    f
                    for f in ("beatmap_id", "beatmapset_id", "mode", "creator_id", "content")
                    if beatmap.get(f) is None
                ]
                if missing:
                    problems.append(f"{key}[{index}]: missing {','.join(missing)}")
    return len(keys), problems
