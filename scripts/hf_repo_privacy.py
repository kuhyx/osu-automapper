"""Report whether a Hugging Face repo is private, for upload_corpus.sh to gate on.

The `hf` CLI can create a repo but cannot read its visibility back (0.36.2 has
only `repo create` and `repo tag`), and `--private` is honoured only when the
invoking call is the one that creates the repo. So an existing public repo would
silently accept a `--private` upload and stay public. This asks the Hub API what
the repo actually is.

Runs against the upstream sibling's venv, which is where huggingface_hub lives;
it deliberately does not live in the osu_automapper package (see the header of
upload_corpus.sh).

Prints "true" or "false" and exits 0 when the repo exists; exits 2 when it does
not, and 1 on any API failure. Silence is never treated as private.
"""

from __future__ import annotations

import argparse
import sys

from huggingface_hub import HfApi
from huggingface_hub.utils import RepositoryNotFoundError


def main() -> int:
    """Print the repo's private flag, or fail loudly."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_id", help="e.g. kuhy/osu-mapsets-lazer")
    parser.add_argument("--repo-type", default="dataset")
    args = parser.parse_args()

    try:
        info = HfApi().repo_info(args.repo_id, repo_type=args.repo_type)
    except RepositoryNotFoundError:
        print(f"repo not found: {args.repo_id}", file=sys.stderr)
        return 2
    except OSError as exc:  # network/auth failures must not read as "private"
        print(f"error querying {args.repo_id}: {exc}", file=sys.stderr)
        return 1

    # `private` is Optional[bool] upstream; anything but an explicit True is
    # reported as not-private so the caller refuses to upload.
    print("true" if info.private is True else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
