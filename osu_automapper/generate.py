"""Drive Mapperatorinator by subprocess.

This package never imports torch: upstream lives in its own python 3.10 venv and
is invoked as a process. That separation is what keeps our test run fast and
CUDA-free while still exercising every line of our own code.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from osu_automapper.config import Paths
from osu_automapper.parse import Mode


class CompletedProcessLike(Protocol):
    """The part of ``subprocess.CompletedProcess`` this module reads."""

    @property
    def returncode(self) -> int:
        """Process exit status."""
        ...

    @property
    def stderr(self) -> str:
        """Captured standard error."""
        ...


class ProcessRunner(Protocol):
    """A ``subprocess.run``-shaped callable, injectable for tests."""

    def __call__(
        self,
        command: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> CompletedProcessLike:
        """Run ``command`` and return its result."""
        ...


class GenerationError(Exception):
    """Raised when upstream inference fails."""


@dataclass(frozen=True)
class GenerationRequest:
    """Every input that affects the produced map.

    ``difficulty`` and ``year`` are not optional in practice: leaving them unset
    makes upstream's difficulty and style drift between runs. ``title``/``artist``
    /``preview_time`` are set because the model otherwise emits "Unknown Title"
    and ``PreviewTime: -1``, both of which fail the gate.
    """

    audio_path: Path
    output_path: Path
    mode: Mode = Mode.STANDARD
    difficulty: float = 5.5
    year: int = 2023
    seed: int | None = None
    keycount: int | None = None
    title: str | None = None
    artist: str | None = None
    preview_time: int | None = None
    export_osz: bool = True
    extra: dict[str, str] = field(default_factory=dict)

    def to_overrides(self) -> list[str]:
        """Render the request as Hydra ``key=value`` overrides."""
        overrides = [
            f"audio_path={self.audio_path}",
            f"output_path={self.output_path}",
            f"gamemode={int(self.mode)}",
            f"difficulty={self.difficulty}",
            f"year={self.year}",
            f"export_osz={str(self.export_osz).lower()}",
        ]
        optional = {
            "seed": self.seed,
            "keycount": self.keycount,
            "preview_time": self.preview_time,
        }
        overrides += [f"{key}={value}" for key, value in optional.items() if value is not None]
        # Quoted: titles and artists routinely contain spaces and punctuation.
        for key, value in (("title", self.title), ("artist", self.artist)):
            if value is not None:
                overrides.append(f"{key}={value}")
        overrides += [f"{key}={value}" for key, value in sorted(self.extra.items())]
        return overrides


def _run_subprocess(
    command: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    capture_output: bool,
    text: bool,
    check: bool,
) -> CompletedProcessLike:
    """Adapt ``subprocess.run`` to the :class:`ProcessRunner` shape."""
    return subprocess.run(
        command, cwd=cwd, env=env, capture_output=capture_output, text=text, check=check
    )


def build_command(request: GenerationRequest, paths: Paths) -> list[str]:
    """Build the full upstream inference command line."""
    return [str(paths.python), str(paths.inference_script), *request.to_overrides()]


def generate(
    request: GenerationRequest,
    paths: Paths | None = None,
    runner: ProcessRunner | None = None,
) -> Path:
    """Run inference and return the directory the map was written to.

    Raises:
        GenerationError: when upstream exits non-zero or is not installed.

    """
    resolved = paths or Paths.from_env()
    if not resolved.python.exists():
        raise GenerationError(f"upstream venv missing: {resolved.python}. Run ./install.sh")

    command = build_command(request, resolved)
    execute: ProcessRunner = runner if runner is not None else _run_subprocess
    result = execute(
        command,
        cwd=str(resolved.mapperatorinator_home),
        env={"HF_HOME": str(resolved.hf_home)},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GenerationError(f"inference failed ({result.returncode}): {result.stderr[-2000:]}")
    return request.output_path
