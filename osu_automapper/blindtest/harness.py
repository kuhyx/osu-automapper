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


def _strip_events(text: str) -> str:
    """Replace the ``[Events]`` section with an empty one.

    Metadata is not the only tell. Ranked maps ship backgrounds, break periods
    and storyboards; generated maps ship none of them, so the section's mere size
    identifies a map's origin before a note is played -- measured on a real pack:
    every human entry had 20 event lines, every generated entry had 0. The
    referenced images are not in the archive either, so leaving them in would
    also make the human entries render differently in lazer.
    """
    head, marker, tail = text.partition("[Events]")
    if not marker:
        return text
    _, next_marker, rest = tail.partition("\n[")
    remainder = f"\n[{rest}" if next_marker else ""
    return f"{head}[Events]\n//Background and Video events\n//Break Periods{remainder}"


def _strip_colours(text: str) -> str:
    """Remove the ``[Colours]`` section entirely.

    Custom combo colours are a palette a real mapper chose; generated maps emit
    the sampler's fixed defaults or none at all. Measured on the 2026-08-22 pack,
    no ``Combo<n>`` value was shared between the two groups, and the colours are
    plainly visible while playing. Removing the section makes every entry fall
    back to the skin's default palette.
    """
    head, marker, tail = text.partition("[Colours]")
    if not marker:
        return text
    _, next_marker, rest = tail.partition("\n[")
    return head + (f"[{rest}" if next_marker else "")


def _clear_kiai(text: str) -> str:
    """Turn off kiai on every timing point.

    A ``[TimingPoints]`` row is
    ``time,beatLength,meter,sampleSet,sampleIndex,volume,uninherited,effects``
    and bit 0 of ``effects`` enables kiai, which makes the playfield pulse and
    the background flash. Ranked maps kiai their chorus; generated maps never do
    -- measured on a real pack, every human entry had 11 kiai rows and every
    generated entry had none, which is visible within seconds of starting.

    Only that one bit is touched. Inherited timing points carry slider velocity
    and volume, so dropping rows would change how the human maps actually play
    and invalidate the very comparison being run.
    """
    head, marker, tail = text.partition("[TimingPoints]")
    if not marker:
        return text
    body, next_marker, rest = tail.partition("\n[")

    lines = []
    for line in body.splitlines():
        fields = line.split(",")
        if len(fields) >= 8:
            try:
                effects = int(fields[7])
            except ValueError:
                lines.append(line)
                continue
            fields[7] = str(effects & ~1)
            lines.append(",".join(fields))
        else:
            lines.append(line)

    remainder = f"\n[{rest}" if next_marker else ""
    return head + "[TimingPoints]" + "\n".join(lines) + remainder


# Where anonymisation stops
# -------------------------
# Two kinds of thing get scrubbed: *tool provenance* (editor state, BeatmapID,
# Source, Tags -- readable in a text editor, invisible while playing) and
# *play-visible decoration* (backgrounds, kiai, combo colours). Everything a
# mapper authored is left exactly as written.
#
# Timing points are the case that fixes the line. On the measured pack the
# generated entries had 3 uninherited lines and <=15 total against the humans'
# 1 and >=28 -- a perfect separator for anyone counting lines. It is deliberately
# NOT scrubbed: barlines are not rendered in std gameplay, so it cannot help a
# player who is actually playing, and rewriting the beat grid would unsnap the
# objects hanging off it. A leak that only rewards cheating beats a "fix" that
# corrupts the maps under test.
#
# Editor state and a handful of [General] keys are written by whichever tool
# produced the map, so they are a provenance fingerprint even though no player
# ever sees them. Measured on the 2026-08-22 pack: every generated entry carried
# `Bookmarks:-330001`, `TimelineZoom: 2.20004`, `GridSize: 8`, `SampleSet: All`
# and an `OverlayPosition` line; every human entry carried real bookmarks,
# `GridSize: 4`, `SampleSet: Normal` and no OverlayPosition. That split the pack
# perfectly into {A,B,F} and {C,D,E} -- a 6/6 score from a text editor, without
# playing a note. Normalising to one constant set makes the sections uniform.
NEUTRAL_EDITOR = {
    "Bookmarks": "",
    "DistanceSpacing": "1.0",
    "BeatDivisor": "4",
    "GridSize": "4",
    "TimelineZoom": "1",
}
NEUTRAL_GENERAL = {
    "SampleSet": "Normal",
    "StackLeniency": "0.7",
    "LetterboxInBreaks": "0",
    "WidescreenStoryboard": "1",
    "Countdown": "0",
    "AudioLeadIn": "0",
    # A real timestamp, not -1: the gate rejects an unset preview, and every
    # entry sharing one point in the song is what makes it non-identifying.
    "PreviewTime": "15984",
}
# Present in some tools' output and absent in others', so their presence alone
# is a tell; dropped from every entry rather than normalised to a value.
# `Source` and the Beatmap*ID pair are ranked-map metadata a generated map never
# has, and `Combo<n>` lines are a custom colour palette only real mappers set.
DROPPED_KEYS = (
    "OverlayPosition",
    "EpilepsyWarning",
    "SamplesMatchPlaybackRate",
    "SpecialStyle",
    "Source",
    "BeatmapID",
    "BeatmapSetID",
)

# The difficulty constants are the subtlest tell: a generated map emits whichever
# fixed values the sampler used while human maps carry hand-tuned ones, so on the
# measured pack AI was a constant (HP 5 / OD 8) that no human entry shared.
#
# Only the judgement/visual knobs are normalised. `SliderMultiplier` and
# `SliderTickRate` are deliberately NOT in here: slider duration is
# `pathLength / (SliderMultiplier * 100 * SV) * beatLength`, so rewriting a human
# map authored at 1.7 down to 1.4 stretches every slider ~21% in time and makes
# it overrun the objects after it. That would corrupt the human entries only, and
# bias the test the wrong way -- a broken-feeling human map reads as "AI".
NEUTRAL_DIFFICULTY = {
    "HPDrainRate": "5",
    "CircleSize": "4",
    "OverallDifficulty": "8",
    "ApproachRate": "9",
}


def _anonymise(text: str, label: str) -> str:
    """Rewrite a beatmap's identifying metadata to a bare label.

    Version, Creator and Tags all leak origin -- upstream records its whole
    generation config in Tags, which would give the answer away immediately.
    Editor state and tool-dependent [General] keys leak it just as reliably
    without ever being displayed, so they are normalised too (see NEUTRAL_EDITOR).
    """
    replacements = {"Version": label, "Creator": "blindtest", "Tags": ""}
    replacements.update(NEUTRAL_EDITOR)
    replacements.update(NEUTRAL_GENERAL)
    replacements.update(NEUTRAL_DIFFICULTY)
    lines = []
    for line in _clear_kiai(_strip_colours(_strip_events(text))).splitlines():
        key, sep, _ = line.partition(":")
        if sep and key in DROPPED_KEYS:
            continue
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
