# The reliability sweep

`osu-automapper sweep` answers "where is the model dependable, and where does it
break?" with a table instead of anecdotes. It walks a grid, generates every cell,
and gates each one twice.

## Why two gates per cell

The model has a known defect: at some difficulties it emits a cluster of hit
objects stacked at `t=0` (see `docs/finetuning.md`). `repair` strips it. If the
sweep only gated repaired output, the defect rate would read as zero and the
sweep would measure nothing.

So every cell records both:

| column | meaning |
|---|---|
| `raw pass` | the model's untouched output cleared the gate |
| `after repair` | it cleared the gate once `repair` ran |
| `t=0 defect` | `repair` actually removed a stacked-at-zero cluster |

The gap between the first two columns *is* the defect's practical cost. The very
first cell measured this way failed raw and passed repaired — a sweep reporting
one number would have hidden that.

`repair` writes to a copy (`<name>.repaired.osu`), so the raw artifact stays on
disk and can be re-gated later.

## The grid

```
song x difficulty x gamemode x seed x adapter
```

`--lora-paths` adds adapters; the base model is always swept too, so every
adapter has a baseline to be compared against. Mania cells get `--keycount`
(default 4); standard cells never do.

```bash
# Defaults: 3-7 stars, std + mania, three seeds, every song in the data root.
./run.sh sweep

# Inspect the grid without spending GPU time on it.
./run.sh sweep --dry-run

# One song, one axis, plus two adapters.
./run.sh sweep --songs ~/osu-automapper_data/songs/x.mp3 \
    --difficulties 4 5 6 --gamemodes 0 --seeds 1 2 3 \
    --lora-paths ~/Mapperatorinator/logs/*/checkpoints/checkpoint_11/lora
```

## Resumption

Each cell writes `~/osu-automapper_data/sweep/<label>.json` the moment it
finishes, and a cell whose file already exists is skipped. A sweep that dies at
cell 130 of 180 therefore loses one cell, not an afternoon — just run it again.

To force a re-run, delete the JSON files you want recomputed. Inference is
deterministic, so re-running a cell at the same seed reproduces it exactly;
any difference is real signal, not variance.

## Song choice matters more than seed count

Inference is deterministic, so seeds are the only within-song variation. Ten
seeds of one song is still one song: a low-difficulty failure on a 240 BPM track
is confounded with the track. Prefer spending the budget on **songs across a BPM
range** over more seeds on one.

The songs used here were pulled from the local lazer library, which is also
where the human maps for the blind test come from. See `docs/lazer-library.md`.

## Results: the full 180-cell sweep

6 songs x 5 difficulties x 2 gamemodes x 3 seeds. **All 180 cells generated**;
raw pass 41%, after repair 47%, `t=0` defect fired in 12%. Every cell is the
**base model** -- no adapter was swept, so the mania rows below are *base*
mania and are not evidence about a LoRA either way (a `gamemode=0` adapter is
silently ignored in mania; see `docs/DOCS-finetuning.md`).

### By difficulty

| target | n | raw pass | after repair | t=0 defect | mean star error | mean objects |
|---|---:|---:|---:|---:|---:|---:|
| 3* | 36 | 56% | 61% | 8% | +0.31 | 1010 |
| 4* | 36 | 42% | 47% | 11% | -0.05 | 1220 |
| 5* | 36 | 28% | 42% | 17% | -0.49 | 1332 |
| 6* | 36 | 42% | 47% | 11% | -0.74 | 1536 |
| 7* | 36 | 36% | 39% | 11% | -1.25 | 1585 |

### By gamemode

| mode | n | raw pass | after repair | t=0 defect | mean star error | mean objects |
|---|---:|---:|---:|---:|---:|---:|
| std | 90 | 51% | 64% | 17% | -0.28 | 635 |
| mania | 90 | 30% | 30% | 7% | -0.61 | 2037 |

### By song, split by mode

Uninherited timing points are counted per generated map (they are the model's
own timing inference, so they vary cell to cell); median and range across that
song's 30 cells. Pass counts are after repair.

| song | BPM | uninherited TPs | std pass | mania pass | snap-fail cells |
|---|---:|---:|---:|---:|---:|
| `celldweller_weaponized` | 100 | 1 (1-1) | 13/15 | 10/15 | 1 |
| `dschinghis_khan_moskau` | 131 | 46 (35-77) | **0/15** | **0/15** | 30 |
| `night_of_knights` | 153 | 3 (2-4) | 12/15 | 14/15 | 2 |
| `pegboard_nerds_emoji` | 163 | 8 (4-16) | 12/15 | 2/15 | 16 |
| `pup_free_at_last` | 179 | 10 (5-14) | 6/15 | 0/15 | 24 |
| `toby_fox_megalovania` | 240 | 3 (2-7) | **15/15** | 1/15 | 14 |

`objects_snapped` is the sweep's dominant failure by an order of magnitude: it
accounts for 87 of the 103 post-repair check failures, against
`hold_notes_ordered` 8, `no_column_collisions` 4, `positions_in_playfield` 3
and `object_gaps` 1.

## What the data says

### In standard, it is timing-point density -- not tempo

The old two-song headline ("the song dominates") was right about the effect and
wrong about the cause. In std the pass rate falls monotonically with the number
of uninherited timing points and has no relationship to BPM at all:
1 TP -> 13/15, 3 TPs -> 12-15/15, 8 TPs -> 12/15, 10 TPs -> 6/15, 46 TPs -> 0/15.

`toby_fox_megalovania` was run as the discriminating case and it settles it:
**the fastest song in the sweep, at 240 BPM, passes 15/15 in std.** The slowest
failing song, Moskau, is 131 BPM. Tempo is ruled out.

Moskau remains the one systemic failure. It is a 1970s recording with drifting
BPM, and the model emits **35-77 uninherited timing points** for it (the
earlier "43" was a single cell read as a constant). The model then places
objects 5-10 ms off the grid just after a timing-point change -- measured by
hand at 9.00 ms, 5.00 ms and 10.00 ms against the correct active red line,
versus a 2 ms tolerance and the ~1.4 ms p99 error across 300 ranked maps.
**Do not respond by loosening `SNAP_TOLERANCE_MS`** -- see the divisor-family
note in `docs/DOCS-gates.md`.

### In mania, tempo *does* bite, above roughly 160 BPM

The mode split is the finding the song-level table hides. Above ~160 BPM every
mania group collapses while std holds: Emoji 2/15 vs 12/15, Free At Last 0/15
vs 6/15, MEGALOVANIA 1/15 vs 15/15. Below that, mania is fine (Weaponized
10/15, Night of Knights 14/15).

The clean pair is `night_of_knights` vs `toby_fox_megalovania`: **identical
median timing-point density (3), 153 vs 240 BPM, mania 14/15 vs 1/15.** Timing
points held constant, tempo alone flips the result -- the mirror image of the
std comparison above.

### It is not just "more notes, more chances"

Mania averages 2037 objects a cell against std's 635, so the obvious confound is
exposure. It does not survive: `night_of_knights` mania is the **densest** group
in the whole sweep at 2826 objects a cell and has **zero** snap failures, while
`toby_fox_megalovania` mania has fewer objects (2037) and fails 14/15. Object
count does not order the failures; BPM does.

### `repair` recovers std cells and never a mania one

Std goes 51% raw -> 64% repaired; mania goes 30% -> 30%, exactly. The
stacked-at-zero artifact that `repair` exists to strip is a std-side defect
(17% of std cells vs 7% of mania), and in mania it never happened to be the
thing standing between a cell and the gate.

### Star error drifts negative with difficulty

Orthogonal to the song story, and monotone across all five rows: +0.31 at 3*,
-0.05 at 4*, -0.49 at 5*, -0.74 at 6*, -1.25 at 7*. The model overshoots easy
targets slightly and **undershoots hard ones badly** -- ask for 7* and you get
about 5.75*. Object counts do rise with the target (1010 -> 1585), so it is
producing more, just not proportionally harder, maps.

### The gate is binary; the failures are not

A failing cell is one bad object or a hundred, and the table cannot tell them
apart. Counting the actual unsnapped objects separates them:

| group | failing cells | unsnapped objects | per cell |
|---|---:|---:|---:|
| Moskau mania | 15 | 149 | 9 |
| Free At Last mania | 15 | 176 | 11 |
| Moskau std | 15 | 52 | 3 |
| Emoji mania | 13 | 33 | 2 |
| MEGALOVANIA mania | 14 | 24 | ~2 |
| everything else (std) | 15 | 16 | 1 |

Most non-Moskau failures are **one off-grid note in 500-2500** -- technically
unrankable and correctly caught, but a very different object from Moskau, where
the timing is wrong throughout. Read the pass rates as "cleared a strict gate",
not as "unusable".

### The methodological point stands

A sweep of one song would have concluded "the model is reliable" or "the model
is broken" purely on which song was picked, and a sweep of std alone would have
missed the mania tempo wall entirely. Spend the budget on songs and modes, not
on seeds.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | every cell generated (some may have failed the gate — read the table) |
| `1` | at least one cell failed to generate at all |
| `2` | usage error (no songs) |

A gate failure is a *result*, not a tooling error, so it does not fail the
command. A cell that never produced a map does.

## The songs swept

A manifest is written to `~/osu-automapper_data/sweep/songs.json`; this table is
the committed copy, because a "By song" row is uninterpretable without the BPM.
Five were pulled from the lazer library to span the tempo range (see
`docs/lazer-library.md`); `night_of_knights` predates the sweep.

| file | artist - title | BPM | length |
|---|---|---:|---:|
| `celldweller_weaponized.mp3` | Celldweller - Weaponized | 100 | 63 s |
| `dschinghis_khan_moskau.mp3` | Dschinghis Khan - Moskau | 131 | 272 s |
| `night_of_knights.mp3` | beatMARIO - Night of Knights | 153 | 203 s |
| `pegboard_nerds_emoji.mp3` | Pegboard Nerds - Emoji | 163 | 220 s |
| `pup_free_at_last.mp3` | PUP - Free At Last | 179 | 155 s |
| `toby_fox_megalovania.mp3` | toby fox - MEGALOVANIA | 240 | 156 s |

Every one of them also has human-made difficulties in the local lazer library on
the *same* audio, which is what makes a controlled blind test possible.
