"""Command-line entry point.

Exit codes are the adjudication mechanism -- no model decides pass/fail:

* ``0`` every blocking check passed (*technically* rankable; see the note in
  :mod:`osu_automapper.report` and ``docs/ranking-criteria.md``)
* ``1`` at least one blocking check failed
* ``2`` usage, IO or parse error -- "we could not look", distinct from "it is bad"
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from osu_automapper.checks import run_checks
from osu_automapper.commands import (
    run_blindtest_build,
    run_blindtest_score,
    run_generate,
)
from osu_automapper.osz import OszError, check_osz_importable
from osu_automapper.parse import BeatmapParseError, parse_beatmap
from osu_automapper.report import CheckResult, Report
from osu_automapper.stars import (
    DEFAULT_TOLERANCE,
    RosuStarRating,
    StarRatingError,
    StarRatingProvider,
    difficulty_within_tolerance,
)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="osu-automapper",
        description="Deterministic quality gates for generated osu! beatmaps.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Gate a .osu file.")
    check.add_argument("path", type=Path, help="Path to the .osu file.")
    check.add_argument(
        "--target-difficulty",
        type=float,
        default=None,
        help="Expected star rating; enables the star-rating gate.",
    )
    check.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help=f"Allowed star deviation (default {DEFAULT_TOLERANCE}).",
    )
    check.add_argument("--lazer", action="store_true", default=True, help="Rate with lazer rules.")
    check.add_argument("--clock-rate", type=float, default=1.0, help="Clock rate for rating.")
    check.add_argument("--json", action="store_true", help="Emit JSON instead of text.")

    osz = sub.add_parser("check-osz", help="Validate a .osz archive for import.")
    osz.add_argument("path", type=Path, help="Path to the .osz file.")
    osz.add_argument("--json", action="store_true", help="Emit JSON instead of text.")

    gen = sub.add_parser("generate", help="Generate a beatmap via Mapperatorinator.")
    gen.add_argument("audio", type=Path, help="Input audio file.")
    gen.add_argument("output", type=Path, help="Output directory.")
    gen.add_argument("--gamemode", type=int, default=0, choices=[0, 1, 2, 3])
    gen.add_argument("--difficulty", type=float, default=5.5, help="Target star rating.")
    gen.add_argument("--year", type=int, default=2023, help="Mapping-style year.")
    gen.add_argument("--seed", type=int, default=None, help="Seed, for reproducibility.")
    gen.add_argument("--keycount", type=int, default=None, help="Mania key count.")
    gen.add_argument("--title", default=None, help="Song title (else 'Unknown Title').")
    gen.add_argument("--artist", default=None, help="Song artist.")
    gen.add_argument("--preview-time", type=int, default=None, help="Preview point in ms.")

    build = sub.add_parser("blindtest", help="Pack real and generated maps anonymously.")
    build.add_argument("--real", type=Path, nargs="+", required=True)
    build.add_argument("--generated", type=Path, nargs="+", required=True)
    build.add_argument("--audio", type=Path, default=None, help="Audio to pack alongside.")
    build.add_argument("--seed", type=int, default=None, help="Shuffle seed.")

    score = sub.add_parser("blindtest-score", help="Score guesses against a saved key.")
    score.add_argument("key", type=Path, help="Path to the saved <ts>.json key.")
    score.add_argument("guess", nargs="+", help="Guesses as A=ai B=human ...")
    return parser


def _star_check(
    report: Report, path: Path, target: float, tolerance: float, provider: StarRatingProvider
) -> None:
    """Append the star-rating result, or a failure explaining why it is absent."""
    try:
        actual = provider.rate(path)
    except StarRatingError as exc:
        report.add(CheckResult(name="star_rating", passed=False, message=str(exc)))
        return
    ok = difficulty_within_tolerance(actual, target, tolerance)
    report.add(
        CheckResult(
            name="star_rating",
            passed=ok,
            message=f"{actual:.2f}* (target {target:.2f}* +-{tolerance:.2f})",
        )
    )


def run_check(args: argparse.Namespace, provider: StarRatingProvider | None = None) -> int:
    """Execute the ``check`` subcommand and return its exit code."""
    try:
        beatmap = parse_beatmap(args.path)
    except BeatmapParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    report = run_checks(beatmap)
    if args.target_difficulty is not None:
        rater = provider or RosuStarRating(lazer=args.lazer, clock_rate=args.clock_rate)
        _star_check(report, args.path, args.target_difficulty, args.tolerance, rater)

    print(report.to_json() if args.json else report.to_text())
    return EXIT_OK if report.technically_rankable else EXIT_FAILED


def run_check_osz(args: argparse.Namespace) -> int:
    """Execute the ``check-osz`` subcommand and return its exit code."""
    try:
        results = check_osz_importable(args.path)
    except OszError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    report = Report(path=str(args.path), mode=-1)
    report.extend(results)
    print(report.to_json() if args.json else report.to_text())
    return EXIT_OK if report.technically_rankable else EXIT_FAILED


def main(argv: Sequence[str] | None = None, provider: StarRatingProvider | None = None) -> int:
    """CLI entry point."""
    args = build_parser().parse_args(argv)
    dispatch = {
        "check-osz": run_check_osz,
        "generate": run_generate,
        "blindtest": run_blindtest_build,
        "blindtest-score": run_blindtest_score,
    }
    handler = dispatch.get(args.command)
    if handler is not None:
        return handler(args)
    return run_check(args, provider)
