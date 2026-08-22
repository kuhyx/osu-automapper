"""Execute a sweep grid, one resumable cell at a time.

Each cell writes its own result file the moment it finishes. A sweep that dies
at cell 130 of 150 therefore loses one cell, not a session: rerunning skips
everything already on disk.
"""

from __future__ import annotations

import time
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path

from osu_automapper.checks import run_checks
from osu_automapper.generate import GenerationError, GenerationRequest, generate
from osu_automapper.parse import Beatmap, BeatmapParseError, parse_beatmap
from osu_automapper.repair import RepairError, repair_file
from osu_automapper.report import Report
from osu_automapper.stars import RosuStarRating, StarRatingError, StarRatingProvider
from osu_automapper.sweep.model import SweepCell, SweepGrid, SweepOutcome, iter_cells

Generator = Callable[[GenerationRequest], Path]


class SweepError(Exception):
    """Raised when the sweep cannot proceed at all (bad paths, unwritable root)."""


def _extract_osu(output_dir: Path) -> Path:
    """Find the generated ``.osu``, unpacking the ``.osz`` when needed.

    Raises:
        SweepError: when generation produced neither a ``.osu`` nor a ``.osz``.

    """
    loose = sorted(output_dir.rglob("*.osu"))
    if loose:
        return loose[0]

    archives = sorted(output_dir.glob("*.osz"))
    if not archives:
        raise SweepError(f"no .osu or .osz under {output_dir}")

    extracted = output_dir / "extracted"
    extracted.mkdir(exist_ok=True)
    with zipfile.ZipFile(archives[0]) as archive:
        for name in archive.namelist():
            if name.endswith(".osu"):
                archive.extract(name, extracted)
    found = sorted(extracted.rglob("*.osu"))
    if not found:
        raise SweepError(f"no .osu inside {archives[0]}")
    return found[0]


def _gate(path: Path, target: float, provider: StarRatingProvider) -> tuple[Report, float | None]:
    """Run the check suite and rate the map, tolerating a rating failure."""
    beatmap: Beatmap = parse_beatmap(path)
    report = run_checks(beatmap)
    try:
        stars: float | None = provider.rate(path)
    except StarRatingError:
        stars = None
    return report, stars


def _object_count(beatmap_path: Path) -> int:
    """Count hit objects, so density is comparable across cells."""
    text = beatmap_path.read_text(encoding="utf-8-sig", errors="replace")
    part = text.split("[HitObjects]")
    if len(part) < 2:
        return 0
    return len([line for line in part[1].strip().splitlines() if line.strip()])


def _blank_outcome(cell: SweepCell) -> SweepOutcome:
    """Build an outcome carrying only the cell's identity."""
    return SweepOutcome(
        label=cell.label,
        song=cell.song.name,
        difficulty=cell.difficulty,
        mode=int(cell.mode),
        seed=cell.seed,
        adapter=cell.lora_path.name if cell.lora_path is not None else "base",
    )


def run_cell(
    cell: SweepCell,
    out_root: Path,
    generator: Generator,
    provider: StarRatingProvider,
) -> SweepOutcome:
    """Generate one cell, gate it raw, repair it, and gate it again."""
    outcome = _blank_outcome(cell)
    started = time.monotonic()
    output_dir = out_root / cell.label

    request = GenerationRequest(
        audio_path=cell.song,
        output_path=output_dir,
        mode=cell.mode,
        difficulty=cell.difficulty,
        seed=cell.seed,
        keycount=cell.keycount,
        title=cell.song.stem,
        artist="sweep",
        preview_time=0,
        lora_path=cell.lora_path,
    )
    try:
        generator(request)
        osu_path = _extract_osu(output_dir)
    except (GenerationError, SweepError) as exc:
        outcome.error = str(exc)[:500]
        outcome.duration_seconds = round(time.monotonic() - started, 1)
        return outcome

    outcome.generated = True
    try:
        raw_report, raw_stars = _gate(osu_path, cell.difficulty, provider)
    except BeatmapParseError as exc:
        outcome.error = f"unparseable output: {exc}"[:500]
        outcome.duration_seconds = round(time.monotonic() - started, 1)
        return outcome

    outcome.raw_passed = raw_report.technically_rankable
    outcome.raw_failures = [r.name for r in raw_report.failures]
    outcome.raw_stars = raw_stars

    # Repair to a COPY: destroying the raw artifact would make the raw column
    # unreproducible, and the two columns are the point of the sweep.
    repaired_path = osu_path.with_name(f"{osu_path.stem}.repaired.osu")
    try:
        result = repair_file(osu_path, repaired_path)
        outcome.objects_removed = result.removed
        repaired_report, repaired_stars = _gate(repaired_path, cell.difficulty, provider)
    except (RepairError, BeatmapParseError) as exc:
        outcome.error = f"repair/gate failed: {exc}"[:500]
        outcome.duration_seconds = round(time.monotonic() - started, 1)
        return outcome

    outcome.repaired_passed = repaired_report.technically_rankable
    outcome.repaired_failures = [r.name for r in repaired_report.failures]
    outcome.repaired_stars = repaired_stars
    outcome.objects = _object_count(repaired_path)
    outcome.duration_seconds = round(time.monotonic() - started, 1)
    return outcome


def run_sweep(
    grid: SweepGrid,
    results_dir: Path,
    out_root: Path,
    generator: Generator | None = None,
    provider: StarRatingProvider | None = None,
    on_result: Callable[[SweepOutcome], None] | None = None,
) -> list[SweepOutcome]:
    """Run every cell, resuming over any result already on disk."""
    results_dir.mkdir(parents=True, exist_ok=True)
    out_root.mkdir(parents=True, exist_ok=True)
    generate_one: Generator = generator if generator is not None else generate
    rater = provider if provider is not None else RosuStarRating()

    cells: Iterable[SweepCell] = iter_cells(grid)
    outcomes: list[SweepOutcome] = []
    for cell in cells:
        destination = results_dir / f"{cell.label}.json"
        if destination.exists():
            outcomes.append(SweepOutcome.from_json(destination.read_text(encoding="utf-8")))
            continue
        outcome = run_cell(cell, out_root, generate_one, rater)
        destination.write_text(outcome.to_json(), encoding="utf-8")
        outcomes.append(outcome)
        if on_result is not None:
            on_result(outcome)
    return outcomes
