# Fine-tuning (Phase 4 — deferred, optional)

**Nothing in the working pipeline needs this.** Generation and gating both run on
the released `OliBomby/Mapperatorinator-v32` checkpoint. Fine-tuning is only
worth doing to chase a *specific mapper's style*, and it is the one part of this
project that costs real GPU hours.

## Corpus — do not write a fetcher

Ranked corpora are already packaged on Hugging Face:

- `Tiger14n/osumaps19866` — ~19,866 `.osz`, organised by year/month
- `project-riz/osu-beatmaps`

`hf download` is resumable and needs no OAuth. The osu! API v2 serves metadata
only and will not bulk-serve beatmap files, so scraping is both unnecessary and
the wrong tool.

Point `HF_HOME` at `~/osu-automapper_data/hf` and let the corpus land in
`~/osu-automapper_data/corpus` — never inside the repository.

## LoRA

Upstream ships `configs/train/lora_v32.yaml`. A LoRA needs **≥10
style-consistent maps** to be worth training; fewer and it memorises rather than
generalises. The result is consumed at inference through `lora_path=`:

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
