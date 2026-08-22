# Next session prompt — osu-automapper

Paste everything below the line into a fresh session.

---

Finish one thing in `~/osu-automapper` (public repo `kuhyx/osu-automapper`,
CI **green**, everything pushed). The project is otherwise done and kuhy has
called it a success — do not open new workstreams.

## The only task: publish the sweep table

The reliability sweep was still running when the last session ended. It is
**resumable** — every finished cell is already a JSON file on disk, and a cell
whose file exists is skipped.

```bash
cd ~/osu-automapper
./run.sh sweep            # resumes; skips every cell already done
```

If it is still running from the previous session (`pgrep -f 'osu_automapper sweep'`),
**do not start a second one** — resumption checks file existence, not a lock, so
two runs race and both compute the same cell.

To read partial results at any time without touching the GPU, build the report
from the cells already on disk:

```python
from pathlib import Path
from osu_automapper.sweep.model import SweepOutcome
from osu_automapper.sweep.report import to_markdown
results = Path.home() / "osu-automapper_data" / "sweep"
outcomes = [SweepOutcome.from_json(p.read_text(encoding="utf-8"))
            for p in sorted(results.glob("*_base.json"))]
print(to_markdown(outcomes))
```
(Glob `*_base.json`, not `*.json` — `songs.json` shares that directory and is a
BPM manifest, not a cell.)

Then fold the final table into `docs/sweep.md` and commit. The data root is
gitignored, so a result that is not copied into the repo does not survive.

### How to write it up — three constraints

1. **Replace, do not append.** `docs/sweep.md` currently has a section
   "First measured finding: the song dominates" built from a 2-song partial
   table that says moskau had **22** cells. The final data says **30**.
   Appending leaves the doc asserting both. Rewrite that section.
2. **Drop the "By adapter" table.** Every cell in this sweep is `base` — one row
   is noise, and its presence invites reading the sweep as a LoRA comparison.
   Say in prose that this is base-model-only, so the mania rows are *base* mania,
   never a LoRA result (a `gamemode=0` LoRA is silently ignored in mania — see
   the measured facts in `docs/finetuning.md`).
3. **250-line cap** on the file (`~/utils/file_length` gates it). `docs/sweep.md`
   was 125 lines; fold a summary, not 180 rows.

### The finding the data is converging on

The old headline ("the song dominates the failure rate") is real but
mis-attributed. Measured across the first 4 songs, the driver is
**timing-point density, not tempo**:

| song | BPM | uninherited TPs | pass rate |
|---|---:|---:|---:|
| celldweller_weaponized | 100 | 1 | 76% (23/30) |
| dschinghis_khan_moskau | 131 | 46 | **0% (0/30)** |
| night_of_knights | 153 | 2 | 86% (26/30) |
| pegboard_nerds_emoji | 163 | 4 | 100% so far |

BPM has no monotonic relationship — the two *fastest* songs pass best. All 30
moskau failures include `objects_snapped`, a single uniform failure mode,
consistent with the known mechanism (the model lands 5-10 ms off-grid right
after a timing-point change).

**`toby_fox_megalovania` at 240 BPM is the discriminating case** and had not run
yet. It is the fastest song with few timing points: if it passes, tempo is ruled
out cleanly and the finding is timing-point density. If it fails, the story is
more complicated — say so rather than forcing it.

Count the uninherited timing points of a generated map with:
```bash
sed -n '/^\[TimingPoints\]/,/^\[/p' <map>.osu | awk -F, 'NF>=7 && $7==1' | wc -l
```

**Do not loosen `SNAP_TOLERANCE_MS`** — those are real unsnapped objects,
hand-verified against the correct active red line.

## What was finished last session (do not redo)

- **Corpus uploaded.** Private HF dataset `kuhy/osu-mapsets-lazer`: 9 shards,
  562 mapsets, 1.3 GB, plus `manifest.json`. Privacy verified before *and* after
  the upload; upstream's `list_repo_files` sees all 9 shards. A training config
  can point at it now. See `docs/corpus-options.md`.
- **Blind test played: 5/6.** With n=6, P(>=5 | guessing) = 7/64 = **0.11** —
  suggestive, *not* conclusive. Never write this up as 6/6. The one miss was `A`,
  a human map; kuhy realised it was human while playing `B`, but `A`'s answer was
  already locked in, so there is a known **order effect against the first map**.
  `play_blindtest.sh` now gates on "played all six?" and allows revision before
  scoring. Full write-up in `docs/runbook.md`.
- **Four blind-test leak classes closed** (`[Events]`, kiai, `[Editor]`+tool
  `[General]` keys, `[Colours]`/`Source`/`Beatmap*ID`/difficulty constants).
  `scripts/check_blindtest_leaks.py` re-checks any pack; run it before playing.
  Two known tells are left *deliberately* — timing points and `SliderMultiplier`
  — because scrubbing them corrupts the maps under test. See `docs/runbook.md`.
- **CI fixed.** It had been red since the corpus command landed: those tests
  encode real audio and the runner had no ffmpeg. Now installed; shellcheck also
  widened to `scripts/*.sh`.

## Standing constraints

- **Nothing is ever uploaded to osu!** — `tests/test_no_upload_boundary.py`
  enforces it, and bans the bare word "upload" anywhere under `osu_automapper/`.
  That is why the corpus uploader lives in `scripts/`. The passing state is
  `technically_rankable`, never `rankable`.
- Upstream `~/Mapperatorinator` is a third-party sibling: never vendor, modify
  or PR it. The `hf` CLI and `huggingface_hub` come from its venv.
- **Seed 1 is burned** for the blind test — kuhy has seen its key. Any new pack
  needs `--seed <fresh>`; `rebuild_blindtest.py` warns if the default is used.
- 258 tests, 100% branch coverage, mypy --strict / ruff / pre-commit clean, no
  suppressions. Keep it that way.

## If the sweep is done and written up

That closes the project. Remaining ideas, none of them requested:
a bigger blind test (cheap now — ~400 lazer maps joined to audio, and the 5/6
p=0.11 result is the argument for it), and a mania LoRA (needs mania in
`ckpt_subfolders`; a `gamemode=0` adapter is a silent no-op there).
