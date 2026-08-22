"""Filesystem layout shared by generation and gating.

All large/binary artifacts (checkpoints, audio, ``.osz``, corpus) live outside the
repository under ``DATA_ROOT`` so the no-binaries pre-commit hook stays satisfied.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAPPERATORINATOR_HOME = Path.home() / "Mapperatorinator"
DEFAULT_DATA_ROOT = Path.home() / "osu-automapper_data"


@dataclass(frozen=True)
class Paths:
    """Resolved locations for upstream and our own data."""

    mapperatorinator_home: Path
    data_root: Path

    @classmethod
    def from_env(cls) -> Paths:
        """Build paths, allowing environment overrides for both roots."""
        home = Path(os.environ.get("MAPPERATORINATOR_HOME", DEFAULT_MAPPERATORINATOR_HOME))
        root = Path(os.environ.get("OSU_AUTOMAPPER_DATA", DEFAULT_DATA_ROOT))
        return cls(mapperatorinator_home=home, data_root=root)

    @property
    def python(self) -> Path:
        """Interpreter of the upstream (torch) virtualenv."""
        return self.mapperatorinator_home / ".venv" / "bin" / "python"

    @property
    def inference_script(self) -> Path:
        """Upstream Hydra entry point."""
        return self.mapperatorinator_home / "inference.py"

    @property
    def hf_home(self) -> Path:
        """Checkpoint cache, kept beside our other large artifacts."""
        return self.data_root / "hf"

    @property
    def songs(self) -> Path:
        """Input audio directory."""
        return self.data_root / "songs"

    @property
    def out(self) -> Path:
        """Generated beatmap output directory."""
        return self.data_root / "out"

    @property
    def blindtest(self) -> Path:
        """Blind-test shuffle keys and packs."""
        return self.data_root / "blindtest"
