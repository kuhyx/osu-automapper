"""Mode-independent checks.

Thresholds come from the osu! Simplified Ranking Criteria; each function documents
the rule it encodes so the numbers are auditable rather than invented.
"""

from __future__ import annotations

from osu_automapper.parse import Beatmap
from osu_automapper.report import CheckResult, Severity

# RC: objects must be snapped to the timeline; >2 ms of error is unsnapped.
SNAP_TOLERANCE_MS = 2.0
# Beat divisors the osu! editor can represent, including lazer's 1/5, 1/7 and 1/9.
# Measured over 300 ranked maps: dropping the triplet family reports 11 false
# unsnapped maps, dropping the lazer family a further 5. The remaining ~2% are
# real editor imprecision that ranked maps genuinely ship.
BEAT_DIVISORS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 16)
# The model leaves these placeholders when no reference beatmap supplies metadata.
PLACEHOLDER_METADATA = frozenset({"unknown title", "unknown artist", "unknown"})
# RC: drain time must be at least 30 seconds.
MIN_DRAIN_SECONDS = 30.0
REQUIRED_METADATA = ("Title", "Artist", "Creator", "Version")


def check_has_objects(beatmap: Beatmap) -> CheckResult:
    """Check that the beatmap has at least one hit object."""
    count = len(beatmap.hit_objects)
    return CheckResult(
        name="has_objects",
        passed=count > 0,
        message=f"{count} hit object(s)",
    )


def check_drain_time(beatmap: Beatmap) -> CheckResult:
    """Drain time must be at least 30 s (Simplified RC)."""
    drain = beatmap.drain_time_seconds
    return CheckResult(
        name="drain_time",
        passed=drain >= MIN_DRAIN_SECONDS,
        message=f"{drain:.1f}s (minimum {MIN_DRAIN_SECONDS:.0f}s)",
    )


def check_metadata_present(beatmap: Beatmap) -> CheckResult:
    """Title, Artist, Creator and Version must be non-empty."""
    missing = [
        k
        for k in REQUIRED_METADATA
        if not beatmap.metadata.get(k, "").strip()
        or beatmap.metadata[k].strip().lower() in PLACEHOLDER_METADATA
    ]
    return CheckResult(
        name="metadata_present",
        passed=not missing,
        message="all present" if not missing else f"missing: {', '.join(missing)}",
    )


def check_audio_filename(beatmap: Beatmap) -> CheckResult:
    """Audio must be declared and use a legal container (.mp3/.ogg)."""
    name = beatmap.audio_filename
    if not name:
        return CheckResult(name="audio_filename", passed=False, message="AudioFilename unset")
    legal = name.lower().endswith((".mp3", ".ogg"))
    return CheckResult(
        name="audio_filename",
        passed=legal,
        message=f"{name}" if legal else f"{name}: must be .mp3 or .ogg",
    )


def check_preview_time(beatmap: Beatmap) -> CheckResult:
    """PreviewTime must be set (RC requires a preview point)."""
    preview = beatmap.preview_time
    return CheckResult(
        name="preview_time",
        passed=preview >= 0,
        message=f"{preview} ms" if preview >= 0 else "PreviewTime unset (-1)",
    )


def check_has_uninherited_timing(beatmap: Beatmap) -> CheckResult:
    """At least one uninherited (red) timing point is required."""
    count = len(beatmap.uninherited_points)
    return CheckResult(
        name="uninherited_timing",
        passed=count >= 1,
        message=f"{count} uninherited timing point(s)",
    )


def check_no_duplicate_timing_points(beatmap: Beatmap) -> CheckResult:
    """No two uninherited (or two inherited) points may share a timestamp."""
    dupes: list[float] = []
    for group in (True, False):
        times = [t.time for t in beatmap.timing_points if t.uninherited is group]
        seen: set[float] = set()
        for t in times:
            if t in seen:
                dupes.append(t)
            seen.add(t)
    return CheckResult(
        name="no_duplicate_timing_points",
        passed=not dupes,
        message="none" if not dupes else f"duplicates at {sorted(set(dupes))}",
    )


def check_inherited_after_uninherited(beatmap: Beatmap) -> CheckResult:
    """No inherited (green) point may precede the first uninherited point."""
    uninherited = beatmap.uninherited_points
    if not uninherited:
        return CheckResult(
            name="inherited_after_uninherited",
            passed=False,
            message="no uninherited point to order against",
        )
    first = min(t.time for t in uninherited)
    early = [t.time for t in beatmap.timing_points if not t.uninherited and t.time < first]
    return CheckResult(
        name="inherited_after_uninherited",
        passed=not early,
        message="ok" if not early else f"{len(early)} inherited point(s) before {first}",
    )


def _snap_error(time: int, anchor: float, beat_length: float, divisor: int) -> float:
    """Distance in ms from ``time`` to the nearest ``1/divisor`` gridline."""
    division = beat_length / divisor
    offset = (time - anchor) % division
    return min(offset, division - offset)


def check_objects_snapped(beatmap: Beatmap) -> CheckResult:
    """Objects must sit within 2 ms of some legal beat division.

    An object counts as snapped when *any* divisor in :data:`BEAT_DIVISORS` places
    it on-grid, mirroring the editor: a triplet-timed map is correctly snapped at
    1/12 even though it looks unsnapped at 1/16.
    """
    uninherited = sorted(beatmap.uninherited_points, key=lambda t: t.time)
    if not uninherited or not beatmap.hit_objects:
        return CheckResult(
            name="objects_snapped",
            passed=False,
            message="needs timing points and objects",
            severity=Severity.WARNING,
        )
    unsnapped: list[int] = []
    first_red = uninherited[0].time
    for obj in beatmap.hit_objects:
        # Objects before the first red line have no beat to snap against; modular
        # arithmetic on a negative offset would silently invent a passing result.
        if obj.time < first_red:
            unsnapped.append(obj.time)
            continue
        active = uninherited[0]
        for point in uninherited:
            if point.time <= obj.time:
                active = point
            else:
                break
        if active.beat_length <= 0:
            continue
        best = min(_snap_error(obj.time, active.time, active.beat_length, d) for d in BEAT_DIVISORS)
        if best > SNAP_TOLERANCE_MS:
            unsnapped.append(obj.time)
    return CheckResult(
        name="objects_snapped",
        passed=not unsnapped,
        message="all snapped"
        if not unsnapped
        else f"{len(unsnapped)} unsnapped (e.g. {unsnapped[:3]})",
    )


COMMON_CHECKS = (
    check_has_objects,
    check_drain_time,
    check_metadata_present,
    check_audio_filename,
    check_preview_time,
    check_has_uninherited_timing,
    check_no_duplicate_timing_points,
    check_inherited_after_uninherited,
    check_objects_snapped,
)
