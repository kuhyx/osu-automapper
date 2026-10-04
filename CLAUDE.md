## Commands

- run: `./run.sh --help`
- test: `.venv/bin/pytest -q`
- test-changed: `scripts/test_changed.sh`
- lint: `.venv/bin/ruff check .`
- coverage: `.venv/bin/pytest -q --cov --cov-branch --cov-report=xml`
- coverage-gaps: `coverage-gaps coverage.xml`

Two venvs: use this repo's `.venv` (`./install.sh`). Never the upstream `~/vendor/Mapperatorinator/.venv` (torch, py3.10; see docs/DOCS-runbook.md).
