# Ranking criteria: why these maps cannot be ranked

## The rule

The osu! [Ranking Criteria](https://osu.ppy.sh/wiki/en/Ranking_criteria) contains
an **AI policy** section. Verbatim, from the
[osu-wiki source](https://raw.githubusercontent.com/ppy/osu-wiki/master/wiki/Ranking_criteria/en.md):

> A beatmap's hit objects, hitsounds and timing must be created exclusively by
> direct human input without the use of any generative tooling.

The same section also bars substantially AI-generated image assets, videos and
songs. Its stated intent:

> The core intent of these rules is allowing osu! to remain a space to celebrate
> human creativity, and its community a welcoming one to artists.

This is unambiguous and it applies to exactly what this repository produces.
**Rankability is closed by rule, not by quality.** No amount of gate-passing
changes it, which is why improving the gate is not a route to eligibility.

## What this means for the project

The original done-condition was "passes osu ranked map requirements". That
requirement cannot be met by any generated map, so it was reframed rather than
silently narrowed:

| | |
|---|---|
| **The gate checks** | snapping, metadata, legal audio, preview point, timing sanity, playfield bounds, object spacing, star rating |
| **The gate does not check** | whether a Beatmap Nominator would nominate it — for a generated map that is a settled *no* |

The passing state is therefore named **`technically rankable`** in code, in the
JSON output and in the human-readable summary. The name is deliberately awkward
so that a green exit code can never be quoted as "this map is rankable".

A second, independent blocker exists regardless: a fully generated set is
unrankable anyway, because the host must have mapped most of the set themselves.

## Uploading

The plan this work came from asserted that *uploading* an AI map (to graveyard)
is permitted while only *ranking* is prohibited. **That distinction is not stated
in the Ranking Criteria text**, which addresses beatmaps in the ranking
procedure. Treat the permissibility of uploading as unverified.

It does not matter here, because nothing is uploaded.

## The no-upload boundary is structural, not a promise

`tests/test_no_upload_boundary.py` fails the build if the package ever gains:

- a reference to `osu.ppy.sh`, a submission endpoint, or `upload`/`submit`
- an API credential (`client_secret`, `OSU_API…`)
- an HTTP client import (`requests`, `httpx`, `urllib.request`, `aiohttp`)

The guard was canary-tested: injecting `import requests` and a submit URL fails
it, and removing them passes. There is no upload code path to disable, because
there is no upload code path.

## The unranking incident

The plan cited a specific case — *DOBERMAN INFINITY - The other story (TV Size)*,
set 2396177, mapper "Fu Xuan", ranked 2025-08-30 and unranked in Nov 2025 —
attributed to Mapperatorinator, the same tool used here. The plan itself was
internally inconsistent about this, calling it "confirmed" in one place and
"rumour" in another.

**Status: UNVERIFIED.** No primary source was located during this work. It is
recorded here as an unconfirmed report, not a fact.

The prohibition above stands entirely on its own without it.
