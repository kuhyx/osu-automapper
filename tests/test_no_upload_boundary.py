"""The no-upload boundary, enforced as a test rather than a promise.

The osu! Ranking Criteria prohibits generative tooling in beatmap creation, and
osu! staff have permanently removed a ranked set after determining AI assistance
was used (November 2025; no specific tool was named). So the boundary is
structural: this package must contain no way to submit anything to osu!, and no
credentials to do it with. See docs/ranking-criteria.md.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "osu_automapper"

# Anything that could put a beatmap on osu!'s servers, or authenticate to do so.
FORBIDDEN_PATTERNS = (
    r"osu\.ppy\.sh",
    r"bm-submit",
    r"beatmapsubmission",
    r"\bupload\b",
    r"\bsubmit\b",
    r"client_secret",
    r"OSU_API",
)

# Network clients have no business in a local gate.
FORBIDDEN_IMPORTS = ("requests", "httpx", "urllib.request", "aiohttp")


def _source_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def test_package_has_no_upload_or_submission_path() -> None:
    offenders: list[str] = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                offenders.append(f"{path.name}: {pattern}")
    assert not offenders, f"upload/credential surface found: {offenders}"


def test_package_imports_no_http_client() -> None:
    offenders: list[str] = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for module in FORBIDDEN_IMPORTS:
            if re.search(rf"^\s*(import|from)\s+{re.escape(module)}\b", text, flags=re.MULTILINE):
                offenders.append(f"{path.name}: {module}")
    assert not offenders, f"network client imported: {offenders}"


def test_the_gate_is_not_named_rankable() -> None:
    """A green gate must never read as ranking eligibility."""
    report = (PACKAGE_ROOT / "report.py").read_text(encoding="utf-8")
    assert "technically_rankable" in report
    assert not re.search(r"\bdef is_rankable\b", report)
