"""Repair known model output defects, explicitly and never as part of checking.

`check` adjudicates and must not modify anything, or a green gate would only
mean "we already fixed it". Repair is therefore a separate, opt-in command.

The one defect handled so far is observed, not hypothetical: at low target
difficulties the model sometimes emits a cluster of hit objects stacked at
timestamp 0, far before the real first object. Measured across three seeds at
4.0 stars on the same song: 16, 0 and 1 such objects. The cluster alone pushed a
clean 4.37-star map to 10.43 stars and produced 15 simultaneous-object errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# A real map can legitimately start at 0, so a lone early object is not proof of
# corruption. The signature is a *stack*: several objects sharing timestamp 0
# while the map proper starts much later.
MIN_STACK_SIZE = 2


class RepairError(Exception):
    """Raised when a file cannot be repaired."""


@dataclass(frozen=True)
class RepairResult:
    """What a repair pass changed."""

    removed: int
    first_real_time: int | None

    @property
    def changed(self) -> bool:
        """True when anything was actually removed."""
        return self.removed > 0


def _split_sections(text: str) -> tuple[str, list[str]]:
    """Split a beatmap into everything-before-objects and the object lines."""
    head, marker, tail = text.partition("[HitObjects]")
    if not marker:
        raise RepairError("no [HitObjects] section")
    objects = [line for line in tail.splitlines() if line.strip()]
    return head, objects


def _object_time(line: str) -> int | None:
    """Parse the timestamp of a hit-object line, or None when malformed."""
    parts = line.split(",")
    if len(parts) < 3:
        return None
    try:
        return int(float(parts[2]))
    except ValueError:
        return None


def repair_text(text: str) -> tuple[str, RepairResult]:
    """Strip a leading stacked-at-zero artifact, returning the new text."""
    head, objects = _split_sections(text)
    timed = [(line, _object_time(line)) for line in objects]
    at_zero = [line for line, time in timed if time == 0]
    later = [(line, time) for line, time in timed if time is not None and time > 0]

    # Only strip when it is unambiguously the artifact: a stack at 0, and the map
    # really begins somewhere else entirely.
    if len(at_zero) < MIN_STACK_SIZE or not later:
        return text, RepairResult(removed=0, first_real_time=later[0][1] if later else None)

    kept = [line for line, time in timed if time != 0]
    repaired = head + "[HitObjects]\n" + "\n".join(kept) + "\n"
    return repaired, RepairResult(removed=len(at_zero), first_real_time=later[0][1])


def repair_file(path: Path, output: Path | None = None) -> RepairResult:
    """Repair a beatmap in place, or into ``output``.

    Raises:
        RepairError: when the file cannot be read or has no object section.

    """
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise RepairError(f"cannot read {path}: {exc}") from exc

    repaired, result = repair_text(text)
    destination = output or path
    if result.changed or output is not None:
        destination.write_text(repaired, encoding="utf-8")
    return result
