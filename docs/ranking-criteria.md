# Ranking criteria: why these maps cannot be ranked

## The rule

The osu! [Ranking Criteria](https://osu.ppy.sh/wiki/en/Ranking_criteria) contains
an **AI policy** section. Verbatim, from the
[osu-wiki source](https://raw.githubusercontent.com/ppy/osu-wiki/master/wiki/Ranking_criteria/en.md):

> A beatmap's hit objects, hitsounds and timing must be created exclusively by
> direct human input without the use of any generative tooling. Creating
> beatmaps is a fundamentally creative process, so using shortcuts like
> generative AI is unacceptable for ranking.

The same section also bars substantially AI-generated image assets, videos and
songs. Its stated intent:

> The core intent of these rules is allowing osu! to remain a space to celebrate
> human creativity, and its community a welcoming one to artists. Allowing
> exclusively human-created songs, artwork, and beatmaps goes hand-in-hand with
> these goals.

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
is permitted while only *ranking* is prohibited.

Checked directly: `Rules/en.md` and `Beatmapping/Beatmap_submission/en.md`
contain **zero** mentions of AI or generative tooling. So the Ranking Criteria
governs ranking and is *silent* on uploading. The RC's own wording ("unacceptable
**for ranking**") implies that scope, but silence is not permission, and the
explicit "uploading is allowed, ranking is not" phrasing is **community-sourced**
(a forum post), not an official rule. It should not be attributed to the RC.

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

The plan cited *DOBERMAN INFINITY - The other story (TV Size)*, set 2396177,
mapper Fu Xuan — and was internally inconsistent, calling it "confirmed" in one
place and "rumour" in another. It was checked against primary sources.

**The unranking is VERIFIED.** An official notice on the beatmap discussion page
(posted by BanchoBot, 2025-11-18, recovered from Wayback captures of osu!'s own
pages) reads:

> The team has determined with near certainty that AI assistance was used to
> create one or more difficulties in this beatmap set. Because this violates the
> ranking criteria, the set has been permanently removed from the ranked
> category.

The event chain matches: ranked 2025-08-30, disqualified and discussion-locked
with reason `unrank` on 2025-11-18, status `graveyard` by 2025-11-22.

**Two details in the plan are NOT supported:**

1. **The tool was not identified as Mapperatorinator.** The official notice says
   only "AI assistance". Nothing from osu! staff names any specific tool, so this
   documentation does not either.
2. **"Set deleted" was a separate, later event** — the set survived as graveyard
   through at least 2025-11-30 and only 404'd afterwards.

The claim that the mapper was removed from the BNG is community-sourced only.

The prohibition above stands on its own regardless: it is a rule, not a
precedent.
