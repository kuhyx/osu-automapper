# AI osu! mappers: the landscape

The question that started this work was *"does an AI osu! automapper already
exist?"* It does, with free pretrained weights, which changes the job entirely:
nothing needs training from scratch. The valuable work left is the **harness** —
reproducible generation, deterministic quality gates, and an honest test of
whether the output is any good.

## Mapperatorinator — the one to use

<https://github.com/OliBomby/Mapperatorinator>

A Whisper-style transformer (~219M params) mapping mel-spectrograms to
hit-object tokens with custom RoPE, plus diffusion-based coordinate refinement.
It is the merge of two earlier projects:

- [osuT5](https://github.com/gyataro/osuT5) — seq2seq audio → hit objects
- [osu-diffusion](https://github.com/OliBomby/osu-diffusion) — coordinate diffusion

Why it wins: all four gamemodes, MIT-licensed checkpoints on Hugging Face
(`OliBomby/Mapperatorinator-v32`), active maintenance, and a conditioning
interface (difficulty, year, mapper style, descriptors) that makes output
steerable rather than a lottery.

## Alternatives

| Project | Verdict |
|---|---|
| [osumapper](https://github.com/kotritrona/osumapper) | the famous one, but 2021/TF1-era; grid-like output |
| [osu-dreamer](https://github.com/jaswon/osu-dreamer) | diffusion, std-only, no comparable released checkpoint |
| [BeatLearning](https://github.com/sedthh/BeatLearning) | research-toy scale |
| [OSU-automapping](https://github.com/FrostHan/OSU-automapping) | academic one-off |

## Corpus: no scraper needed

The osu! API v2 serves metadata, not bulk beatmap files — but no scraping is
required either way. Ranked corpora are already packaged on Hugging Face
(`Tiger14n/osumaps19866`, `project-riz/osu-beatmaps`), and `hf download` is
resumable without OAuth.

For a *local* test song, you do not even need that: lazer's own library at
`~/.local/share/osu/files` already holds real maps and audio (see
[`runbook.md`](runbook.md) for how to pair them without a Realm reader).

## Validator: why this repo writes its own

MapsetVerifier (AiMod's successor) is the community standard, but it is an
Electron GUI with no CLI and no NuGet packages — it cannot produce an exit code,
which is the entire point of a gate. So the gate is self-written Python over
`slider`-style parsing, and MapsetVerifier remains an optional manual
cross-check.
