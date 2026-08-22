"""Anonymise a mix of real and generated maps so they can be judged blind.

Never part of CI: this is a human-in-the-loop measurement, and the honest answer
to "is this map good?" is a person playing it without knowing its origin.
"""

from __future__ import annotations

import json
import random
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
