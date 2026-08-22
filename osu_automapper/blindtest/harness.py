"""Anonymise a mix of real and generated maps so they can be judged blind.

Never part of CI: this is a human-in-the-loop measurement, and the honest answer
to "is this map good?" is a person playing it without knowing its origin.
"""

from __future__ import annotations

import json
import random
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass(frozen=True)
class Entry:
    """One anonymised map in a blind test."""

    label: str
    source: str
    generated: bool


@dataclass(frozen=True)
class BlindTest:
    """A shuffled set of entries plus the key needed to score it."""

    created: str
    entries: list[Entry]

    def to_json(self) -> str:
        """Serialise the shuffle key."""
        return json.dumps(
            {"created": self.created, "entries": [asdict(e) for e in self.entries]}, indent=2
        )

    @classmethod
    def from_json(cls, text: str) -> BlindTest:
        """Rebuild a blind test from a saved key."""
        payload = json.loads(text)
        return cls(
            created=payload["created"],
            entries=[Entry(**e) for e in payload["entries"]],
        )

    @property
    def answer_key(self) -> dict[str, bool]:
        """Map each label to whether it was generated."""
        return {e.label: e.generated for e in self.entries}


def build_blindtest(real: list[Path], generated: list[Path], seed: int | None = None) -> BlindTest:
    """Shuffle real and generated maps into a labelled, origin-hiding set.

    Raises:
        ValueError: when there are more maps than single-letter labels.

    """
    combined = [(p, False) for p in real] + [(p, True) for p in generated]
    if len(combined) > len(LABELS):
        raise ValueError(f"at most {len(LABELS)} maps supported, got {len(combined)}")
    rng = random.Random(seed)
    rng.shuffle(combined)
    entries = [
        Entry(label=LABELS[i], source=str(path), generated=is_generated)
        for i, (path, is_generated) in enumerate(combined)
    ]
    return BlindTest(created=datetime.now(UTC).isoformat(), entries=entries)


def score_blindtest(test: BlindTest, guesses: dict[str, bool]) -> tuple[int, int]:
    """Score guesses against the key, returning ``(correct, total_guessed)``.

    Only labels actually guessed are counted, so a partial session still scores.
    """
    key = test.answer_key
    scored = [(label, value) for label, value in guesses.items() if label in key]
    correct = sum(1 for label, value in scored if key[label] == value)
    return correct, len(scored)


def _anonymise(text: str, label: str) -> str:
    """Rewrite a beatmap's identifying metadata to a bare label.

    Version, Creator and Tags all leak origin -- upstream records its whole
    generation config in Tags, which would give the answer away immediately.
    """
    replacements = {"Version": label, "Creator": "blindtest", "Tags": ""}
    lines = []
    for line in text.splitlines():
        key, sep, _ = line.partition(":")
        if sep and key in replacements:
            lines.append(f"{key}:{replacements[key]}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def pack_blindtest(
    test: BlindTest, destination: Path, audio: Path | None = None
) -> tuple[Path, Path]:
    """Write the anonymised ``.osz`` and its answer key.

    All entries are packed as difficulties of one set so they appear together in
    lazer, labelled A, B, C... with no other distinguishing metadata.

    Returns:
        The archive path and the key path.

    Raises:
        OSError: when a source map cannot be read.

    """
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    archive_path = destination / f"blindtest-{stamp}.osz"
    key_path = destination / f"{stamp}.json"

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in test.entries:
            text = Path(entry.source).read_text(encoding="utf-8-sig", errors="replace")
            anonymous = _anonymise(text, entry.label)
            if audio is not None:
                anonymous = _retarget_audio(anonymous, audio.name)
            archive.writestr(f"blindtest [{entry.label}].osu", anonymous)
        if audio is not None:
            archive.write(audio, audio.name)

    key_path.write_text(test.to_json(), encoding="utf-8")
    return archive_path, key_path


def _retarget_audio(text: str, filename: str) -> str:
    """Point every difficulty at the single audio file packed in the archive."""
    lines = []
    for line in text.splitlines():
        if line.startswith("AudioFilename:"):
            lines.append(f"AudioFilename: {filename}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"
