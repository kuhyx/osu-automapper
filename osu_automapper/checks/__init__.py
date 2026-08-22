"""Check registry: dispatches the mode-specific suite over a shared common core."""

from __future__ import annotations

from collections.abc import Callable

from osu_automapper.checks.common import COMMON_CHECKS
from osu_automapper.checks.mania import MANIA_CHECKS
from osu_automapper.checks.standard import STANDARD_CHECKS
from osu_automapper.parse import Beatmap, Mode
from osu_automapper.report import CheckResult, Report

Check = Callable[[Beatmap], CheckResult]

MODE_CHECKS: dict[Mode, tuple[Check, ...]] = {
    Mode.STANDARD: STANDARD_CHECKS,
    Mode.MANIA: MANIA_CHECKS,
    # Taiko and catch share the common core only: their rulesets are out of scope,
    # and silently applying standard's playfield rules to them would be wrong.
    Mode.TAIKO: (),
    Mode.CATCH: (),
}


def checks_for(mode: Mode) -> tuple[Check, ...]:
    """Every check that applies to ``mode``, common ones first."""
    return COMMON_CHECKS + MODE_CHECKS[mode]


def run_checks(beatmap: Beatmap) -> Report:
    """Run the applicable suite and collect the results."""
    report = Report(path=str(beatmap.path), mode=int(beatmap.mode))
    report.extend([check(beatmap) for check in checks_for(beatmap.mode)])
    return report
