"""Assemble lazer blobs into mapset samples ready for sharding.

Grouping is the whole job. The loader wants one audio track plus every
difficulty that uses it, but the blob store knows neither -- a ``.osu`` names its
audio by *filename* while blobs are hashes. Maps are therefore grouped by
``BeatmapSetID`` and matched to audio by tags plus duration, exactly as
``docs/lazer-library.md`` describes.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from osu_automapper.corpus.dates import submit_date_for_set_id
from osu_automapper.corpus.extract import ParsedBeatmap, bpm_of
from osu_automapper.corpus.model import BeatmapEntry, MapsetSample

# lazer holds no osu! web metadata, so ranked status cannot be known from disk.
# 1 is "ranked", which is what `ranked_statuses: [1, 2]` accepts; anything else
# would make every sample invisible to the loader's filter.
ASSUMED_APPROVED = 1
# Used only when a map carries no usable BeatmapSetID to date it from.
FALLBACK_DATE = "2020-01-01 00:00:00"


@dataclass(frozen=True)
class AudioCandidate:
    """One audio blob and what is known about it."""

    path: Path
    duration: float
    artist: str = ""
    title: str = ""


def _synthetic_id(*parts: str) -> int:
    """Derive a stable positive id from identifying strings.

    lazer does not keep osu! beatmap ids for every map, but the loader casts
    ``beatmap_id``/``creator_id`` with ``int()`` and uses them only as identity.
    A content hash is therefore both sufficient and reproducible.
    """
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _entry(beatmap: ParsedBeatmap, set_id: int, stars: float, submitted: str) -> BeatmapEntry:
    """Convert a parsed map into a corpus entry."""
    fields = beatmap.fields
    creator = fields.get("Creator", "unknown")
    version = fields.get("Version", "")
    title = fields.get("Title", "unknown")
    artist = fields.get("Artist", "unknown")
    length_seconds = max(beatmap.last_object_ms // 1000, 1)

    def number(key: str, default: float) -> float:
        try:
            return float(fields.get(key, default))
        except ValueError:
            return default

    return BeatmapEntry(
        beatmap_id=_synthetic_id(str(set_id), version, creator),
        beatmapset_id=set_id,
        mode=beatmap.mode,
        creator_id=_synthetic_id(creator),
        creator=creator,
        content=beatmap.text,
        difficultyrating=stars,
        approved=ASSUMED_APPROVED,
        approved_date=submitted,
        submit_date=submitted,
        version=version,
        artist=artist,
        title=title,
        bpm=bpm_of(beatmap.text),
        total_length=length_seconds,
        hit_length=max((beatmap.last_object_ms - beatmap.first_object_ms) // 1000, 1),
        count_normal=beatmap.circle_count,
        count_slider=beatmap.slider_count,
        count_spinner=beatmap.spinner_count,
        diff_size=number("CircleSize", 4.0),
        diff_overall=number("OverallDifficulty", 7.0),
        diff_approach=number("ApproachRate", 8.0),
        diff_drain=number("HPDrainRate", 5.0),
        max_combo=beatmap.object_count,
        tags=fields.get("Tags", ""),
        source=fields.get("Source", ""),
    )


def _submitted_date(set_key: str) -> str:
    """Date a mapset from its real osu! id when the group key carries one.

    Groups keyed by artist+title have no id to date from, so they keep the
    fallback; that is a small minority and better than inventing a year.
    """
    if set_key.startswith("set:"):
        raw = set_key.removeprefix("set:")
        if raw.isdigit():
            return submit_date_for_set_id(int(raw))
    return FALLBACK_DATE


StarRater = Callable[[Path], float]


def build_sample(
    set_key: str,
    beatmaps: Sequence[ParsedBeatmap],
    audio: AudioCandidate,
    rater: StarRater,
) -> MapsetSample | None:
    """Group one mapset's difficulties into a sample, or None when unusable."""
    if not beatmaps:
        return None
    set_id = _synthetic_id(set_key)
    submitted = _submitted_date(set_key)
    entries = []
    for beatmap in beatmaps:
        try:
            stars = rater(beatmap.path)
        except Exception:
            stars = 0.0
        entries.append(_entry(beatmap, set_id, stars, submitted))
    return MapsetSample(
        key=set_key,
        audio_hash=audio.path.name,
        audio_length=audio.duration,
        beatmaps=entries,
    )


def group_by_set(beatmaps: Sequence[ParsedBeatmap]) -> dict[str, list[ParsedBeatmap]]:
    """Group parsed maps into mapsets.

    ``BeatmapSetID`` is preferred; maps lacking one fall back to artist+title,
    which is what lazer itself shows as a set.
    """
    grouped: dict[str, list[ParsedBeatmap]] = {}
    for beatmap in beatmaps:
        set_id = beatmap.fields.get("BeatmapSetID", "").strip()
        if set_id and set_id not in {"-1", "0"}:
            key = f"set:{set_id}"
        else:
            artist = beatmap.fields.get("Artist", "?")
            title = beatmap.fields.get("Title", "?")
            key = f"name:{artist}::{title}"
        grouped.setdefault(key, []).append(beatmap)
    return grouped


def match_audio(
    beatmaps: Sequence[ParsedBeatmap], candidates: Sequence[AudioCandidate]
) -> AudioCandidate | None:
    """Pick the audio blob a mapset belongs to.

    The audio must be long enough to contain the longest difficulty and must not
    be wildly longer. Tag agreement decides between equally plausible files.
    """
    if not beatmaps or not candidates:
        return None
    end = max(b.last_object_ms for b in beatmaps) / 1000.0
    artist = beatmaps[0].fields.get("Artist", "").lower().strip()
    title = beatmaps[0].fields.get("Title", "").lower().strip()

    fits = [c for c in candidates if end - 2 <= c.duration <= end + 120]
    if not fits:
        return None
    tagged = [
        c for c in fits if c.title.lower().strip() == title and c.artist.lower().strip() == artist
    ]
    pool = tagged or fits
    return min(pool, key=lambda c: abs(c.duration - end))
