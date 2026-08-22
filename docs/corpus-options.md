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

## "Do we need to upload it?" -- yes, for the `web` route

Worth stating precisely, because a partial test suggested otherwise and was
wrong. `WebDataset` uses two different HF calls, and only one of them tolerates
a local path:

| call | local path? |
|---|---|
| `load_dataset(repo_id, data_files=...)` (`web_dataset.py:95`) | **yes** -- reads local parquet fine |
| `list_repo_files(repo_id, repo_type="dataset")` (`web_dataset.py:71-74`) | **no** -- always hits `huggingface.co/api/...` |

`list_repo_files` runs unconditionally in `__init__`, so it fails before the
loader ever reaches `load_dataset`. Verified: a hand-built local cache directory
(`hub/datasets--<ns>--<name>/snapshots/<sha>/`) with `refs/main` still raised
`OfflineModeIsEnabled`, and `HF_HUB_OFFLINE=1` fails for the *already-downloaded*
`project-riz/osu-beatmaps` too -- there is no cached file listing to fall back
on. Upstream has no `local_files_only` option anywhere.

So on the `web` route the corpus must exist as a real HF dataset repo. It can be
**private** -- nothing here needs it public -- but it does have to be uploaded,
and upstream must not be modified to avoid it (it is a third-party sibling).

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

## Building the shards

`./run.sh corpus` implements option 1's local half: it scans the blob store,
groups difficulties into mapsets, matches each set to its audio, writes
webdataset `.tar` shards and verifies every one of them.

```bash
./run.sh corpus --dry-run              # what would be built, writes nothing
./run.sh corpus --shard-size 64        # write into <data>/corpus/compressed/
./run.sh corpus --gamemode 3           # mania instead of standard
```

Measured on this library: 2,864 standard beatmaps and 2,888 audio blobs across
563 mapsets. A manifest lands beside the shards recording what was built and any
verification problems; a failed verification fails the command rather than being
reported as success.

**Nothing in this command touches the network.** Uploading is a separate,
deliberate step.

### The schema, and how it was confirmed

Each sample is one mapset: a `<key>.json` / `<key>.opus` pair inside the tar.

```json
{"audio_hash": "...", "audio_length": 123.4,
 "beatmaps": [{"beatmap_id": 1, "beatmapset_id": 2, "mode": 0, "creator_id": 3,
               "approved": 1, "difficultyrating": 4.2, "content": "osu file format v14..."}]}
```

`beatmap_id`, `beatmapset_id`, `mode`, `creator_id` and `content` are read with
`[]` in `web_dataset.py`, so a missing one crashes training rather than skipping
a sample; `verify_shard` checks all five. `approved`, `difficultyrating`,
`approved_date` and `submit_date` drive `filter_web_beatmaps`, whose absence
silently excludes the beatmap instead.

This was verified against a real 25.8 MB shard, not assumed:

- `datasets` decodes the audio to 16 kHz mono
- upstream's own `filter_web_beatmaps` keeps every beatmap under
  `gamemodes=[0], ranked_statuses=[1,2]`
- `slider.Beatmap.parse` -- the call the training loop makes -- parses all 68
  difficulties with zero failures

### Two honest caveats about the metadata

lazer keeps no osu! web metadata, so two fields are *asserted* rather than known:

- **`approved` is set to 1 ("ranked") for everything.** The local library holds
  whatever was downloaded, ranked or not. Setting anything else would make every
  sample invisible to `ranked_statuses: [1, 2]`.
- **`beatmap_id` / `creator_id` are content hashes**, since lazer does not retain
  ids for every map. The loader only uses them as identity, and hashing is
  stable across rebuilds. Note these are *not* what the year is derived from:
  dating reads the real `BeatmapSetID` off the group key, so a content hash
  never reaches `year_for_set_id`.
- **A 2020 date is ambiguous, and 13% of the corpus is on it.** `FALLBACK_DATE`
  is `2020-01-01`, the same value a genuinely-2020 set gets, so mapsets grouped
  by artist+title (no id to date from) cannot be told apart from real 2020 ones.
  Counted on the built shards: **75 of 562 samples (13.3%) carry no usable
  `BeatmapSetID`** and take the fallback, so of the 100 samples dated 2020 only
  **25 are actually 2020**.

  This matters more than a metadata wart, because `add_year_token: true` means
  every one of those 75 trains the *2020* token specifically -- a milder form of
  the single-year pile-up `dates.py` exists to prevent. It is a seventh of the
  corpus rather than the bulk, so it skews the year distribution without
  dominating it. If that becomes a problem, dating those sets from their audio
  or dropping them beats moving the fallback to a year nobody asks for.

Neither is load-bearing for training, but neither should be reported as real
osu! metadata.

## Uploading it (option 1's other half)

```bash
./scripts/upload_corpus.sh --dry-run    # check the repo and privacy, send nothing
./scripts/upload_corpus.sh              # create if needed, verify private, upload
```

The default destination is the **private** dataset repo `kuhy/osu-mapsets-lazer`
(override with `--repo-id` or `REPO_ID`).

Three things about this script are deliberate:

- **It lives in `scripts/`, not in the package.**
  `tests/test_no_upload_boundary.py` forbids the bare word `upload` anywhere
  under `osu_automapper/`, because that package must contain no path capable of
  submitting a beatmap to osu!. Publishing a training corpus to Hugging Face is
  a different act, but the boundary is kept blunt and structural rather than
  clever, so the uploader stays outside the package it protects.
- **Privacy is read back off the Hub API before any bytes move.**
  `hf repo create --private` is honoured only when that call is the one that
  creates the repo, so an existing *public* repo would happily accept the upload
  and stay public. `scripts/hf_repo_privacy.py` asks the API what the repo
  actually is, and the script refuses on anything but an explicit `true` — a
  network or auth failure never reads as "private".
- **It refuses to run without `manifest.json`.** The manifest is written only
  after every shard verifies, so its absence means the build did not finish and
  the shards are not known to be good.

Neither the `hf` CLI nor `huggingface_hub` is on `PATH` or in this repo's venv;
both are read out of the upstream sibling's venv
(`~/Mapperatorinator/.venv/`), which is never modified. The manifest is uploaded
alongside the shards because it lives one level *above* `compressed/` and would
otherwise be left behind.
