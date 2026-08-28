#!/bin/bash

# ============================================================================
# osu-automapper installer: upstream (torch, py3.10) and our own (py3.14) venv.
# Idempotent -- re-running is a no-op.
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_NAME REPO_DIR
readonly UPSTREAM_URL="https://github.com/OliBomby/Mapperatorinator.git"
readonly UPSTREAM_DIR="${MAPPERATORINATOR_HOME:-$HOME/Mapperatorinator}"
readonly DATA_ROOT="${OSU_AUTOMAPPER_DATA:-$HOME/osu-automapper_data}"
readonly UPSTREAM_PYTHON="3.10"
# Our own code runs exactly one Python and it is the newest. UPSTREAM_PYTHON
# stays 3.10 because Mapperatorinator is OliBomby's repo, not ours, and its
# torch pins are what fix that number.
readonly OUR_PYTHON="3.14"
# CUDA 13.0 wheels: the 3090 (driver 610.x) runs these, and pinning the index
# keeps pip from silently resolving a CPU-only build from PyPI.
readonly TORCH_INDEX="https://download.pytorch.org/whl/cu130"

usage() {
    echo "Usage: $SCRIPT_NAME [--help]"
    echo "Installs both virtualenvs, clones upstream and prepares the data root."
    exit 0
}

ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        return
    fi
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
}

clone_upstream() {
    if [[ -d "$UPSTREAM_DIR/.git" ]]; then
        echo "Upstream already cloned: $UPSTREAM_DIR"
        return
    fi
    echo "Cloning Mapperatorinator..."
    git clone --depth 1 "$UPSTREAM_URL" "$UPSTREAM_DIR"
}

install_upstream_venv() {
    echo "Preparing upstream venv (python $UPSTREAM_PYTHON)..."
    uv python install "$UPSTREAM_PYTHON"
    [[ -d "$UPSTREAM_DIR/.venv" ]] || uv venv --python "$UPSTREAM_PYTHON" "$UPSTREAM_DIR/.venv"

    # torch FIRST, from the CUDA index: requirements.txt leaves it unpinned, so
    # installing it afterwards can replace the CUDA build with a CPU one.
    VIRTUAL_ENV="$UPSTREAM_DIR/.venv" uv pip install --quiet torch --index-url "$TORCH_INDEX"
    # torchaudio is imported by osuT5/model/spectrogram.py but is MISSING from
    # upstream's requirements.txt (it only ships in their Dockerfile).
    VIRTUAL_ENV="$UPSTREAM_DIR/.venv" uv pip install --quiet torchaudio --index-url "$TORCH_INDEX"
    VIRTUAL_ENV="$UPSTREAM_DIR/.venv" uv pip install --quiet -r "$UPSTREAM_DIR/requirements.txt"
    # requirements.txt pins torchcodec==0.10.0, which is ABI-broken against
    # current torch (undefined symbol c10::MessageLogger) and has no build for
    # FFmpeg 9 as shipped by Arch. Only the dataset/training path uses it, so
    # inference hides the problem until you try to train. Upgrade last, so it
    # wins over the pin.
    VIRTUAL_ENV="$UPSTREAM_DIR/.venv" uv pip install --quiet \
        "torchcodec>=0.16.0" --index-url "$TORCH_INDEX"
}

install_our_venv() {
    echo "Preparing osu-automapper venv (python $OUR_PYTHON)..."
    uv python install "$OUR_PYTHON"
    [[ -d "$REPO_DIR/.venv" ]] || uv venv --python "$OUR_PYTHON" "$REPO_DIR/.venv"
    VIRTUAL_ENV="$REPO_DIR/.venv" uv pip install --quiet -e "${REPO_DIR}[dev]"
}

prepare_data_root() {
    echo "Preparing data root: $DATA_ROOT"
    mkdir -p "$DATA_ROOT"/{hf,out,corpus,songs,blindtest}
}

# Verify CUDA survived the requirements install rather than assuming it did.
probe_environment() {
    echo "--- environment probe ---"
    HF_HOME="$DATA_ROOT/hf" "$UPSTREAM_DIR/.venv/bin/python" - <<'PY'
import torch  # must precede torchcodec: it puts libtorch on the loader path
import torchaudio
import torchcodec

print(f"torch      {torch.__version__}")
print(f"torchaudio {torchaudio.__version__}")
print(f"torchcodec {torchcodec.__version__}")
print(f"cuda       {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"device     {torch.cuda.get_device_name(0)}")
print(f"sdpa       {torch.backends.cuda.flash_sdp_enabled()}")
PY
    echo "--- end probe ---"
}

main() {
    ensure_uv
    clone_upstream
    install_upstream_venv
    install_our_venv
    prepare_data_root
    probe_environment
    echo "Done. Try: ./run.sh check <path.osu> --target-difficulty 5.5"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) usage ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

main
