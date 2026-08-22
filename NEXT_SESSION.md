# Next session prompt — osu-automapper

Paste everything below the line into a fresh session.

---

Continue work on `~/osu-automapper` (public repo `kuhyx/osu-automapper`, clean
and fully pushed as of 2026-08-22 17:00). Read `docs/finetuning.md` and
`docs/gates.md` first — they hold the measured findings, and re-deriving them
costs GPU hours.

## What already works — do not rebuild any of it

- **Generation + gates.** `./run.sh generate|check|check-osz|repair|blindtest|blindtest-score`.
  Verified on real output for osu!standard AND osu!mania. 137 tests, 100% branch
  coverage, mypy --strict / ruff / shellcheck clean, CI green, pre-commit installed.
- **Quality confirmed by a human**: kuhy played a generated map and reported it
  "plays fine, on beat, everything seems working correctly". A 4.07★ map
  (`out/std_4star_s7`) passes all 14 checks.
- **LoRA fine-tuning runs end to end.** A 3000-step run completed cleanly
  (zero errors). `configs/train/lora_kuhy.yaml` in the upstream clone, mirrored
  at `docs/lora_kuhy.yaml` and gated by `scripts/check_training_config.py`.
- **Upstream is a third-party sibling** at `~/Mapperatorinator` — never vendor,
  modify or PR it. It is in `THIRD_PARTY_REPOS` in `~/utils/file_length/config.py`.
- **Hard boundary: nothing is ever uploaded to osu!.** The Ranking Criteria
  forbids generative tooling outright, so these maps cannot be ranked.
  `tests/test_no_upload_boundary.py` fails the build on any submit endpoint,
  credential or HTTP-client import. The passing state is named
  `technically_rankable`, never `rankable`. See `docs/ranking-criteria.md`.

## Measured facts — trust these instead of re-measuring

- **Inference is deterministic.** Two no-LoRA runs at the same seed produce
  byte-identical hit objects. So any same-seed difference is real signal, and an
  unexplained one must be explained rather than dismissed as variance.
- **Snap checking needs a divisor FAMILY** `(1,2,3,4,5,6,7,8,9,12,16)`. Over 300
  ranked maps / 129,097 objects: powers of two alone falsely flag 11 maps
  (triplet 1/12), lazer's 1/5,1/7,1/9 five more. p99 error ~1.4 ms. The ~2% that
  still fail are REAL unsnaps ranked maps ship — never add a % tolerance.
- **LoRA training on `project-riz/osu-beatmaps` plateaus immediately.** Loss
  0.752 → 0.742 across 3000 steps (delta −0.011 vs noise ±0.052) because that is
  the corpus v32 was already trained on. Do NOT respond by raising `base_lr` or
  adding steps — it is a data problem, not a hyperparameter one.
- **The adapters still change style despite flat loss** (seed 555, difficulty 5.0):

  | | objects | circles | sliders | stars |
  |---|---|---|---|---|
  | base | 973 | 679 | 293 | 4.91 |
  | checkpoint_10 | 808 | 513 | 291 | 4.84 |
  | checkpoint_11 | 848 | 447 | 401 | 4.52 |
  | checkpoint_12 | 848 | 447 | 401 | 4.52 |

  All pass the gate. Re-run with `./scripts/eval_checkpoints.sh`.
- **The run converged before it ended.** checkpoint_11 and checkpoint_12 have
  **byte-identical adapter weights** (same md5 on `adapter_model.safetensors`),
  so the final 250 steps changed nothing. Together with the flat loss this means
  a future run on this corpus should stop early — there is nothing to gain.
- **Final test metrics**: fuzzy timing 96.9%, volume 97.0%, other 97.7%, exact
  timing 88.0%, hitsound 78.0%, position 49.7% (positions come from the separate
  diffusion model at inference, so the low number is expected).
- **Known model defect**: at low target difficulty the model sometimes emits a
  cluster of objects stacked at `t=0` (seeds 4004/7/21 gave 16/0/1). `./run.sh
  repair` strips it; it leaves clean and human maps byte-identical.

## Pick up here (roughly in value order)

1. **Play the blind test.** Already built and waiting:
   `~/osu-automapper_data/blindtest/blindtest-20260822T111919.osz` — 3 maps
   labelled A/B/C, anonymity verified (Version/Creator/Tags stripped). Import it
   into lazer, play without reading the key, then
   `./run.sh blindtest-score ~/osu-automapper_data/blindtest/20260822T111919.json A=ai B=human C=ai`.
   This is the only real answer to "are these maps actually good?" and it needs
   kuhy at the keyboard. Consider building a bigger pack first (6 maps).
2. **Train a LoRA on a corpus v32 has NOT seen** — the plateau above says this is
   the only way to get a real style change. kuhy's own lazer library is the
   obvious candidate: ~2786 std maps already local at `~/.local/share/osu/files`
   (see `reference-lazer-library-access` memory — content-addressed blobs, no
   Realm reader needed, join audio ID3 tags to `.osu [Metadata]`). Needs a
   webdataset-shaped corpus; that is real work, so **agree scope before starting**.
   Do NOT use `dataset_type: "mmrs"` — it needs an osu! OAuth token this project
   deliberately does not hold.
3. **A difficulty/gamemode reliability sweep**: generate 3★–7★ across std and
   mania, several seeds each, gate everything, and report where the model is
   reliable and where it breaks (e.g. how often the t=0 defect fires by
   difficulty). Cheap, fully automatable, and turns anecdotes into a table.
4. **Test a LoRA with mania** — every adapter so far is `gamemode=0` only
   (`ckpt_subfolders: ["gamemode=0"]`), and no mania+LoRA run has been done.

## Housekeeping

- `~/osu-automapper_data/` holds ~50 GB: a partial 49 GB corpus download that is
  NOT needed (training streams) and can be deleted, plus checkpoints and test
  output. `local_total_limit: 3` already pruned all but checkpoints 10–12.
- Bulk-downloading that corpus saturated the uplink hard enough to break DNS for
  `git push` and `huggingface.co`. Stream instead.
