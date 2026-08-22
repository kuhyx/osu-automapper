"""Aggregate sweep outcomes into the tables the session was run to produce.

Every number here is a count or a mean of recorded exit-code verdicts. Nothing
is inferred, and a cell that failed to generate is never silently dropped -- it
appears as a generation failure, which is itself a reliability finding.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from statistics import mean

from osu_automapper.sweep.model import SweepOutcome

MODE_NAMES = {0: "std", 1: "taiko", 2: "catch", 3: "mania"}


@dataclass(frozen=True)
class Bucket:
    """Summary of every outcome sharing one key."""

    key: str
    total: int
    generated: int
    raw_pass: int
    repaired_pass: int
    defects: int
    mean_star_error: float | None
    mean_objects: float | None

    def _rate(self, numerator: int) -> str:
        """Format ``numerator`` as a percentage of the bucket size."""
        return "n/a" if not self.total else f"{100.0 * numerator / self.total:.0f}%"

    @property
    def raw_pass_rate(self) -> str:
        """Share of cells whose untouched output passed the gate."""
        return self._rate(self.raw_pass)

    @property
    def repaired_pass_rate(self) -> str:
        """Share of cells that passed after repair."""
        return self._rate(self.repaired_pass)

    @property
    def defect_rate(self) -> str:
        """Share of cells where the stacked-at-zero artifact fired."""
        return self._rate(self.defects)


def _summarise(key: str, rows: Sequence[SweepOutcome]) -> Bucket:
    """Reduce the outcomes sharing ``key`` to one row."""
    errors = [r.star_error for r in rows if r.star_error is not None]
    objects = [float(r.objects) for r in rows if r.objects]
    return Bucket(
        key=key,
        total=len(rows),
        generated=sum(1 for r in rows if r.generated),
        raw_pass=sum(1 for r in rows if r.raw_passed),
        repaired_pass=sum(1 for r in rows if r.repaired_passed),
        defects=sum(1 for r in rows if r.defect_fired),
        mean_star_error=round(mean(errors), 2) if errors else None,
        mean_objects=round(mean(objects), 0) if objects else None,
    )


def aggregate(outcomes: Iterable[SweepOutcome], key: Callable[[SweepOutcome], str]) -> list[Bucket]:
    """Group outcomes by ``key`` and summarise each group."""
    grouped: dict[str, list[SweepOutcome]] = {}
    for outcome in outcomes:
        grouped.setdefault(key(outcome), []).append(outcome)
    return [_summarise(name, rows) for name, rows in sorted(grouped.items())]


def _table(title: str, buckets: Sequence[Bucket], header: str) -> list[str]:
    """Render one markdown table."""
    lines = [
        f"### {title}",
        "",
        f"| {header} | n | generated | raw pass | after repair "
        "| t=0 defect | mean star error | mean objects |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for b in buckets:
        star = "n/a" if b.mean_star_error is None else f"{b.mean_star_error:+.2f}"
        objects = "n/a" if b.mean_objects is None else f"{b.mean_objects:.0f}"
        lines.append(
            f"| {b.key} | {b.total} | {b.generated} | {b.raw_pass_rate} | "
            f"{b.repaired_pass_rate} | {b.defect_rate} | {star} | {objects} |"
        )
    lines.append("")
    return lines


def _mode_name(outcome: SweepOutcome) -> str:
    """Human-readable gamemode."""
    return MODE_NAMES.get(outcome.mode, str(outcome.mode))


def to_markdown(outcomes: Sequence[SweepOutcome]) -> str:
    """Render the full report: overall, then by each axis of the grid."""
    if not outcomes:
        return "No sweep results.\n"

    overall = _summarise("all", outcomes)
    lines = [
        "# Reliability sweep",
        "",
        f"{overall.total} cells, {overall.generated} generated. "
        f"Raw pass {overall.raw_pass_rate}, after repair {overall.repaired_pass_rate}, "
        f"t=0 defect {overall.defect_rate}.",
        "",
        "`raw pass` gates the model's untouched output; `after repair` gates it once",
        "`repair` has stripped the known stacked-at-zero artifact. A green gate never",
        "implies rankability -- see `docs/ranking-criteria.md`.",
        "",
    ]
    lines += _table("By difficulty", aggregate(outcomes, lambda o: f"{o.difficulty:g}*"), "target")
    lines += _table("By gamemode", aggregate(outcomes, _mode_name), "mode")
    lines += _table("By song", aggregate(outcomes, lambda o: o.song), "song")
    lines += _table("By adapter", aggregate(outcomes, lambda o: o.adapter), "adapter")

    failures = sorted({name for o in outcomes for name in o.repaired_failures})
    if failures:
        lines += ["### Failing checks after repair", ""]
        counts = {
            name: sum(1 for o in outcomes if name in o.repaired_failures) for name in failures
        }
        lines += [f"- `{name}`: {count} cell(s)" for name, count in sorted(counts.items())]
        lines.append("")

    broken = [o for o in outcomes if not o.generated]
    if broken:
        lines += ["### Cells that failed to generate", ""]
        lines += [f"- `{o.label}`: {o.error or 'unknown error'}" for o in broken]
        lines.append("")
    return "\n".join(lines)
