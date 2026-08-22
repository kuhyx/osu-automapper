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

## Generate

Upstream's Hydra config is `configs/inference/v32.yaml` (there is no
`configs/inference.yaml`).

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

## Test song, without a scraper or a Realm reader

lazer stores beatmaps content-addressed under `~/.local/share/osu/files/<a>/<ab>/<hash>`
with no extensions. You do not need to read `client.realm` to get at them:

- `.osu` files are plain text starting with `osu file format v`
- audio is findable with `ffprobe`, and its ID3 artist/title join to a map's
  `[Metadata]` Artist/Title

That join is enough to pair a song with its human-made reference map, which is
what the blind test needs.

## Blind test (Phase 3, never CI)

`build_blindtest` shuffles real and generated maps behind labels A–F and saves
the key; `score_blindtest` grades guesses afterwards. Judging map quality is a
human act — it never gates a commit.
