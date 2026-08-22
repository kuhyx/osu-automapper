# Runbook

## Install

```bash
cd ~/osu-automapper && ./install.sh
```

Idempotent. Creates two virtualenvs, clones upstream, prepares
`~/osu-automapper_data/`, and prints an environment probe.

### Why two virtualenvs

| venv | Python | Holds |
|---|---|---|
| `~/Mapperatorinator/.venv` | 3.10 | torch, torchaudio, transformers, the checkpoint |
| `~/osu-automapper/.venv` | 3.12 | slider, rosu-pp-py, pytest, ruff, mypy |

This package **never imports torch**. Upstream is driven by subprocess, which is
what keeps the test suite at 100% branch coverage and CI free of CUDA.

### Two install traps, both handled in `install.sh`

1. **`torchaudio` is missing from upstream's `requirements.txt`** even though
   `osuT5/osuT5/model/spectrogram.py` imports it — it only ships in their
   Dockerfile. Inference dies with `ModuleNotFoundError` without it.
2. **torch must be installed first, from the CUDA index.** `requirements.txt`
   pulls `torchcodec`, which will happily drag in a CPU-only torch. The probe at
   the end of `install.sh` re-checks `torch.cuda.is_available()` *after* the
   requirements install for exactly this reason.
3. **`torchcodec==0.10.0` (pinned upstream) is ABI-broken against torch 2.13**
   and fails with `undefined symbol: _ZN3c1013MessageLoggerC1EPKciib`. It only
   bites the *dataset* path (training), not inference, which uses `torchaudio`.
   Fix: `torchcodec==0.16.0` from the same cu130 index — it also ships a
   `core9` build for Arch's FFmpeg 9, where 0.10.0 topped out at FFmpeg 8.
   Installing `ffmpeg4.4` is **not** needed and does not help.

   Diagnosing this: a bare `ctypes.CDLL()` on `libtorchcodec_core*.so` reports
   a misleading `libc10_cuda.so: cannot open shared object file`, because only
   `import torch` puts libtorch on the loader path. Always probe with
   `import torch` first, then `import torchcodec`.

## Generate

Through this repo (records every input, so a run is repeatable):

```bash
./run.sh generate ~/osu-automapper_data/songs/<song>.mp3 \
  ~/osu-automapper_data/out/std \
  --difficulty 5.5 --year 2023 --seed 1337 \
  --title "<Title>" --artist "<Artist>" --preview-time 1598

# mania
./run.sh generate <song.mp3> <out> --gamemode 3 --difficulty 4.5 --keycount 4
```

Or drive upstream directly. Its Hydra config is `configs/inference/v32.yaml`
(there is no `configs/inference.yaml`).

```bash
cd ~/Mapperatorinator
HF_HOME=~/osu-automapper_data/hf .venv/bin/python inference.py \
  audio_path=~/osu-automapper_data/songs/<song>.mp3 \
  output_path=~/osu-automapper_data/out/std \
  gamemode=0 difficulty=5.5 year=2023 export_osz=true seed=1337 \
  title="<Title>" artist="<Artist>" preview_time=1598
```

- `difficulty` and `year` are effectively mandatory — omitting them makes style
  and difficulty drift between runs.
- `title`, `artist` and `preview_time` are **not optional if you want a green
  gate**: the model emits `Unknown Title` / `Unknown Artist` / `PreviewTime: -1`
  otherwise, and the gate correctly rejects all three.
- `export_osz=true` writes a `.osz` you can import into lazer directly.
- mania needs `keycount=`; `gamemode=3 difficulty=4.5 keycount=4`.
- `seed=` makes a run reproducible. Upstream also records the whole config in the
  map's `Tags:` field, so any generated map can be traced back to its inputs.

Measured on an RTX 3090: ~4 s timing + ~35 s map for a 3½-minute song.

## Check

```bash
cd ~/osu-automapper
./run.sh check ~/osu-automapper_data/out/std/extracted/*.osu --target-difficulty 5.5
echo "exit=$?"
./run.sh check <map.osu> --json          # machine-readable
```

## Test songs from the local lazer library

lazer stores beatmaps content-addressed under `~/.local/share/osu/files/<a>/<ab>/<hash>`
with no extensions. You do not need a Realm reader to get at them: sniff the
first bytes to classify a blob, then join maps to audio on ID3 tags plus
duration. Full method, measured yields, and the approaches that **do not** work
are in `docs/lazer-library.md` — read that before writing any extraction code.

## Sweep

```bash
./run.sh sweep --dry-run          # see the grid without spending GPU time
./run.sh sweep                    # 3-7 stars, std + mania, 3 seeds, every song
```

Resumable: each cell writes its own JSON, and existing cells are skipped. See
`docs/sweep.md` for the grid, the two-gate design, and the songs used.

## Blind test (Phase 3, never CI)

`build_blindtest` shuffles real and generated maps behind labels A-F and saves
the key; `score_blindtest` grades guesses afterwards. Judging map quality is a
human act -- it never gates a commit.

```bash
./run.sh blindtest --real <human.osu>... --generated <ai.osu>... \
    --audio <song.mp3> --seed <n>
# play the .osz in lazer WITHOUT reading the key, then:
./run.sh blindtest-score <key>.json A=ai B=human C=ai D=human E=ai F=human
```

**Every entry must be the same song.** The pack ships one audio file shared by
all difficulties, so mixing songs would give the answer away immediately. Match
the generated maps' target difficulty to the human maps' *measured* star rating,
or difficulty becomes the tell instead of mapping quality.

Anonymisation covers far more than metadata. Four separate leaks each split a
real pack perfectly, and every one was found by diffing rather than by thinking
about it:

| leak | why it gave the answer away | found |
|---|---|---|
| `[Events]` | human maps ship backgrounds/breaks/storyboards, generated ship none | 1st pack |
| kiai (`effects` bit 0) | human maps kiai the chorus; the playfield pulses | 1st pack |
| `[Editor]` + tool `[General]` keys | `Bookmarks:-330001`, `TimelineZoom: 2.20004`, `GridSize: 8`, `SampleSet: All`, `OverlayPosition` -- constant per *tool*, split `{A,B,F}` from `{C,D,E}` | 2nd pack |
| `[Colours]`, `Source`, `Beatmap*ID`, HP/OD/AR/CS | ranked metadata and hand-tuned constants a sampler never emits | 2nd pack |

All four are handled by `_anonymise`. The 2026-08-22 15:39 pack predates the
last two and is **compromised** -- anyone reading the `.osu` files scores 6/6
without playing.

### Where anonymisation stops

Scrub two categories and nothing else: **tool provenance** (editor state,
`BeatmapID`, `Source`, `Tags` -- readable in a text editor, invisible in play)
and **play-visible decoration** (backgrounds, kiai, combo colours). Anything a
mapper *authored* stays exactly as written, even when it is a known tell:

- **Timing points are not scrubbed.** Generated entries had 3 uninherited lines
  and <=15 total against the humans' 1 and >=28 -- a perfect separator. But
  barlines are not rendered in std gameplay, so it cannot help someone actually
  playing, and rewriting the beat grid would unsnap the objects hanging off it.
- **`SliderMultiplier`/`SliderTickRate` are not normalised.** Slider duration is
  `pathLength / (SliderMultiplier * 100 * SV) * beatLength`, so forcing a human
  map's 1.7 to 1.4 stretches every slider ~21% and makes it overrun the objects
  after it. That corrupts the human entries *only*, biasing the test the wrong
  way: a broken-feeling human map reads as "AI".

A leak that merely rewards cheating is better than a "fix" that corrupts the
maps under test. `PreviewTime` is normalised to a real timestamp rather than
`-1`, because the gate rejects an unset preview.

When adding a new source of maps, diff a human entry against a generated one
**before** playing -- the gate does not catch leaks, only broken maps. Compare
every `key:value` line above `[HitObjects]`, then gate all six entries to prove
the normalisation did not break them.
