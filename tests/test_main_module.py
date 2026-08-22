"""The ``python -m osu_automapper`` entry point."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_module_entry_point_runs(std_map: Path) -> None:
    """Running as a module must behave exactly like the console script."""
    result = subprocess.run(
        [sys.executable, "-m", "osu_automapper", "check", str(std_map)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "technically rankable" in result.stdout
