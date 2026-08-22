"""Build a training corpus from the local lazer library.

Upstream's ``web`` loader reads webdataset shards whose schema was measured off
a real corpus rather than guessed -- see ``docs/corpus-options.md`` for why the
other two loaders (``mmrs``, ``ors``) are unavailable here.
"""

from __future__ import annotations

from osu_automapper.corpus.build import AudioCandidate, build_sample, group_by_set, match_audio
from osu_automapper.corpus.model import BeatmapEntry, MapsetSample
from osu_automapper.corpus.shards import ShardError, chunk, verify_shard, write_shard

__all__ = [
    "AudioCandidate",
    "BeatmapEntry",
    "MapsetSample",
    "ShardError",
    "build_sample",
    "chunk",
    "group_by_set",
    "match_audio",
    "verify_shard",
    "write_shard",
]
