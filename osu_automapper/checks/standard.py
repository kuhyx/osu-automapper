"""osu!standard-specific checks."""

from __future__ import annotations

from itertools import pairwise

from osu_automapper.parse import Beatmap
from osu_automapper.report import CheckResult

PLAYFIELD_WIDTH = 512
PLAYFIELD_HEIGHT = 384
# RC: a circle needs >=10 ms before the next object, a slider end >=20 ms.
MIN_GAP_AFTER_CIRCLE_MS = 10
MIN_GAP_AFTER_SLIDER_MS = 20


def check_positions_in_playfield(beatmap: Beatmap) -> CheckResult:
    """Every object must sit inside the 512x384 playfield."""
    offscreen = [
        o.time
        for o in beatmap.hit_objects
        if not o.is_spinner and not (0 <= o.x <= PLAYFIELD_WIDTH and 0 <= o.y <= PLAYFIELD_HEIGHT)
    ]
    return CheckResult(
        name="positions_in_playfield",
        passed=not offscreen,
        message="all in bounds"
        if not offscreen
        else f"{len(offscreen)} offscreen (e.g. {offscreen[:3]})",
    )


def check_no_simultaneous_objects(beatmap: Beatmap) -> CheckResult:
    """Two standard objects may not start on the same millisecond."""
    seen: set[int] = set()
    clashes: list[int] = []
    for obj in beatmap.hit_objects:
        if obj.time in seen:
            clashes.append(obj.time)
        seen.add(obj.time)
    return CheckResult(
        name="no_simultaneous_objects",
        passed=not clashes,
        message="none" if not clashes else f"{len(clashes)} collision(s) (e.g. {clashes[:3]})",
    )


def check_object_gaps(beatmap: Beatmap) -> CheckResult:
    """Objects must not follow each other faster than the RC minimum gap."""
    ordered = sorted(beatmap.hit_objects, key=lambda o: o.time)
    violations: list[str] = []
    for previous, current in pairwise(ordered):
        required = MIN_GAP_AFTER_SLIDER_MS if previous.is_slider else MIN_GAP_AFTER_CIRCLE_MS
        gap = current.time - previous.end_time
        if 0 <= gap < required:
            violations.append(f"{previous.time}->{current.time} ({gap}ms < {required}ms)")
    return CheckResult(
        name="object_gaps",
        passed=not violations,
        message="ok"
        if not violations
        else f"{len(violations)} too-close pair(s): {violations[:2]}",
    )


def check_slider_velocity_finite(beatmap: Beatmap) -> CheckResult:
    """SliderMultiplier must be a finite, positive number."""
    raw = beatmap.difficulty.get("SliderMultiplier", "")
    try:
        value = float(raw)
    except ValueError:
        return CheckResult(
            name="slider_velocity_finite",
            passed=False,
            message=f"SliderMultiplier unparseable: {raw!r}",
        )
    ok = value > 0 and value == value and value != float("inf")
    return CheckResult(
        name="slider_velocity_finite",
        passed=ok,
        message=f"{value}" if ok else f"invalid SliderMultiplier: {value}",
    )


STANDARD_CHECKS = (
    check_positions_in_playfield,
    check_no_simultaneous_objects,
    check_object_gaps,
    check_slider_velocity_finite,
)
