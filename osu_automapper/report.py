"""Result types for the gate suite.

A check never raises for a *map* problem: it returns a ``CheckResult``. Exceptions
are reserved for IO/parse faults, which the CLI maps to exit code 2. This keeps
"the map is bad" (exit 1) and "we could not look" (exit 2) distinguishable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    """How a failed check should affect the exit code."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a single named check."""

    name: str
    passed: bool
    message: str
    severity: Severity = Severity.ERROR

    @property
    def is_blocking(self) -> bool:
        """True when this result must fail the run."""
        return not self.passed and self.severity is Severity.ERROR


@dataclass
class Report:
    """Aggregated results for one beatmap."""

    path: str
    mode: int
    results: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        """Append a single check result."""
        self.results.append(result)

    def extend(self, results: list[CheckResult]) -> None:
        """Append several check results."""
        self.results.extend(results)

    @property
    def failures(self) -> list[CheckResult]:
        """Every blocking failure."""
        return [r for r in self.results if r.is_blocking]

    @property
    def warnings(self) -> list[CheckResult]:
        """Every non-blocking failure."""
        return [r for r in self.results if not r.passed and r.severity is Severity.WARNING]

    @property
    def technically_rankable(self) -> bool:
        """True when no blocking check failed.

        Named *technically* rankable on purpose: the osu! Ranking Criteria forbids
        generative tooling outright, so a green result never implies eligibility.
        See ``docs/ranking-criteria.md``.
        """
        return not self.failures

    def to_json(self) -> str:
        """Serialise the whole report."""
        return json.dumps(
            {
                "path": self.path,
                "mode": self.mode,
                "technically_rankable": self.technically_rankable,
                "results": [asdict(r) for r in self.results],
            },
            indent=2,
        )

    def to_text(self) -> str:
        """Human-readable summary."""
        lines = [
            f"{'PASS' if r.passed else r.severity.value.upper()}  {r.name}: {r.message}"
            for r in self.results
        ]
        verdict = (
            "technically rankable" if self.technically_rankable else "NOT technically rankable"
        )
        lines.append(
            f"-- {verdict} ({len(self.failures)} error(s), {len(self.warnings)} warning(s))"
        )
        return "\n".join(lines)
