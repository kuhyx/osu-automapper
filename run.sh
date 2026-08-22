#!/bin/bash

# ============================================================================
# Dispatcher for osu-automapper. Sets HF_HOME so the checkpoint cache stays in
# the data root (an export inside install.sh would die with that script).
# ============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR
readonly DATA_ROOT="${OSU_AUTOMAPPER_DATA:-$HOME/osu-automapper_data}"

export HF_HOME="$DATA_ROOT/hf"

if [[ ! -x "$REPO_DIR/.venv/bin/python" ]]; then
    echo "Error: venv missing. Run ./install.sh first." >&2
    exit 2
fi

exec "$REPO_DIR/.venv/bin/python" -m osu_automapper "$@"
