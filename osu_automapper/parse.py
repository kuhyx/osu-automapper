"""Minimal, dependency-light ``.osu`` reader.

``slider`` is an upstream dependency and handles ranked maps well, but it raises on
several shapes freshly generated output can take. The gate must be able to *report*
those instead of dying, so parsing is done here over the plain text sections and
kept deliberately tolerant; individual checks decide what is fatal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path


class Mode(IntEnum):
    """osu! gamemode, as stored in the ``Mode:`` key."""

    STANDARD = 0
    TAIKO = 1
    CATCH = 2
    MANIA = 3


class BeatmapParseError(Exception):
    """Raised when a file cannot be read as a beatmap at all."""


@dataclass(frozen=True)
class TimingPoint:
    """One line of ``[TimingPoints]``."""

    time: float
    beat_length: float
    uninherited: bool

    @property
    def bpm(self) -> float | None:
        """BPM for uninherited points, else None."""
        if not self.uninherited or self.beat_length <= 0:
            return None
        return 60000.0 / self.beat_length


@dataclass(frozen=True)
class HitObject:
    """One line of ``[HitObjects]``."""

    x: int
    y: int
    time: int
    type_flags: int
    raw: str

    @property
    def is_circle(self) -> bool:
        """True for hit circles."""
        return bool(self.type_flags & 1)

    @property
    def is_slider(self) -> bool:
        """True for sliders."""
        return bool(self.type_flags & 2)

    @property
    def is_spinner(self) -> bool:
        """True for spinners."""
        return bool(self.type_flags & 8)

    @property
    def is_hold(self) -> bool:
        """True for mania hold notes."""
        return bool(self.type_flags & 128)

    @property
    def end_time(self) -> int:
        """End time for spinners/holds; equal to ``time`` otherwise."""
        if self.is_spinner or self.is_hold:
            parts = self.raw.split(",")
            if len(parts) >= 6:
                tail = parts[5].split(":")[0]
                try:
                    return int(float(tail))
                except ValueError:
                    return self.time
        return self.time


@dataclass
class Beatmap:
    """Parsed beatmap: only what the gates actually inspect."""

    path: Path
    format_version: int
    general: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)
    difficulty: dict[str, str] = field(default_factory=dict)
    timing_points: list[TimingPoint] = field(default_factory=list)
    hit_objects: list[HitObject] = field(default_factory=list)

    @property
    def mode(self) -> Mode:
        """Gamemode, defaulting to standard when absent."""
        try:
            return Mode(int(self.general.get("Mode", "0")))
        except ValueError:
            return Mode.STANDARD

    @property
    def audio_filename(self) -> str:
        """Value of ``AudioFilename``."""
        return self.general.get("AudioFilename", "")

    @property
    def preview_time(self) -> int:
        """Value of ``PreviewTime``, -1 when unset."""
        try:
            return int(self.general.get("PreviewTime", "-1"))
        except ValueError:
            return -1

    @property
    def uninherited_points(self) -> list[TimingPoint]:
        """Only the uninherited (red) timing points."""
        return [t for t in self.timing_points if t.uninherited]

    @property
    def drain_time_seconds(self) -> float:
        """Rough drain time: first object start to last object end."""
        if not self.hit_objects:
            return 0.0
        start = min(o.time for o in self.hit_objects)
        end = max(o.end_time for o in self.hit_objects)
        return (end - start) / 1000.0

    @property
    def circle_size(self) -> float:
        """CircleSize; doubles as mania keycount."""
        try:
            return float(self.difficulty.get("CircleSize", "5"))
        except ValueError:
            return 5.0


def _parse_kv(line: str) -> tuple[str, str] | None:
    """Split a ``Key: Value`` line, returning None when there is no colon."""
    if ":" not in line:
        return None
    key, _, value = line.partition(":")
    return key.strip(), value.strip()


def _parse_timing_point(line: str) -> TimingPoint | None:
    """Parse one ``[TimingPoints]`` line, or None when malformed."""
    parts = line.split(",")
    if len(parts) < 2:
        return None
    try:
        time = float(parts[0])
        beat_length = float(parts[1])
    except ValueError:
        return None
    # Field 6 is the uninherited flag; older formats omit it and imply uninherited.
    uninherited = True
    if len(parts) >= 7:
        uninherited = parts[6].strip() == "1"
    return TimingPoint(time=time, beat_length=beat_length, uninherited=uninherited)


def _parse_hit_object(line: str) -> HitObject | None:
    """Parse one ``[HitObjects]`` line, or None when malformed."""
    parts = line.split(",")
    if len(parts) < 4:
        return None
    try:
        return HitObject(
            x=int(float(parts[0])),
            y=int(float(parts[1])),
            time=int(float(parts[2])),
            type_flags=int(parts[3]),
            raw=line,
        )
    except ValueError:
        return None


def parse_beatmap(path: Path) -> Beatmap:
    """Read a ``.osu`` file into a :class:`Beatmap`.

    Raises:
        BeatmapParseError: when the file is unreadable or lacks the format header.

    """
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise BeatmapParseError(f"cannot read {path}: {exc}") from exc

    lines = text.splitlines()
    version = 0
    for line in lines:
        if "osu file format v" in line:
            try:
                version = int(line.split("osu file format v")[1].strip())
            except IndexError, ValueError:
                version = 0
            break
    else:
        raise BeatmapParseError(f"{path}: missing 'osu file format' header")

    beatmap = Beatmap(path=path, format_version=version)
    discarded: dict[str, str] = {}
    kv_destinations: dict[str, dict[str, str]] = {
        "General": beatmap.general,
        "Metadata": beatmap.metadata,
        "Difficulty": beatmap.difficulty,
        "Editor": discarded,
    }
    section = ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        # Explicit destination lookup: [Editor] is a key/value section we parse but
        # deliberately keep nothing from, and a dict makes that a data fact rather
        # than an unreachable branch.
        destination = kv_destinations.get(section)
        if destination is not None:
            kv = _parse_kv(line)
            if kv is not None:
                destination[kv[0]] = kv[1]
        elif section == "TimingPoints":
            tp = _parse_timing_point(line)
            if tp is not None:
                beatmap.timing_points.append(tp)
        elif section == "HitObjects":
            ho = _parse_hit_object(line)
            if ho is not None:
                beatmap.hit_objects.append(ho)
    return beatmap
