"""Report every header field that separates the AI entries from the human ones.

The gate catches broken maps, not leaks. Four separate leaks each split a real
pack perfectly (see docs/runbook.md), and every one was found by diffing rather
than by reasoning about which fields might leak -- the first fix looked complete
and this check immediately found seven more separating keys. So it exists to be
re-run after every anonymiser change and whenever a new source of maps is added.

A "leak" here is a header key whose values never overlap between the two groups:
if every AI entry says one thing and no human entry ever says it, that key alone
answers the question the blind test is asking.

Not every separating key is a bug. `SliderMultiplier` is expected to appear --
normalising it would stretch human sliders and corrupt the entries under test,
so it is a deliberate, documented exception rather than an oversight.

Usage:
    python3 scripts/check_blindtest_leaks.py <pack>.osz <key>.json

Exits 1 when an unexpected separating key is found, 0 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

# Separating keys that are deliberately left authored; see docs/runbook.md.
# SliderMultiplier stays because normalising it stretches human sliders and
# corrupts the entries under test; Version is the label itself; AudioFilename is
# rewritten to the packed audio at build time. SliderTickRate is NOT here: it was
# uniform across the measured pack, so if it ever starts separating the groups
# that is news and should be flagged rather than waved through.
ALLOWED = frozenset({"SliderMultiplier", "AudioFilename", "Version"})


def header_fields(text: str) -> dict[str, str]:
    """Every ``key:value`` line above ``[HitObjects]``."""
    head = text.split("[HitObjects]")[0]
    fields: dict[str, str] = {}
    for line in head.splitlines():
        if line.startswith("//"):
            continue
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def section(text: str, name: str) -> list[str]:
    """Return the non-comment, non-blank body lines of one ``[Section]``."""
    _, marker, tail = text.partition(f"[{name}]")
    if not marker:
        return []
    body = tail.partition("\n[")[0]
    return [ln for ln in body.splitlines() if ln.strip() and not ln.startswith("//")]


def counted_fields(text: str) -> dict[str, str]:
    """Header keys plus the two leaks that are not ``key:value`` lines at all.

    ``[Events]`` rows (`0,0,"BG.jpg",0,0`) and ``[TimingPoints]`` rows
    (`0,500,4,2,0,60,1,1`) contain no colon, so a key:value scan skips them
    entirely -- which would silently miss the first two leaks ever found. They
    are folded in as synthetic count fields so the same overlap test covers them.
    """
    fields = header_fields(text)
    fields["#events"] = str(len(section(text, "Events")))
    kiai = 0
    for row in section(text, "TimingPoints"):
        parts = row.split(",")
        if len(parts) >= 8 and parts[7].lstrip("-").isdigit() and int(parts[7]) & 1:
            kiai += 1
    fields["#kiai"] = str(kiai)
    return fields


def load_groups(archive: Path, key_path: Path) -> dict[bool, list[dict[str, str]]]:
    """Split the pack's entries into generated and human header maps."""
    answer = {e["label"]: e["generated"] for e in json.loads(key_path.read_text())["entries"]}
    groups: dict[bool, list[dict[str, str]]] = {True: [], False: []}
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            if not name.endswith(".osu"):
                continue
            # Entries are packed as "blindtest [A].osu".
            label = name.split("[")[-1].split("]")[0]
            if label in answer:
                text = zf.read(name).decode("utf-8-sig", errors="replace")
                groups[answer[label]].append(counted_fields(text))
    return groups


def main() -> int:
    """Print every separating key, and fail on the unexpected ones."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="the .osz pack")
    parser.add_argument("key", type=Path, help="the saved <ts>.json key")
    args = parser.parse_args()

    groups = load_groups(args.archive, args.key)
    if not groups[True] or not groups[False]:
        print("error: pack needs both generated and human entries", file=sys.stderr)
        return 2

    ai_keys = {k for d in groups[True] for k in d}
    human_keys = {k for d in groups[False] for k in d}

    problems: list[str] = []
    for key in sorted(ai_keys ^ human_keys):
        if key not in ALLOWED:
            problems.append(f"key present in only one group: {key}")

    for key in sorted(ai_keys & human_keys):
        ai_values = {d.get(key) for d in groups[True]}
        human_values = {d.get(key) for d in groups[False]}
        if not (ai_values & human_values):
            line = f"{key}: ai={sorted(ai_values)} human={sorted(human_values)}"
            if key in ALLOWED:
                print(f"  (allowed) {line}")
            else:
                problems.append(f"values never overlap: {line}")

    if problems:
        print(f"\n{len(problems)} leak(s):", file=sys.stderr)
        for problem in problems:
            print(f"  LEAK {problem}", file=sys.stderr)
        return 1
    print("\nno unexpected separating keys")
    return 0


if __name__ == "__main__":
    sys.exit(main())
