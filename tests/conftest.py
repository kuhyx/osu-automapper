"""Shared fixtures.

Fixtures are hand-written ``.osu`` *text*: no binaries enter the repository, and a
minimal map makes each check's failure mode obvious.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MINIMAL_STD = """osu file format v14

[General]
AudioFilename: audio.mp3
PreviewTime: 5000
Mode: 0

[Metadata]
Title:Test Song
TitleUnicode:Test Song
Artist:Test Artist
ArtistUnicode:Test Artist
Creator:tester
Version:Normal

[Difficulty]
HPDrainRate:5
CircleSize:4
OverallDifficulty:7
ApproachRate:8
SliderMultiplier:1.4
SliderTickRate:1

[TimingPoints]
0,500,4,2,0,60,1,0

[HitObjects]
{objects}
"""

MINIMAL_MANIA = """osu file format v14

[General]
AudioFilename: audio.mp3
PreviewTime: 5000
Mode: 3

[Metadata]
Title:Test Song
TitleUnicode:Test Song
Artist:Test Artist
ArtistUnicode:Test Artist
Creator:tester
Version:Normal

[Difficulty]
HPDrainRate:5
CircleSize:4
OverallDifficulty:7
ApproachRate:8
SliderMultiplier:1.4
SliderTickRate:1

[TimingPoints]
0,500,4,2,0,60,1,0

[HitObjects]
{objects}
"""


def _std_objects(count: int = 80, step: int = 500) -> str:
    """Build a run of snapped circles long enough to clear the 30 s drain minimum."""
    return "\n".join(f"256,192,{i * step},1,0,0:0:0:0:" for i in range(count))


def _mania_objects(count: int = 80, step: int = 500, keys: int = 4) -> str:
    """Build a run of snapped mania notes cycling through every column."""
    lines = []
    for i in range(count):
        column = i % keys
        x = int((column + 0.5) * 512 / keys)
        lines.append(f"{x},192,{i * step},1,0,0:0:0:0:")
    return "\n".join(lines)


def write_map(tmp_path: Path, text: str, name: str = "test.osu") -> Path:
    """Write ``text`` to ``tmp_path`` and return the path."""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def std_map(tmp_path: Path) -> Path:
    """Return a valid standard beatmap that passes every check."""
    return write_map(tmp_path, MINIMAL_STD.format(objects=_std_objects()), "std.osu")


@pytest.fixture
def mania_map(tmp_path: Path) -> Path:
    """Return a valid 4K mania beatmap that passes every check."""
    return write_map(tmp_path, MINIMAL_MANIA.format(objects=_mania_objects()), "mania.osu")
