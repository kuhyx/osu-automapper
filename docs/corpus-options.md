# Training on a corpus v32 has not seen

`docs/finetuning.md` records why a new corpus is the only way to get a real style
change: LoRA training on `project-riz/osu-beatmaps` plateaus immediately, because
that is what v32 was already trained on.

The obvious candidate was the local lazer library (~2,867 std maps at
`~/.local/share/osu/files`). **That path is blocked**, and this file records why,
so the next session does not spend hours building shards for a loader that
cannot read them.

## Upstream supports exactly three dataset types

`osuT5/osuT5/utils/model_utils.py:541-552` branches on `data.dataset_type` and
raises `NotImplementedError` for anything else:

| type | loader | reads from |
|---|---|---|
| `ors` | `OrsDataset` | a local directory |
| `mmrs` | `MmrsDataset` | local, but built by the Mapperator .NET tool |
| `web` | `WebDataset` | a **Hugging Face dataset repo** |

## Why each is unavailable for "point it at my lazer library"

**`mmrs`** needs an osu! OAuth token to build, which this project deliberately
does not hold (`docs/ranking-criteria.md` explains the no-upload boundary).

**`web`** is not a local-filesystem loader, despite `train_dataset_path` looking
like a path. `WebDataset.__init__` (`web_dataset.py:65-76`) calls
`list_repo_files(self.repo_id, repo_type="dataset")` — a Hugging Face Hub API —
and then `load_dataset(self.repo_id, ...)`. The value must be a `namespace/name`
repo id. Using it with a local corpus would mean uploading the whole corpus to
HF first.

**`ors`** *is* a genuine local-directory loader, and its layout is simple:

```
<train_dataset_path>/
  Track00000/
    audio.mp3          # actually glob('audio.*'), so any ffmpeg-readable file
    metadata.json      # {"Beatmaps": {"<stem>": {"StandardStarRating": {"0": 4.2}, "Index": 1234}}}
    beatmaps/
      <stem>.osu
  Track00001/
    ...
```

Track directories must be `Track` + a zero-padded 5-digit contiguous index, and
`train_dataset_start`/`train_dataset_end` are indices into that numbering, not
counts.

But `ors` is the **pre-V29 legacy loader** and is incompatible with the v32
checkpoint that `lora_kuhy.yaml` fine-tunes:

- `OrsDataset._validate_args` (`ors_dataset.py:73-79`) hard-raises on
  `gamemodes != [0]`, on `add_kiai`, and on `add_year_token`. `v32.yaml` sets
  `add_year_token: true`, so construction fails immediately.
- It has no `_get_special_tokens` path at all, so it cannot emit v32's gamemode,
  year, song-length, keycount, hold-note-ratio or scroll-speed prefix tokens.
- It treats `context_types["out"]` as a scalar, where v32 (and `web`/`mmrs`) use
  a list.

So `ors` would mean training an older-architecture model from
`configs/train/default.yaml`, **not** fine-tuning `OliBomby/Mapperatorinator-v32`.

## What this leaves

Three real options, in rough order of cost:

1. **Upload a corpus to Hugging Face** and keep using `dataset_type: "web"`.
   The 400-map audio join in `docs/lazer-library.md` is already enough to build
   one; the work is shaping it into the row schema `web` expects (an `opus`
   audio column plus a `json` column whose `beatmaps` list carries each
   difficulty's raw `.osu` text under `content`, filtered on `beatmapset_id`,
   `mode`, `approved`, `difficultyrating`). Needs an HF account/token — not an
   osu! one.
2. **Train an older-architecture model via `ors`** from the local library. The
   loader is happy with a local path and the layout is easy to produce, but the
   result is not a v32 LoRA and cannot reuse the v32 checkpoint.
3. **Accept the plateau** and spend the effort on the blind test instead, which
   measures whether the *current* output is actually good.

This is a scope decision, not a technical one — it should be made deliberately
rather than discovered halfway through building shards.
