"""The row schema upstream's ``web`` dataset loader expects.

Every field here was read off a real shard of ``project-riz/osu-beatmaps``
rather than inferred, because a corpus that merely looks plausible fails deep
inside training. See ``docs/corpus-options.md``.

A sample is one *mapset*: a single audio track plus every difficulty mapped to
it. That grouping is load-bearing -- ``add_gd_context`` skips samples holding one
difficulty, and the loader decodes the audio once per mapset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Read with `[]` in web_dataset.py, so a missing one is a crash, not a skip.
REQUIRED_BEATMAP_FIELDS = ("beatmap_id", "beatmapset_id", "mode", "creator_id", "content")

# Read with `.get()` by the filter; absent means "excluded", which is quieter
# and worse than crashing, so they are always written.
FILTER_BEATMAP_FIELDS = ("approved", "difficultyrating", "approved_date", "submit_date")


@dataclass(frozen=True)
class BeatmapEntry:
    """One difficulty inside a mapset."""

    beatmap_id: int
    beatmapset_id: int
    mode: int
    creator_id: int
    creator: str
    content: str
    difficultyrating: float
    approved: int
    approved_date: str
    submit_date: str
    version: str
    artist: str
    title: str
    bpm: float
    total_length: int
    hit_length: int
    count_normal: int
    count_slider: int
    count_spinner: int
    diff_size: float
    diff_overall: float
    diff_approach: float
    diff_drain: float
    max_combo: int
    tags: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Render as the loader expects to read it."""
        payload: dict[str, Any] = {
            "beatmap_id": self.beatmap_id,
            "beatmapset_id": self.beatmapset_id,
            "mode": self.mode,
            "creator_id": self.creator_id,
            "creator": self.creator,
            "content": self.content,
            "difficultyrating": self.difficultyrating,
            "approved": self.approved,
            "approved_date": self.approved_date,
            "submit_date": self.submit_date,
            "last_update": self.approved_date,
            "version": self.version,
            "artist": self.artist,
            "artist_unicode": self.artist,
            "title": self.title,
            "title_unicode": self.title,
            "bpm": self.bpm,
            "total_length": self.total_length,
            "hit_length": self.hit_length,
            "count_normal": self.count_normal,
            "count_slider": self.count_slider,
            "count_spinner": self.count_spinner,
            "diff_size": self.diff_size,
            "diff_overall": self.diff_overall,
            "diff_approach": self.diff_approach,
            "diff_drain": self.diff_drain,
            "max_combo": self.max_combo,
            "tags": self.tags,
            "source": self.source,
        }
        # Fields the model never reads but the schema carries; kept so a shard
        # is structurally interchangeable with the upstream corpus.
        payload.update(
            {
                "genre_id": 0,
                "language_id": 0,
                "favourite_count": 0,
                "rating": 0.0,
                "storyboard": 0,
                "video": 0,
                "download_unavailable": 0,
                "audio_unavailable": 0,
                "playcount": 0,
                "passcount": 0,
                "packs": "",
                "diff_aim": None,
                "diff_speed": None,
            }
        )
        return payload


@dataclass(frozen=True)
class MapsetSample:
    """One audio track and every difficulty that uses it."""

    key: str
    audio_hash: str
    audio_length: float
    beatmaps: list[BeatmapEntry] = field(default_factory=list)

    def to_json_payload(self) -> dict[str, Any]:
        """Render the ``.json`` member of the shard."""
        return {
            "audio_hash": self.audio_hash,
            "audio_length": self.audio_length,
            "beatmaps": [b.to_dict() for b in self.beatmaps],
        }

    def is_usable(self, gamemodes: tuple[int, ...], statuses: tuple[int, ...]) -> bool:
        """Report whether any difficulty survives the loader's own filter.

        Mirrors ``filter_web_beatmaps``: a sample none of whose beatmaps pass is
        silently skipped at train time, so writing it only wastes disk.
        """
        return any(b.mode in gamemodes and b.approved in statuses for b in self.beatmaps)
