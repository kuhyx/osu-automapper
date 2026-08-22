# Fine-tuning (Phase 4 — deferred, optional)

**Nothing in the working pipeline needs this.** Generation and gating both run on
the released `OliBomby/Mapperatorinator-v32` checkpoint. Fine-tuning is only
worth doing to chase a *specific mapper's style*, and it is the one part of this
project that costs real GPU hours.

## Corpus — stream it; do not download it

`project-riz/osu-beatmaps` is the dataset the base `v32` config already points
at, in WebDataset format: **74 `compressed/` shards** (64 kbps Opus) plus a
larger `original/` variant. Records carry `json` (beatmap) + `opus` (audio).

**`train_dataset_streaming: true` is the default, so training needs no local
copy at all.** Downloading the full set is ~299 GB and actively harmful here:
it saturated the uplink hard enough to break DNS resolution for everything else
on the machine (`git push` and `huggingface.co` both failed with
`Temporary failure in name resolution` until the download was killed).

Do **not** use `dataset_type: "mmrs"`. That format is produced by the
Mapperator .NET console app and requires an **osu! OAuth client token** — a
credential this project deliberately does not hold.

`HF_HOME` points at `~/osu-automapper_data/hf`; nothing lands in the repo.

## LoRA

Upstream ships `configs/train/lora_v32.yaml`, but it expects a local `mmrs`
dataset. Use `configs/train/lora_kuhy.yaml` instead (written by this project),
which keeps the same LoRA hyperparameters and streams the web dataset:

```bash
cd ~/Mapperatorinator
HF_HOME=~/osu-automapper_data/hf .venv/bin/python osuT5/train.py \
  --config-name lora_kuhy
```

Confirmed on launch: 11,206,656 trainable of 227,511,552 total parameters
(4.9%), base weights frozen.

### Sizing, measured rather than guessed

A first run at `batch_size: 8, grad_acc: 8` used only **4.9 GB of 24 GB** and
ran at **~1.1 s/step** once past warmup, finishing 400 steps in about seven
minutes — far too small to be worth the setup. The shipped config is therefore
`batch_size: 24, total_steps: 3000`, which sits at ~8.5 GB and keeps the GPU
pinned at 100%.

The first step of a run is slow (~13-15 s) while the streaming dataloader fills;
do not read that as the steady-state rate. Nor is the batch-8 figure a guide:
**batch 24 runs at ~3.0 s/step**, not 1.1, so 3000 steps is ~150 minutes. Time
the run by sampling two step numbers a minute apart rather than trusting
`train/seconds_per_step` from the first log line.

Checkpoints every 250 steps (~12 min) mean the run can be stopped at any point
and still yield a usable adapter.

### Two overrides that config needs, and why

- **`attn_implementation: 'sdpa'`** — `v32.yaml` asks for `flash_attention_2`,
  but `flash-attn` is absent from `requirements.txt` (Docker-only), so training
  dies with `ImportError` at model construction. Inference is unaffected because
  it defaults to `auto` and falls back on its own.
- **`checkpoint.every_steps: 100`** — the default is 5000, which would never
  fire in a shorter run and would leave nothing on disk.

A style LoRA needs **≥10 style-consistent maps** to be worth training; fewer and
it memorises rather than generalises. The result is consumed at inference
through `lora_path=`:

```bash
.venv/bin/python inference.py \
  audio_path=<song.mp3> output_path=<out> \
  gamemode=0 difficulty=5.5 year=2023 \
  lora_path=<path/to/lora>
```

## Scheduling

Any real training run is **off-hours only** and never launched while the machine
is in use — a multi-hour job that saturates the GPU makes the desktop unusable.

## Before spending the hours

Run the blind test on stock-checkpoint output first (see
[`runbook.md`](runbook.md)). If a human cannot reliably separate generated maps
from human ones already, a style LoRA is solving a problem you do not have.
