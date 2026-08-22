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
from osu_automapper.corpus.pipeline import assemble, collect, probe_audio, write_corpus
from osu_automapper.generate import GenerationError, GenerationRequest, generate
from osu_automapper.parse import Mode
from osu_automapper.repair import RepairError, repair_file
from osu_automapper.stars import RosuStarRating, StarRatingError
from osu_automapper.sweep.model import SweepGrid, SweepOutcome, iter_cells
from osu_automapper.sweep.report import to_markdown
from osu_automapper.sweep.runner import run_sweep

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
        lora_path=args.lora_path,
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


def _sweep_grid(args: argparse.Namespace, paths: Paths) -> SweepGrid:
    """Build the grid described by the parsed arguments.

    Raises:
        ValueError: when no audio is available to sweep over.

    """
    songs = list(args.songs) if args.songs else sorted(paths.songs.glob("*.mp3"))
    if not songs:
        raise ValueError(f"no songs given and none found in {paths.songs}")
    # Base is always swept so every adapter has something to be compared against.
    adapters: list[Path | None] = [None, *(args.lora_paths or [])]
    return SweepGrid(
        songs=songs,
        difficulties=list(args.difficulties),
        modes=[Mode(m) for m in args.gamemodes],
        seeds=list(args.seeds),
        adapters=adapters,
        mania_keycount=args.keycount,
    )


def run_sweep_command(args: argparse.Namespace) -> int:
    """Run a reliability sweep and write its markdown report."""
    paths = Paths.from_env()
    try:
        grid = _sweep_grid(args, paths)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(f"grid: {grid.size} cells ({len(grid.songs)} songs)")
    if args.dry_run:
        for cell in iter_cells(grid):
            print(f"  {cell.label}")
        return EXIT_OK

    def progress(outcome: SweepOutcome) -> None:
        state = (
            "gen-fail" if not outcome.generated else ("pass" if outcome.repaired_passed else "FAIL")
        )
        print(f"  {outcome.label}: {state} ({outcome.duration_seconds:.0f}s)", flush=True)

    outcomes = run_sweep(grid, paths.sweep, paths.out / "sweep", on_result=progress)
    report_path = args.report or (paths.sweep / "REPORT.md")
    report_path.write_text(to_markdown(outcomes), encoding="utf-8")
    print(f"report: {report_path}")
    return EXIT_OK if all(o.generated for o in outcomes) else EXIT_FAILED


def run_corpus_command(args: argparse.Namespace) -> int:
    """Build webdataset shards from the local lazer library."""
    paths = Paths.from_env()
    destination = args.output or (paths.data_root / "corpus" / "compressed")
    if not args.library.is_dir():
        print(f"error: no lazer library at {args.library}", file=sys.stderr)
        return EXIT_ERROR

    print(f"scanning {args.library} ...", flush=True)
    beatmaps, audio = collect(args.library, probe_audio, gamemode=args.gamemode)
    print(f"  {len(beatmaps)} beatmaps (mode {args.gamemode}), {len(audio)} audio blobs")

    rater = RosuStarRating()

    def rate(path: Path) -> float:
        try:
            return rater.rate(path)
        except StarRatingError:
            return 0.0

    samples, stats = assemble(beatmaps, audio, rate, gamemode=args.gamemode, limit=args.limit)
    print(f"  {stats.mapsets} mapsets -> {stats.samples} usable ({stats.unmatched} without audio)")
    if not samples:
        print("error: nothing to write", file=sys.stderr)
        return EXIT_ERROR
    if args.dry_run:
        print(f"dry run: would write ~{-(-stats.samples // args.shard_size)} shard(s)")
        return EXIT_OK

    def announce(path: Path, count: int) -> None:
        print(f"  wrote {path.name}: {count} mapsets", flush=True)

    stats = write_corpus(samples, destination, stats, args.shard_size, on_shard=announce)
    manifest = destination.parent / "manifest.json"
    manifest.write_text(stats.to_json(), encoding="utf-8")
    print(f"{stats.shards} shard(s) -> {destination}")
    print(f"manifest: {manifest}")
    if stats.problems:
        for problem in stats.problems[:10]:
            print(f"  PROBLEM {problem}", file=sys.stderr)
        return EXIT_FAILED
    print("every shard verified")
    return EXIT_OK


def run_repair(args: argparse.Namespace) -> int:
    """Strip known model artifacts from a beatmap, returning an exit code."""
    try:
        result = repair_file(args.path, args.output)
    except RepairError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if not result.changed:
        print("no repairable artifact found; file unchanged")
        return EXIT_OK
    destination = args.output or args.path
    print(
        f"removed {result.removed} object(s) stacked at t=0 "
        f"(map really starts at {result.first_real_time}ms) -> {destination}"
    )
    print("re-run `check` to confirm the result now passes.")
    return EXIT_OK
