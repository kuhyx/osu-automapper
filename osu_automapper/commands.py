"""Subcommand implementations that need more than a report.

Kept out of :mod:`osu_automapper.cli` so both stay under the 250-line cap.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from osu_automapper.blindtest import build_blindtest, score_blindtest
from osu_automapper.blindtest.harness import BlindTest, pack_blindtest
from osu_automapper.config import Paths
from osu_automapper.generate import GenerationError, GenerationRequest, generate
from osu_automapper.parse import Mode

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_ERROR = 2


def run_generate(args: argparse.Namespace) -> int:
    """Generate a beatmap through upstream, returning an exit code."""
    request = GenerationRequest(
        audio_path=args.audio,
        output_path=args.output,
        mode=Mode(args.gamemode),
        difficulty=args.difficulty,
        year=args.year,
        seed=args.seed,
        keycount=args.keycount,
        title=args.title,
        artist=args.artist,
        preview_time=args.preview_time,
    )
    try:
        output = generate(request)
    except GenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"generated into {output}")
    return EXIT_OK


def run_blindtest_build(args: argparse.Namespace) -> int:
    """Pack real and generated maps into one anonymised set."""
    paths = Paths.from_env()
    try:
        test = build_blindtest(args.real, args.generated, seed=args.seed)
        archive, key_path = pack_blindtest(test, paths.blindtest, audio=args.audio)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"pack: {archive}")
    print(f"key:  {key_path}")
    last = test.entries[-1].label
    print(f"Import the .osz into lazer and play A-{last} without looking at the key.")
    return EXIT_OK


def run_blindtest_score(args: argparse.Namespace) -> int:
    """Score guesses against a saved shuffle key."""
    try:
        test = BlindTest.from_json(args.key.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"error: cannot read key {args.key}: {exc}", file=sys.stderr)
        return EXIT_ERROR

    guesses: dict[str, bool] = {}
    for item in args.guess:
        label, _, verdict = item.partition("=")
        if verdict.lower() not in {"ai", "human"}:
            print(f"error: guess must be <LABEL>=ai|human, got {item!r}", file=sys.stderr)
            return EXIT_ERROR
        guesses[label.upper()] = verdict.lower() == "ai"

    correct, total = score_blindtest(test, guesses)
    print(f"{correct}/{total} correct")
    for entry in test.entries:
        if entry.label in guesses:
            mark = "OK " if guesses[entry.label] == entry.generated else "MISS"
            origin = "generated" if entry.generated else "human"
            print(f"  {mark} {entry.label}: {origin}  ({Path(entry.source).name})")
    return EXIT_OK
