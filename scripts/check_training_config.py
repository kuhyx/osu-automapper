#!/usr/bin/env python3
"""Gate the LoRA training config against the traps that break a run.

Every rule here corresponds to a failure actually hit while getting training to
run, all of which either crash minutes in or waste a whole run. The config lives
in the upstream clone, which is third-party and not tracked here, so this checks
the mirrored copy in ``docs/`` and, when present, the live file.

Exit codes: 0 all rules hold, 1 a rule is violated, 2 the config is unreadable.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIRROR = REPO_ROOT / "docs" / "lora_kuhy.yaml"
LIVE = Path.home() / "Mapperatorinator" / "configs" / "train" / "lora_kuhy.yaml"


def check(text: str) -> list[str]:
    """Return a list of violated rules for ``text``."""
    problems: list[str] = []
    if "attn_implementation: 'sdpa'" not in text:
        problems.append(
            "attn_implementation must be 'sdpa': flash-attn is absent from upstream's "
            "requirements.txt (Docker-only) and training dies at model construction."
        )
    if "log_with: 'wandb'" not in text:
        problems.append(
            "log_with must be 'wandb' (with mode: offline): maybe_save_checkpoint() calls "
            "get_tracker('wandb') unconditionally and accelerate raises otherwise, killing "
            "the run at the first checkpoint."
        )
    if "mode: offline" not in text:
        problems.append("logging.mode must be 'offline': no W&B account, no network writes.")
    if 'dataset_type: "mmrs"' in text:
        problems.append(
            "dataset_type must not be 'mmrs': that format needs the Mapperator .NET app and "
            "an osu! OAuth token this project does not hold. Use 'web'."
        )
    if "every_steps: 5000" in text:
        problems.append(
            "checkpoint.every_steps: 5000 would never fire in a short run, leaving nothing on disk."
        )
    return problems


def main() -> int:
    """Check every available copy of the training config."""
    targets = [p for p in (MIRROR, LIVE) if p.exists()]
    if not targets:
        print(f"error: no training config found at {MIRROR} or {LIVE}", file=sys.stderr)
        return 2

    failed = False
    for path in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot read {path}: {exc}", file=sys.stderr)
            return 2
        problems = check(text)
        if problems:
            failed = True
            print(f"FAIL {path}")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"OK   {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
