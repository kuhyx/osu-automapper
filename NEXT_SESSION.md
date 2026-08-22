# Next session prompt — osu-automapper

Paste everything below the line into a fresh session.

---

Continue work on `~/osu-automapper` (public repo `kuhyx/osu-automapper`, clean
and fully pushed as of 2026-08-22 ~18:30, CI green). Read `docs/sweep.md`,
`docs/corpus-options.md` and `docs/lazer-library.md` first — they hold measured
findings, and several of them cost GPU hours or a wrong turn to establish.

## Two things need a human, do these first

1. **Play the 6-map blind test.** It is built and both known leaks are fixed:
   `~/osu-automapper_data/blindtest/blindtest-20260822T153940.osz`
   Import into lazer, play A–F **without reading the key**, then:
   ```bash
   ./run.sh blindtest-score ~/osu-automapper_data/blindtest/20260822T153940.json \
       A=ai B=human C=ai D=human E=ai F=human   # <- your actual guesses
   ```
   All six are MEGALOVANIA on identical audio, gate-clean, with interleaved star
   ratings (3.77/3.81, 4.48/4.63, 4.93/5.47) so difficulty is not the tell.
   This is still the only real answer to "are these maps any good?".

2. **Log in to Hugging Face** — the `hf` CLI is NOT on PATH; it lives in the
   upstream venv:
   ```bash
   ~/Mapperatorinator/.venv/bin/hf auth login
   ```
   kuhy chose a **private** HF dataset repo for the corpus. Everything up to the
   upload is done locally and needs no token; only the upload is blocked.

## What is new since the last handoff

- **`./run.sh sweep`** — resumable reliability sweep over
  (song × difficulty × gamemode × seed × adapter). Gates each cell **twice**:
  raw model output and post-`repair`. Per-cell JSON in
  `~/osu-automapper_data/sweep/`; existing cells are skipped on restart.
- **`./run.sh corpus`** — builds webdataset `.tar` shards from the lazer library
  in the exact schema upstream's `web` loader expects. Verified end to end
  against upstream's own code, not assumed.
- **Blind-test anonymisation now strips two leaks** that made the first pack
  worthless (see below).
- 252 tests, 100% branch coverage, mypy --strict / ruff / pre-commit clean, no
  suppressions.

## Measured facts — trust these instead of re-deriving them

- **A `gamemode=0` LoRA is silently ignored in mania.** Loading checkpoint_11
  with `--gamemode 3` produced hit objects **byte-identical to the base model**
  at seeds 1/2/3. Inference is deterministic, so that is proof, not coincidence.
  Never report mania+LoRA numbers as a LoRA result; a mania adapter must be
  trained with mania in `ckpt_subfolders`. (Item 4 is answered — done.)
- **The song dominates the failure rate, not the difficulty.** Two songs in:
  `dschinghis_khan_moskau` failed **22/22** cells while `celldweller_weaponized`
  passed 23/30. Moskau has 43 uninherited timing points with drifting BPM, and
  the model lands 5–10 ms off-grid right after a timing-point change (hand-checked
  against the correct active red line: 9.00/5.00/10.00 ms vs a 2 ms tolerance).
  These are real unsnapped objects. **Do not loosen `SNAP_TOLERANCE_MS`.**
- **Two invisible blind-test leaks, both fixed, both worth re-checking whenever a
  new source of maps is added:** `[Events]` (human maps ship backgrounds, breaks
  and storyboards; generated maps ship none) and **kiai** (`effects` bit 0 —
  human maps had 11 kiai rows, generated maps 0; it pulses the playfield). The
  gate catches broken maps, not leaks — diff a human entry against a generated
  one before playing.
- **The `web` route genuinely requires an upload.** `load_dataset` accepts local
  paths, but `list_repo_files` runs first, unconditionally, and always hits the
  Hub API. A hand-built local cache with `refs/main` still raised
  `OfflineModeIsEnabled`. There is no `local_files_only` anywhere upstream, and
  upstream must not be modified. A **private** repo is fine.
- **`ors` is the only local-directory loader and it cannot fine-tune v32**: it
  hard-raises on the `add_year_token` v32 sets, has no special-token path, and
  takes a scalar `context_types["out"]` where v32 uses a list.
- **Corpus schema (measured off a real shard, not guessed):** webdataset `.tar`
  of `<key>.json` + `<key>.opus` pairs, one sample per *mapset*. `beatmap_id`,
  `beatmapset_id`, `mode`, `creator_id`, `content` are read with `[]` and crash
  training if missing; `approved`, `difficultyrating`, `approved_date`,
  `submit_date` drive the filter and silently exclude instead.
- **Every mapset is dated from its osu! set id**, via an anchor table measured
  from 2,979 real id/date pairs. A constant date would train one year token while
  inference asks for `--year 2023` — the same silent-no-op shape as the mania bug.
  On this library it yields 16 distinct years, 2007–2025.
- **Two things the corpus asserts rather than knows** (do not read them back as
  real osu! metadata): `approved` is set to 1 for everything, and
  `beatmap_id`/`creator_id` are content hashes.

## Pick up here

1. **Finish and publish the sweep table.** The sweep was still running at ~65/180
   cells when the session ended; it is resumable, so just re-run it:
   ```bash
   ./run.sh sweep            # skips every cell already on disk
   ```
   Then fold the final table from `~/osu-automapper_data/sweep/REPORT.md` into
   `docs/sweep.md` and commit it — the data root is gitignored, so the headline
   result must be copied into the repo to survive.
2. **Finish the corpus and upload it** (needs step 2 above):
   ```bash
   ./run.sh corpus --shard-size 64      # ~562 usable mapsets, writes + verifies
   ```
   Then upload `~/osu-automapper_data/corpus/compressed/` to a **private** HF
   dataset repo and point a training config at it. Budget for the blockers in the
   `reference-mapperatorinator-training` memory (torchcodec ABI, flash-attn,
   wandb-only checkpoints) — training has not been attempted on this corpus yet.
3. **Consider a bigger blind test** once the first is scored: the lazer library
   has ~400 maps joined to audio, so packs on other songs are cheap now.
4. **A mania LoRA**, if mania is wanted — see the byte-identical finding above.

## Housekeeping

- The 49 GB unused corpus download is **deleted** (authorised); 2 TB free.
- `~/osu-automapper_data/` holds sweep results, shards, checkpoints and blind
  tests. `songs/` now has 6 songs spanning 100–240 BPM, five pulled from the
  lazer library; `docs/sweep.md` has the table with BPMs.
- Upstream `~/Mapperatorinator` is a third-party sibling: never vendor, modify or
  PR it.
- **Nothing is ever uploaded to osu!** — `tests/test_no_upload_boundary.py`
  enforces it. The passing state is `technically_rankable`, never `rankable`.
