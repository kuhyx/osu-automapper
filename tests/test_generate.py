"""Tests for the upstream generation driver."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from osu_automapper.config import Paths
from osu_automapper.generate import (
    CompletedProcessLike,
    GenerationError,
    GenerationRequest,
    build_command,
    generate,
)
from osu_automapper.parse import Mode


@dataclass
class FakeResult:
    """Stand-in for ``subprocess.CompletedProcess``."""

    returncode: int
    stderr: str = ""


class FakeRunner:
    """Records the command it was asked to run."""

    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        """Store the result this runner will return."""
        self.result = FakeResult(returncode, stderr)
        self.command: list[str] = []
        self.env: dict[str, str] = {}

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
        """Capture the invocation and return the canned result."""
        self.command = command
        self.env = env
        return self.result


@pytest.fixture
def installed_paths(tmp_path: Path) -> Paths:
    """Return paths pointing at a fake but present upstream venv."""
    python = tmp_path / "up" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    return Paths(mapperatorinator_home=tmp_path / "up", data_root=tmp_path / "data")


def test_overrides_include_required_style_keys(tmp_path: Path) -> None:
    request = GenerationRequest(audio_path=tmp_path / "a.mp3", output_path=tmp_path / "out")
    overrides = request.to_overrides()
    assert any(o.startswith("difficulty=") for o in overrides)
    assert any(o.startswith("year=") for o in overrides)
    assert "gamemode=0" in overrides
    assert "export_osz=true" in overrides


def test_optional_overrides_omitted_when_unset(tmp_path: Path) -> None:
    overrides = GenerationRequest(
        audio_path=tmp_path / "a.mp3", output_path=tmp_path / "out"
    ).to_overrides()
    assert not any(o.startswith("seed=") for o in overrides)
    assert not any(o.startswith("keycount=") for o in overrides)
    assert not any(o.startswith("title=") for o in overrides)


def test_mania_overrides_include_keycount(tmp_path: Path) -> None:
    request = GenerationRequest(
        audio_path=tmp_path / "a.mp3",
        output_path=tmp_path / "out",
        mode=Mode.MANIA,
        keycount=4,
        seed=1337,
        title="Song",
        artist="Band",
        preview_time=1598,
        extra={"temperature": "0.9"},
    )
    overrides = request.to_overrides()
    assert "gamemode=3" in overrides
    assert "keycount=4" in overrides
    assert "seed=1337" in overrides
    assert "title=Song" in overrides
    assert "artist=Band" in overrides
    assert "preview_time=1598" in overrides
    assert "temperature=0.9" in overrides


def test_build_command_uses_upstream_python(installed_paths: Paths, tmp_path: Path) -> None:
    request = GenerationRequest(audio_path=tmp_path / "a.mp3", output_path=tmp_path / "out")
    command = build_command(request, installed_paths)
    assert command[0] == str(installed_paths.python)
    assert command[1] == str(installed_paths.inference_script)


def test_generate_success_returns_output_path(installed_paths: Paths, tmp_path: Path) -> None:
    request = GenerationRequest(audio_path=tmp_path / "a.mp3", output_path=tmp_path / "out")
    runner = FakeRunner()
    assert generate(request, installed_paths, runner) == request.output_path
    assert runner.env["HF_HOME"] == str(installed_paths.hf_home)


def test_generate_augments_environment_rather_than_replacing_it(
    installed_paths: Paths, tmp_path: Path
) -> None:
    """A bare env would strip PATH/HOME and break upstream's interpreter."""
    request = GenerationRequest(audio_path=tmp_path / "a.mp3", output_path=tmp_path / "out")
    runner = FakeRunner()
    generate(request, installed_paths, runner)
    assert "PATH" in runner.env
    assert runner.env["HF_HOME"] == str(installed_paths.hf_home)


def test_generate_raises_when_upstream_missing(tmp_path: Path) -> None:
    paths = Paths(mapperatorinator_home=tmp_path / "absent", data_root=tmp_path / "data")
    request = GenerationRequest(audio_path=tmp_path / "a.mp3", output_path=tmp_path / "out")
    with pytest.raises(GenerationError, match=r"install\.sh"):
        generate(request, paths, FakeRunner())


def test_generate_raises_on_nonzero_exit(installed_paths: Paths, tmp_path: Path) -> None:
    request = GenerationRequest(audio_path=tmp_path / "a.mp3", output_path=tmp_path / "out")
    with pytest.raises(GenerationError, match="inference failed"):
        generate(request, installed_paths, FakeRunner(returncode=1, stderr="boom"))


def test_real_subprocess_adapter_runs_a_command(tmp_path: Path) -> None:
    """The default runner really shells out; exercised with a harmless command."""
    from osu_automapper.generate import _run_subprocess

    result = _run_subprocess(
        ["/bin/echo", "hello"],
        cwd=str(tmp_path),
        env={},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_generate_uses_real_runner_by_default(tmp_path: Path) -> None:
    """With no runner injected, generate() falls back to the subprocess adapter."""
    python = tmp_path / "up" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    # A python that exits non-zero: proves the default path executed it for real.
    python.write_text("#!/bin/sh\nexit 3\n")
    python.chmod(0o755)
    paths = Paths(mapperatorinator_home=tmp_path / "up", data_root=tmp_path / "data")
    request = GenerationRequest(audio_path=tmp_path / "a.mp3", output_path=tmp_path / "out")
    with pytest.raises(GenerationError, match="inference failed"):
        generate(request, paths)
