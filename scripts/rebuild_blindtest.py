"""Rebuild the MEGALOVANIA blind-test pack from its staged sources.

Exists so the pack kuhy actually plays is reproducible rather than a one-off:
the first pack was rebuilt three times while four separate leaks were closed,
and each rebuild was a hand-written scratch file.

The seed is pinned. Seed 1 was chosen because its assignment both differs from
the compromised 15:39 pack's (whose answer leaked 19 ways, so reusing its A-F
mapping would carry that knowledge straight over) and interleaves the two
groups rather than clustering them.

Verify whatever this writes before playing it:

    python3 scripts/check_blindtest_leaks.py <pack>.osz <key>.json
    ./run.sh check '<extracted>/blindtest [A].osu'   # ... and B-F
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from osu_automapper.blindtest.harness import build_blindtest, pack_blindtest

HUMAN = ("human_Extra.osu", "human_Insane.osu", "human_Hard.osu")
GENERATED = ("ai_d3.8.osu", "ai_d5.5.osu", "ai_d4.6.osu")
SEED = 1


def main() -> int:
    """Pack the staged maps and report where they landed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path, help="directory holding the staged .osu sources")
    parser.add_argument("--audio", type=Path, required=True, help="the shared song")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path.home() / "osu-automapper_data" / "blindtest",
    )
    args = parser.parse_args()

    missing = [n for n in HUMAN + GENERATED if not (args.stage / n).is_file()]
    if missing:
        print(f"error: missing sources in {args.stage}: {missing}", file=sys.stderr)
        return 2
    if not args.audio.is_file():
        print(f"error: no audio at {args.audio}", file=sys.stderr)
        return 2

    test = build_blindtest(
        real=[args.stage / n for n in HUMAN],
        generated=[args.stage / n for n in GENERATED],
        seed=args.seed,
    )
    archive, key_path = pack_blindtest(test, args.destination, audio=args.audio)
    print(f"pack: {archive}")
    print(f"key:  {key_path}")
    print("\nVerify before playing:")
    print(f"  python3 scripts/check_blindtest_leaks.py {archive} {key_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
