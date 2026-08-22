"""Validate ``.osz`` archives before they reach lazer.

The most common import failure is a beatmap whose declared ``AudioFilename`` is
not actually in the archive. That is mechanically checkable, so it is a gate
rather than something to discover by hand in the client.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from osu_automapper.report import CheckResult


class OszError(Exception):
    """Raised when an archive cannot be read as a ``.osz`` at all."""


@dataclass(frozen=True)
class OszContents:
    """What an archive holds, from an import point of view."""

    beatmaps: list[str]
    audio_declared: set[str]
    names: set[str]


def read_osz(path: Path) -> OszContents:
    """Inspect an ``.osz``.

    Raises:
        OszError: when the file is missing or is not a valid zip archive.

    """
    if not path.exists():
        raise OszError(f"no such archive: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            beatmaps = sorted(n for n in names if n.lower().endswith(".osu"))
            declared: set[str] = set()
            for name in beatmaps:
                text = archive.read(name).decode("utf-8-sig", errors="replace")
                for line in text.splitlines():
                    if line.startswith("AudioFilename:"):
                        declared.add(line.split(":", 1)[1].strip())
                        break
    except zipfile.BadZipFile as exc:
        raise OszError(f"{path}: not a valid zip archive") from exc
    return OszContents(beatmaps=beatmaps, audio_declared=declared, names=names)


def check_osz_importable(path: Path) -> list[CheckResult]:
    """Check that an archive has a beatmap and that its audio resolves."""
    contents = read_osz(path)
    results = [
        CheckResult(
            name="osz_has_beatmap",
            passed=bool(contents.beatmaps),
            message=f"{len(contents.beatmaps)} .osu file(s)",
        )
    ]
    missing = sorted(a for a in contents.audio_declared if a not in contents.names)
    results.append(
        CheckResult(
            name="osz_audio_present",
            passed=not missing,
            message="audio resolves" if not missing else f"declared but absent: {missing}",
        )
    )
    return results
