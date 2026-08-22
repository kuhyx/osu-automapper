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

## First measured finding: the song dominates

Partway through the first full sweep, with two songs done:

| song | BPM | cells | passed | `objects_snapped` failures |
|---|---:|---:|---:|---:|
| `celldweller_weaponized` | 100 | 30 | 23 | 1 |
| `dschinghis_khan_moskau` | 131 | 22 | 0 | 22 |

Every Moskau cell failed, at every difficulty, in both gamemodes. The cause is
the song, not the difficulty: Moskau is a 1970s recording with **43 uninherited
timing points** and drifting BPM, and the model places objects 5-10 ms off the
grid just after a timing-point change (measured: 9.00 ms, 5.00 ms, 10.00 ms
against the correct active red line, versus a 2 ms tolerance and the ~1.4 ms p99
error seen across 300 ranked maps).

That is a real model limitation, confirmed by re-deriving the snap error by hand
against the active timing point rather than trusting the gate. **Do not respond
by loosening `SNAP_TOLERANCE_MS`** -- see the divisor-family note in
`docs/gates.md`.

The methodological point is the important one: a sweep of one song would have
concluded "the model is reliable" or "the model is broken" purely on which song
was picked. Spend the budget on songs, not seeds.

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
