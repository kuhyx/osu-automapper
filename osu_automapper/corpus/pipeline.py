"""Drive the whole corpus build: blobs in, verified shards out.

Kept separate from the CLI so the expensive parts (ffprobe over every audio
blob, star-rating every difficulty) are injectable and the command stays thin.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from osu_automapper.corpus.build import AudioCandidate, build_sample, group_by_set, match_audio
from osu_automapper.corpus.extract import ParsedBeatmap, classify, iter_blobs, parse_beatmap_blob
from osu_automapper.corpus.model import MapsetSample
from osu_automapper.corpus.shards import DEFAULT_SHARD_SIZE, verify_shard, write_shard

Prober = Callable[[Path], AudioCandidate | None]
StarRater = Callable[[Path], float]


@dataclass
class BuildStats:
    """What one corpus build produced."""

    beatmaps: int = 0
    mapsets: int = 0
    samples: int = 0
    shards: int = 0
    unmatched: int = 0
    problems: list[str] | None = None

    def to_json(self) -> str:
        """Serialise for the manifest beside the shards."""
        return json.dumps(
            {
                "beatmaps": self.beatmaps,
                "mapsets": self.mapsets,
                "samples": self.samples,
                "shards": self.shards,
                "unmatched": self.unmatched,
                "problems": self.problems or [],
            },
            indent=2,
        )


def probe_audio(path: Path) -> AudioCandidate | None:
    """Read an audio blob's duration and tags with ffprobe."""
    command = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "{}").get("format", {})
        duration = float(payload.get("duration", 0) or 0)
    except ValueError, json.JSONDecodeError:
        return None
    if duration <= 0:
        return None
    tags = {k.lower(): v for k, v in (payload.get("tags") or {}).items()}
    return AudioCandidate(
        path=path,
        duration=duration,
        artist=str(tags.get("artist", "")),
        title=str(tags.get("title", "")),
    )


def collect(
    library: Path, prober: Prober, gamemode: int = 0
) -> tuple[list[ParsedBeatmap], list[AudioCandidate]]:
    """Split the blob store into parsed beatmaps and probed audio."""
    beatmaps: list[ParsedBeatmap] = []
    audio: list[AudioCandidate] = []
    for blob in iter_blobs(library):
        kind = classify(blob)
        if kind == "beatmap":
            parsed = parse_beatmap_blob(blob)
            if parsed is not None and parsed.mode == gamemode:
                beatmaps.append(parsed)
        elif kind == "audio":
            candidate = prober(blob)
            if candidate is not None:
                audio.append(candidate)
    return beatmaps, audio


def assemble(
    beatmaps: Sequence[ParsedBeatmap],
    audio: Sequence[AudioCandidate],
    rater: StarRater,
    gamemode: int = 0,
    limit: int | None = None,
) -> tuple[list[tuple[MapsetSample, Path]], BuildStats]:
    """Group beatmaps into samples paired with the audio file to encode."""
    groups = group_by_set(beatmaps)
    stats = BuildStats(beatmaps=len(beatmaps), mapsets=len(groups))
    samples: list[tuple[MapsetSample, Path]] = []
    for key, entries in sorted(groups.items()):
        matched = match_audio(entries, audio)
        if matched is None:
            stats.unmatched += 1
            continue
        sample = build_sample(key, entries, matched, rater)
        if sample is None or not sample.is_usable(gamemodes=(gamemode,), statuses=(1, 2)):
            continue
        samples.append((sample, matched.path))
        if limit is not None and len(samples) >= limit:
            break
    stats.samples = len(samples)
    return samples, stats


def write_corpus(
    samples: Sequence[tuple[MapsetSample, Path]],
    destination: Path,
    stats: BuildStats,
    shard_size: int = DEFAULT_SHARD_SIZE,
    on_shard: Callable[[Path, int], None] | None = None,
) -> BuildStats:
    """Write every shard and verify each one as it lands."""
    destination.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    index = 0
    for start in range(0, len(samples), shard_size):
        batch = samples[start : start + shard_size]
        target = destination / f"data-{index:06d}.tar"
        written = write_shard(batch, target)
        if written == 0:
            continue
        _, found = verify_shard(target)
        problems.extend(f"{target.name}: {p}" for p in found)
        if on_shard is not None:
            on_shard(target, written)
        index += 1
    stats.shards = index
    stats.problems = problems
    return stats
