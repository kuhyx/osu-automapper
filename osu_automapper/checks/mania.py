"""osu!mania-specific checks.

Mania stores the column in the ``x`` field: ``column = floor(x * keycount / 512)``.
A standard-only validator silently passes garbage here, which is why the suite
dispatches on ``Mode:``.
"""

from __future__ import annotations

from osu_automapper.parse import Beatmap
from osu_automapper.report import CheckResult

PLAYFIELD_WIDTH = 512


def column_of(x: int, keycount: int) -> int:
    """Map an ``x`` coordinate to a zero-based mania column."""
    if keycount <= 0:
        return -1
    return int(x * keycount // PLAYFIELD_WIDTH)


def check_keycount_sane(beatmap: Beatmap) -> CheckResult:
    """CircleSize doubles as the mania key count and must be a whole 1..18."""
    keys = beatmap.circle_size
    ok = keys.is_integer() and 1 <= keys <= 18
    return CheckResult(
        name="keycount_sane",
        passed=ok,
        message=f"{int(keys)}K" if ok else f"invalid keycount from CircleSize={keys}",
    )


def check_columns_in_range(beatmap: Beatmap) -> CheckResult:
    """Check that every note lands in a column the key count actually has."""
    keys = int(beatmap.circle_size)
    if keys <= 0:
        return CheckResult(name="columns_in_range", passed=False, message="keycount unusable")
    bad = [o.time for o in beatmap.hit_objects if not 0 <= column_of(o.x, keys) < keys]
    return CheckResult(
        name="columns_in_range",
        passed=not bad,
        message=f"all within {keys} column(s)"
        if not bad
        else f"{len(bad)} out of range (e.g. {bad[:3]})",
    )


def check_hold_notes_ordered(beatmap: Beatmap) -> CheckResult:
    """Hold notes must end strictly after they start."""
    bad = [o.time for o in beatmap.hit_objects if o.is_hold and o.end_time <= o.time]
    return CheckResult(
        name="hold_notes_ordered",
        passed=not bad,
        message="ok" if not bad else f"{len(bad)} zero/negative-length hold(s) (e.g. {bad[:3]})",
    )


def check_no_column_collisions(beatmap: Beatmap) -> CheckResult:
    """Check that no single column holds two notes at the same millisecond."""
    keys = int(beatmap.circle_size)
    if keys <= 0:
        return CheckResult(name="no_column_collisions", passed=False, message="keycount unusable")
    seen: set[tuple[int, int]] = set()
    clashes: list[int] = []
    for obj in beatmap.hit_objects:
        key = (column_of(obj.x, keys), obj.time)
        if key in seen:
            clashes.append(obj.time)
        seen.add(key)
    return CheckResult(
        name="no_column_collisions",
        passed=not clashes,
        message="none" if not clashes else f"{len(clashes)} collision(s) (e.g. {clashes[:3]})",
    )


MANIA_CHECKS = (
    check_keycount_sane,
    check_columns_in_range,
    check_hold_notes_ordered,
    check_no_column_collisions,
)
