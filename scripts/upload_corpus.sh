#!/bin/bash

# ============================================================================
# Publish the webdataset corpus to a PRIVATE Hugging Face dataset repo, which
# is the only way the upstream `web` route can read it: `list_repo_files` runs
# unconditionally before `load_dataset` and always hits the Hub API, so a local
# path cannot be substituted (see docs/corpus-options.md).
#
# This lives in scripts/ rather than in the package on purpose.
# tests/test_no_upload_boundary.py forbids the word "upload" anywhere under
# osu_automapper/, because that package must contain no path that can submit a
# beatmap to osu!. Uploading a training corpus to Hugging Face is a different
# act entirely, but the boundary is kept blunt and structural rather than
# clever, so the corpus uploader stays outside the package it protects.
#
# Privacy is verified by reading it back off the Hub API before a single byte
# of audio is sent -- not by trusting the --private flag, which only applies
# when the invoking command is the one that creates the repo.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly DATA_ROOT="${OSU_AUTOMAPPER_DATA:-$HOME/osu-automapper_data}"
readonly CORPUS_DIR="$DATA_ROOT/corpus"
readonly SHARD_DIR="$CORPUS_DIR/compressed"
# Neither the `hf` CLI nor huggingface_hub is on PATH or in this repo's venv;
# both ship in the upstream sibling's venv, which is read, never modified.
readonly HF="${HF_CLI:-$HOME/Mapperatorinator/.venv/bin/hf}"
readonly HF_PYTHON="${HF_PYTHON:-$HOME/Mapperatorinator/.venv/bin/python}"

REPO_ID="${REPO_ID:-kuhy/osu-mapsets-lazer}"
DRY_RUN=0

usage() {
    echo "Usage: $(basename "$0") [--repo-id ID] [--dry-run] [--help]"
    echo "Uploads $SHARD_DIR to a private HF dataset repo."
    echo "Env: REPO_ID, HF_CLI, OSU_AUTOMAPPER_DATA"
    exit 0
}

validate_requirements() {
    if [[ ! -x "$HF" ]]; then
        echo "Error: hf CLI not found at $HF" >&2
        echo "It lives in the upstream venv; set HF_CLI to override." >&2
        exit 1
    fi
    if [[ ! -d "$SHARD_DIR" ]]; then
        echo "Error: no corpus at $SHARD_DIR -- run './run.sh corpus' first" >&2
        exit 1
    fi
    local shards
    shards="$(find "$SHARD_DIR" -maxdepth 1 -name '*.tar' | wc -l)"
    if [[ "$shards" -eq 0 ]]; then
        echo "Error: no .tar shards in $SHARD_DIR" >&2
        exit 1
    fi
    if [[ ! -f "$CORPUS_DIR/manifest.json" ]]; then
        echo "Error: $CORPUS_DIR/manifest.json missing -- the corpus build did" >&2
        echo "not finish, so the shards are not known to be verified." >&2
        exit 1
    fi
    echo "Found $shards shard(s) in $SHARD_DIR"
}

# Create the repo if absent, then read privacy back off the API. `--private` is
# honoured only when this call is the one that creates the repo, so an existing
# public repo would accept the upload and stay public -- hence the read-back.
ensure_private_repo() {
    echo "Ensuring private dataset repo $REPO_ID ..."
    "$HF" repo create "$REPO_ID" --repo-type dataset --private --exist-ok

    local private
    private="$("$HF_PYTHON" "$SCRIPT_DIR/hf_repo_privacy.py" "$REPO_ID")"
    if [[ "$private" != "true" ]]; then
        echo "Error: $REPO_ID reports private=$private -- refusing to upload." >&2
        echo "Make it private on the Hub, then re-run." >&2
        exit 1
    fi
    echo "Verified: $REPO_ID is private"
}

main() {
    validate_requirements
    ensure_private_repo

    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "Dry run: would upload $SHARD_DIR and manifest.json to $REPO_ID"
        exit 0
    fi

    echo "Uploading shards to $REPO_ID ..."
    "$HF" upload "$REPO_ID" "$SHARD_DIR" data --repo-type dataset

    # The manifest records what was built (usable mapsets, unmatched audio,
    # shard verification) and lives one level above the shards, so it is not
    # swept up by the directory upload above.
    echo "Uploading manifest ..."
    "$HF" upload "$REPO_ID" "$CORPUS_DIR/manifest.json" manifest.json \
        --repo-type dataset

    echo "Done. Point a training config at: $REPO_ID"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --repo-id)
            REPO_ID="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

readonly REPO_ID DRY_RUN

main "$@"
