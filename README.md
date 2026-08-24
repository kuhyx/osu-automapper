# osu-automapper

Reproducible generation and **deterministic quality gates** for AI-generated
osu! beatmaps, wrapped around
[Mapperatorinator](https://github.com/OliBomby/Mapperatorinator).

The interesting part is not that a model can write a beatmap — it can, and
someone else trained it. The interesting part is making *"is this map any good?"*
an exit code instead of an opinion.

```bash
./install.sh
./run.sh check <map.osu> --target-difficulty 5.5 ; echo "exit=$?"
```

## What it does

- **Generates** osu!standard and osu!mania maps from any audio file, with the
  generation config recorded so a run can be repeated exactly. Optionally
  through a fine-tuned LoRA adapter (`--lora-path`).
- **Gates** the result: 9 mode-independent checks plus a per-gamemode suite,
  a pinned star-rating tolerance, and a `0` / `1` / `2` exit-code contract.
- **Repairs** a known model artifact (a cluster of objects stacked at `t=0`)
  as a separate opt-in command, so gating never silently edits what it judges.
- **Blind-tests** generated maps against human ones behind anonymous labels,
  because quality is a human judgement and shouldn't pretend to be CI.

No LLM adjudicates anything. Every check is a pure function over parsed `.osu`
data, and the suite holds 100% branch coverage with no lint suppressions.

## ⚠️ These maps cannot be ranked, and are not uploaded

The osu! Ranking Criteria prohibits generative tooling in beatmap creation
outright. This repository therefore:

- has **no upload or submission code path**, and no osu! API credentials
- names its passing state **`technically rankable`** — meaning "well-formed",
  never "eligible"

See [`docs/DOCS-ranking-criteria.md`](docs/DOCS-ranking-criteria.md). This is a local
tool for a local question.

## Docs

| | |
|---|---|
| [`DOCS-runbook.md`](docs/DOCS-runbook.md) | install, generate, check — and the traps |
| [`DOCS-gates.md`](docs/DOCS-gates.md) | every check, and the measurements behind the thresholds |
| [`DOCS-landscape.md`](docs/DOCS-landscape.md) | what already exists, and why Mapperatorinator |
| [`DOCS-finetuning.md`](docs/DOCS-finetuning.md) | LoRA training, and the four traps that block it |
| [`DOCS-ranking-criteria.md`](docs/DOCS-ranking-criteria.md) | the AI policy, sourced |

## Architecture

Two virtualenvs. Upstream (torch, CUDA, python 3.10) is driven **by subprocess**;
this package never imports torch. That seam is what keeps CI fast, GPU-free, and
fully covered.
