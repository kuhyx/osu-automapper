"""Aggregation of sweep outcomes into the reported tables."""

from __future__ import annotations

from osu_automapper.sweep.model import SweepOutcome
from osu_automapper.sweep.report import aggregate, to_markdown


def _outcome(
    *,
    label: str = "c",
    song: str = "s.mp3",
    difficulty: float = 5.0,
    mode: int = 0,
    seed: int = 1,
    adapter: str = "base",
    generated: bool = True,
    error: str = "",
    raw_passed: bool = True,
    repaired_passed: bool = True,
    repaired_failures: list[str] | None = None,
    repaired_stars: float | None = 5.0,
    objects_removed: int = 0,
    objects: int = 400,
) -> SweepOutcome:
    """Build an outcome, defaulting to a clean passing cell."""
    return SweepOutcome(
        label=label,
        song=song,
        difficulty=difficulty,
        mode=mode,
        seed=seed,
        adapter=adapter,
        generated=generated,
        error=error,
        raw_passed=raw_passed,
        repaired_passed=repaired_passed,
        repaired_failures=repaired_failures or [],
        repaired_stars=repaired_stars,
        objects_removed=objects_removed,
        objects=objects,
    )


def test_empty_results_do_not_pretend_to_be_a_report() -> None:
    assert to_markdown([]) == "No sweep results.\n"


def test_rates_are_shares_of_the_bucket() -> None:
    outcomes = [
        _outcome(raw_passed=True, repaired_passed=True),
        _outcome(raw_passed=False, repaired_passed=True, objects_removed=3),
        _outcome(raw_passed=False, repaired_passed=False),
        _outcome(raw_passed=False, repaired_passed=False, generated=False),
    ]
    bucket = aggregate(outcomes, lambda o: "all")[0]
    assert bucket.total == 4
    assert bucket.generated == 3
    assert bucket.raw_pass_rate == "25%"
    assert bucket.repaired_pass_rate == "50%"
    assert bucket.defect_rate == "25%"


def test_star_error_is_averaged_only_over_rated_cells() -> None:
    outcomes = [
        _outcome(difficulty=5.0, repaired_stars=5.5),
        _outcome(difficulty=5.0, repaired_stars=4.5),
        _outcome(difficulty=5.0, repaired_stars=None),
    ]
    bucket = aggregate(outcomes, lambda o: "all")[0]
    assert bucket.mean_star_error == 0.0


def test_buckets_with_nothing_measurable_report_na() -> None:
    bucket = aggregate([_outcome(repaired_stars=None, objects=0)], lambda o: "all")[0]
    assert bucket.mean_star_error is None
    assert bucket.mean_objects is None


def test_grouping_splits_on_the_key() -> None:
    outcomes = [_outcome(mode=0), _outcome(mode=3), _outcome(mode=3)]
    buckets = {b.key: b for b in aggregate(outcomes, lambda o: str(o.mode))}
    assert buckets["0"].total == 1
    assert buckets["3"].total == 2


def test_markdown_covers_every_axis_and_names_failures() -> None:
    outcomes = [
        _outcome(mode=0, difficulty=3.0, song="a.mp3", adapter="base"),
        _outcome(
            mode=3,
            difficulty=7.0,
            song="b.mp3",
            adapter="checkpoint_11",
            repaired_passed=False,
            repaired_failures=["object_gaps"],
        ),
    ]
    text = to_markdown(outcomes)
    assert "### By difficulty" in text
    assert "### By gamemode" in text
    assert "### By song" in text
    assert "### By adapter" in text
    assert "std" in text and "mania" in text
    assert "`object_gaps`: 1 cell(s)" in text
    assert "docs/ranking-criteria.md" in text


def test_failed_generations_are_listed_rather_than_dropped() -> None:
    text = to_markdown([_outcome(generated=False, error="cuda oom", label="cell_x")])
    assert "### Cells that failed to generate" in text
    assert "cell_x" in text
    assert "cuda oom" in text


def test_a_failed_generation_without_a_message_still_appears() -> None:
    text = to_markdown([_outcome(generated=False, error="", label="cell_y")])
    assert "cell_y" in text
    assert "unknown error" in text


def test_an_unknown_mode_falls_back_to_its_number() -> None:
    text = to_markdown([_outcome(mode=9)])
    assert "| 9 |" in text
