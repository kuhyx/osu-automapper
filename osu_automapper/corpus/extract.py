"""Read mapsets out of the local lazer blob store.

lazer stores every file content-addressed with no extension, so blobs are
classified by sniffing their first bytes. See ``docs/lazer-library.md`` for the
measured yields and for the Realm-scraping approach that does **not** work.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

OSU_SIGNATURE = b"osu file format"
AUDIO_SIGNATURES = (b"ID3", b"\xff\xfb", b"OggS", b"RIFF")
_SECTION = re.compile(r"^\[(\w+)\]", re.MULTILINE)


def is_beatmap(head: bytes) -> bool:
    """Report whether a blob's first bytes mark it as a ``.osu`` file."""
    return OSU_SIGNATURE in head


def is_audio(head: bytes) -> bool:
    """Report whether a blob's first bytes mark it as an audio file."""
    return any(head.startswith(signature) for signature in AUDIO_SIGNATURES)


def classify(blob: Path) -> str:
    """Return ``"beatmap"``, ``"audio"`` or ``"other"`` for one blob."""
    with blob.open("rb") as handle:
        head = handle.read(512)
    if is_beatmap(head):
        return "beatmap"
    return "audio" if is_audio(head) else "other"


@dataclass(frozen=True)
class ParsedBeatmap:
    """The parts of a ``.osu`` file the corpus needs."""

    path: Path
    text: str
    fields: dict[str, str]
    object_count: int
    circle_count: int
    slider_count: int
    spinner_count: int
    last_object_ms: int
    first_object_ms: int

    @property
    def mode(self) -> int:
        """Osu! gamemode, defaulting to standard when unstated."""
        return int(self.fields.get("Mode", "0") or 0)


def _read_fields(text: str) -> dict[str, str]:
    """Collect ``Key: value`` pairs from the header sections."""
    body = text.split("[HitObjects]")[0]
    fields: dict[str, str] = {}
    for line in body.splitlines():
        key, sep, value = line.partition(":")
        key = key.strip()
        if sep and key and not key.startswith("//") and key not in fields:
            fields[key] = value.strip()
    return fields


def _object_times(text: str) -> tuple[list[int], list[int]]:
    """Return hit-object timestamps and their type flags."""
    part = text.split("[HitObjects]")
    if len(part) < 2:
        return [], []
    times: list[int] = []
    types: list[int] = []
    for line in part[1].strip().splitlines():
        columns = line.split(",")
        if len(columns) < 4:
            continue
        try:
            times.append(int(float(columns[2])))
            types.append(int(columns[3]))
        except ValueError:
            continue
    return times, types


def parse_beatmap_blob(path: Path) -> ParsedBeatmap | None:
    """Parse one blob into the fields the corpus needs, or None if unusable."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if OSU_SIGNATURE.decode() not in text[:64]:
        return None
    times, types = _object_times(text)
    if not times:
        return None
    return ParsedBeatmap(
        path=path,
        text=text,
        fields=_read_fields(text),
        object_count=len(times),
        circle_count=sum(1 for t in types if t & 1),
        slider_count=sum(1 for t in types if t & 2),
        spinner_count=sum(1 for t in types if t & 8),
        last_object_ms=max(times),
        first_object_ms=min(times),
    )


def iter_blobs(root: Path) -> Iterator[Path]:
    """Yield every file in the blob store, deterministically ordered."""
    yield from sorted(p for p in root.rglob("*") if p.is_file())


def bpm_of(text: str) -> float:
    """Derive BPM from the first uninherited timing point."""
    part = text.split("[TimingPoints]")
    if len(part) < 2:
        return 0.0
    for line in part[1].split("\n[")[0].strip().splitlines():
        columns = line.split(",")
        if len(columns) < 2:
            continue
        try:
            beat_length = float(columns[1])
        except ValueError:
            continue
        if beat_length > 0:
            return round(60000.0 / beat_length, 3)
    return 0.0
