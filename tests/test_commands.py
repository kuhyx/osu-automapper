"""Tests for the generate and blindtest subcommands."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from osu_automapper.blindtest import build_blindtest, pack_blindtest
from osu_automapper.cli import main
from osu_automapper.config import Paths

REAL_MAP = """osu file format v14

[General]
AudioFilename: original.mp3

[Metadata]
Title:Song
Artist:Band
Creator:HumanMapper
Version:Insane
Tags:human made

[HitObjects]
256,192,0,1,0,0:0:0:0:
"""

GENERATED_MAP = """osu file format v14

[General]
AudioFilename: other.mp3

[Metadata]
Title:Song
Artist:Band
Creator:Mapperatorinator
Version:Mapperatorinator V32
Tags:model=OliBomby/Mapperatorinator-v32 seed=1337

[HitObjects]
256,192,0,1,0,0:0:0:0:
"""


@pytest.fixture
def maps(tmp_path: Path) -> tuple[Path, Path]:
    """Write one human and one generated map."""
    real = tmp_path / "real.osu"
    real.write_text(REAL_MAP)
    generated = tmp_path / "gen.osu"
    generated.write_text(GENERATED_MAP)
    return real, generated


def test_pack_anonymises_identifying_metadata(tmp_path: Path, maps: tuple[Path, Path]) -> None:
    """Version, Creator and Tags must not survive: Tags carries the whole config."""
    real, generated = maps
    test = build_blindtest([real], [generated], seed=1)
    archive, key = pack_blindtest(test, tmp_path / "out")
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            text = zf.read(name).decode("utf-8")
            assert "Mapperatorinator" not in text
            assert "HumanMapper" not in text
            assert "model=" not in text
            assert "seed=1337" not in text
    assert key.exists()


def test_pack_includes_audio_and_retargets_it(tmp_path: Path, maps: tuple[Path, Path]) -> None:
    real, generated = maps
    audio = tmp_path / "shared.mp3"
    audio.write_bytes(b"audio")
    test = build_blindtest([real], [generated], seed=1)
    archive, _ = pack_blindtest(test, tmp_path / "out", audio=audio)
    with zipfile.ZipFile(archive) as zf:
        assert "shared.mp3" in zf.namelist()
        for name in (n for n in zf.namelist() if n.endswith(".osu")):
            assert "AudioFilename: shared.mp3" in zf.read(name).decode("utf-8")


def test_pack_without_audio_keeps_original_reference(
    tmp_path: Path, maps: tuple[Path, Path]
) -> None:
    real, generated = maps
    test = build_blindtest([real], [generated], seed=1)
    archive, _ = pack_blindtest(test, tmp_path / "out")
    with zipfile.ZipFile(archive) as zf:
        texts = [zf.read(n).decode("utf-8") for n in zf.namelist()]
    assert any("original.mp3" in t or "other.mp3" in t for t in texts)


def test_cli_blindtest_build_and_score(
    tmp_path: Path,
    maps: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real, generated = maps
    monkeypatch.setenv("OSU_AUTOMAPPER_DATA", str(tmp_path / "data"))
    assert (
        main(["blindtest", "--real", str(real), "--generated", str(generated), "--seed", "5"]) == 0
    )
    capsys.readouterr()

    key = next((Paths.from_env().blindtest).glob("*.json"))
    answers = {e["label"]: e["generated"] for e in json.loads(key.read_text())["entries"]}
    guesses = [f"{label}={'ai' if is_gen else 'human'}" for label, is_gen in answers.items()]
    assert main(["blindtest-score", str(key), *guesses]) == 0
    assert f"{len(answers)}/{len(answers)} correct" in capsys.readouterr().out


def test_cli_blindtest_build_rejects_too_many(
    tmp_path: Path, maps: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    real, _ = maps
    monkeypatch.setenv("OSU_AUTOMAPPER_DATA", str(tmp_path / "data"))
    argv = ["blindtest", "--real", *([str(real)] * 27), "--generated", str(real)]
    assert main(argv) == 2


def test_cli_blindtest_score_bad_key(tmp_path: Path) -> None:
    assert main(["blindtest-score", str(tmp_path / "absent.json"), "A=ai"]) == 2


def test_cli_blindtest_score_bad_guess_syntax(
    tmp_path: Path, maps: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    real, generated = maps
    monkeypatch.setenv("OSU_AUTOMAPPER_DATA", str(tmp_path / "data"))
    main(["blindtest", "--real", str(real), "--generated", str(generated), "--seed", "5"])
    key = next((Paths.from_env().blindtest).glob("*.json"))
    assert main(["blindtest-score", str(key), "A=perhaps"]) == 2


def test_cli_generate_reports_missing_upstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAPPERATORINATOR_HOME", str(tmp_path / "absent"))
    monkeypatch.setenv("OSU_AUTOMAPPER_DATA", str(tmp_path / "data"))
    assert main(["generate", str(tmp_path / "a.mp3"), str(tmp_path / "out")]) == 2


def test_cli_generate_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stub interpreter that exits 0 proves the success path end to end."""
    python = tmp_path / "up" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)
    monkeypatch.setenv("MAPPERATORINATOR_HOME", str(tmp_path / "up"))
    monkeypatch.setenv("OSU_AUTOMAPPER_DATA", str(tmp_path / "data"))
    out = tmp_path / "out"
    assert (
        main(
            [
                "generate",
                str(tmp_path / "a.mp3"),
                str(out),
                "--gamemode",
                "3",
                "--keycount",
                "4",
                "--seed",
                "7",
                "--title",
                "T",
                "--artist",
                "A",
                "--preview-time",
                "100",
            ]
        )
        == 0
    )
    assert str(out) in capsys.readouterr().out


def test_cli_blindtest_score_partial_guesses(
    tmp_path: Path,
    maps: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Guessing only some labels scores just those; the rest stay unrevealed."""
    real, generated = maps
    monkeypatch.setenv("OSU_AUTOMAPPER_DATA", str(tmp_path / "data"))
    main(["blindtest", "--real", str(real), "--generated", str(generated), "--seed", "5"])
    capsys.readouterr()

    key = next((Paths.from_env().blindtest).glob("*.json"))
    entries = json.loads(key.read_text())["entries"]
    first = entries[0]
    verdict = "ai" if first["generated"] else "human"
    assert main(["blindtest-score", str(key), f"{first['label']}={verdict}"]) == 0
    out = capsys.readouterr().out
    assert "1/1 correct" in out
    assert entries[1]["label"] not in out.split("correct")[1]
