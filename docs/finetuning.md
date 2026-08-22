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

### Three overrides that config needs, and why

- **`attn_implementation: 'sdpa'`** — `v32.yaml` asks for `flash_attention_2`,
  but `flash-attn` is absent from `requirements.txt` (Docker-only), so training
  dies with `ImportError` at model construction. Inference is unaffected because
  it defaults to `auto` and falls back on its own.
- **`checkpoint.every_steps: 250`** — the default is 5000, which would never
  fire in a shorter run and would leave nothing on disk.
- **`logging.log_with: 'wandb'` with `mode: offline`** — counter-intuitive, but
  required. `maybe_save_checkpoint()` calls `accelerator.get_tracker("wandb")`
  unconditionally, and `accelerate` *raises* when trackers exist but none carry
  that name. Setting `tensorboard` therefore crashes the run at the first
  checkpoint. Offline wandb keeps upstream's code path valid, needs no account
  and touches no network. Export `WANDB_MODE=offline WANDB_SILENT=true` too.

  The crash lands *after* the adapter is written, so a run killed this way still
  leaves a usable LoRA on disk — which is how the first step-250 adapter
  survived to be tested. **Fix confirmed:** with offline wandb the run saved
  checkpoint_0 at step 250 and continued past it with zero tracker errors.

A style LoRA needs **≥10 style-consistent maps** to be worth training; fewer and
it memorises rather than generalises. Each checkpoint writes a PEFT adapter to `checkpoints/checkpoint_N/lora/`
(~95 MB, r=64, alpha=128, targeting `Wq`/`Wkv`/`Wqkv`/`Wo`). That directory is
what inference consumes:

```bash
./run.sh generate <song.mp3> <out> --difficulty 5.0 --lora-path <lora-dir>
```

Verified at step 250 with seed (555) and difficulty (5.0) held constant:

| | base | LoRA |
|---|---|---|
| objects | 973 | 928 |
| circles | 679 | 616 |
| sliders | 293 | 312 |
| spinners | 1 | 0 |
| shared timestamps | — | 80% |

The LoRA map still passed all 14 checks at 4.68 stars. Object *count* alone is
weak evidence; the shifted slider-to-circle ratio is what shows the adapter is
changing style rather than just reshuffling. Fixed-seed comparison like this is
the cheapest way to prove an adapter is loaded rather than silently ignored.

## Evaluating the checkpoints

A run leaves a pile of adapters nobody has looked at. `scripts/eval_checkpoints.sh`
turns them into numbers: it generates one map per checkpoint plus a no-LoRA
baseline, all at the same seed and difficulty, gates each, and writes
`~/osu-automapper_data/lora/results.tsv`.

```bash
cd ~/osu-automapper && ./scripts/eval_checkpoints.sh
SEED=99 DIFFICULTY=4.0 ./scripts/eval_checkpoints.sh   # or vary the probe
```

It reports circles and sliders separately because **object count alone
understates the effect**. First run, seed 555, difficulty 5.0:

```
label         objects  circles  sliders  stars  verdict
base          973      679      293      4.91   pass
checkpoint_0  922      612      310      4.71   pass
```

Both pass the gate; the adapter is trading circles for sliders (30.1% → 33.6%
sliders) rather than simply producing fewer objects.

Safe to run while training continues: both fit in 24 GB. Expect inference to
take roughly twice as long (~90 s vs ~40 s) while sharing the GPU.

## Scheduling

Any real training run is **off-hours only** and never launched while the machine
is in use — a multi-hour job that saturates the GPU makes the desktop unusable.

## Before spending the hours

Run the blind test on stock-checkpoint output first (see
[`runbook.md`](runbook.md)). If a human cannot reliably separate generated maps
from human ones already, a style LoRA is solving a problem you do not have.
