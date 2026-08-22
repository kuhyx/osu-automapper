# The gate suite

`osu-automapper check <path.osu>` turns "is this map broken?" into an exit code.
No model adjudicates: every check is a pure function over parsed `.osu` data.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | every blocking check passed — **technically rankable** |
| `1` | at least one blocking check failed |
| `2` | usage, IO or parse error ("we could not look", not "it is bad") |

The `1` / `2` split matters: a corrupt file must never be reported as a bad map,
and a bad map must never be reported as a tooling failure.

## What "technically rankable" does and does not mean

It means: correctly snapped, legal metadata and audio, sane timing, nothing
offscreen, no impossible object spacing. It does **not** mean the map is
eligible for ranking — see [`ranking-criteria.md`](ranking-criteria.md). The
name is deliberately awkward so a green gate is never quoted as eligibility.

## Common checks (every gamemode)

| Check | Rule |
|---|---|
| `has_objects` | at least one hit object |
| `drain_time` | ≥ 30 s |
| `metadata_present` | Title/Artist/Creator/Version non-empty **and not the model's `Unknown …` placeholders** |
| `audio_filename` | declared, and `.mp3` or `.ogg` |
| `preview_time` | `PreviewTime` set (the model leaves it `-1`) |
| `uninherited_timing` | ≥ 1 red line |
| `no_duplicate_timing_points` | no two red (or two green) points share a timestamp |
| `inherited_after_uninherited` | no green line before the first red one |
| `objects_snapped` | within 2 ms of a legal beat division |

### Why snapping needs a divisor *family*, not a divisor

An object counts as snapped when **any** divisor in
`BEAT_DIVISORS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 16)` places it on-grid.

This was measured, not guessed. Checking only powers of two reported 11 of 300
ranked maps as unsnapped; every one was really triplet-timed (1/12). Adding
lazer's 1/5, 1/7 and 1/9 cleared 5 more. Across 129,097 objects in 300 ranked
maps the p99 snap error is ~1.4 ms, which is what makes 2 ms the right bound.

The remaining ~2% of ranked maps do carry genuinely unsnapped objects. That is a
true positive, not noise to tune away — the threshold stays absolute, per-object.

## Standard checks

Positions inside 512×384 (spinners exempt), no two objects on the same
millisecond, ≥ 10 ms after a circle and ≥ 20 ms after a slider end, and a finite
positive `SliderMultiplier`.

## Mania checks

Keycount sane (`CircleSize`, whole, 1–18), every note inside a real column
(`column = x * keys // 512`), holds ending after they start, and no two notes in
one column at the same millisecond.

**Simultaneous notes are legal in mania** — a jump is two notes at one timestamp
in different columns. The standard `no_simultaneous_objects` rule would reject
every real mania map, which is exactly why the suite dispatches on `Mode:`.

## Star rating

Via `rosu-pp-py` (already an upstream dependency, so no dotnet/osu-tools build).
"Within ±0.5" is meaningless unless the ruleset is pinned, so the defaults are
explicit and overridable: **lazer, no mods, 1.0× clock**.

`rosu-pp` does not validate its input — it returns ~0.14★ for junk rather than
raising. The CLI therefore parses the map first, so the rating is only ever
computed for a file already known to be well-formed.
