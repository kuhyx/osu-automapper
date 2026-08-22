"""Allow ``python -m osu_automapper``."""

from __future__ import annotations

import sys

from osu_automapper.cli import main

sys.exit(main())
