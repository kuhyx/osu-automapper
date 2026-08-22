#!/bin/bash

# ============================================================================
# Generate one map per LoRA checkpoint and gate it, so a training run produces
# measured results rather than a pile of untested adapters.
#
# Seed and difficulty are held constant across checkpoints on purpose: that is
# what makes the object/slider counts comparable between them and against the
# base model.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
readonly SCRIPT_DIR REPO_DIR
readonly DATA_ROOT="${OSU_AUTOMAPPER_DATA:-$HOME/osu-automapper_data}"
readonly SONG="${SONG:-$DATA_ROOT/songs/night_of_knights.mp3}"
readonly SEED="${SEED:-555}"
readonly DIFFICULTY="${DIFFICULTY:-5.0}"
readonly RESULTS="$DATA_ROOT/lora/results.tsv"

usage() {
    echo "Usage: $(basename "$0") [--help]"
    echo "Evaluates every LoRA checkpoint under the newest training run."
    echo "Env: SONG, SEED, DIFFICULTY, OSU_AUTOMAPPER_DATA"
    exit 0
}

# Count hit objects by type so a checkpoint's *style* is visible, not just its
# object count -- count alone barely moves while ratios do.
summarise_map() {
    local osu="$1"
    python3 - "$osu" <<'PY'
import sys
from pathlib import Path

body = Path(sys.argv[1]).read_text(errors="replace").split("[HitObjects]")[1]
rows = [line.split(",") for line in body.strip().splitlines() if line.strip()]
types = [int(r[3]) for r in rows if len(r) > 3]
circles = sum(1 for t in types if t & 1)
sliders = sum(1 for t in types if t & 2)
print(f"{len(rows)}\t{circles}\t{sliders}")
PY
}

evaluate_one() {
    local lora_dir="$1" label="$2" out_dir
    out_dir="$DATA_ROOT/out/eval_$label"

    if ! "$REPO_DIR/run.sh" generate "$SONG" "$out_dir" \
        --difficulty "$DIFFICULTY" --seed "$SEED" \
        --title "Night of Knights" --artist "beatMARIO" --preview-time 1598 \
        ${lora_dir:+--lora-path "$lora_dir"} >/dev/null 2>&1; then
        echo "  $label: generation FAILED" >&2
        return 0
    fi

    local osz osu extracted="$out_dir/extracted"
    osz="$(find "$out_dir" -maxdepth 1 -name '*.osz' -print -quit)"
    [[ -n "$osz" ]] || { echo "  $label: no .osz produced" >&2; return 0; }
    rm -rf "$extracted"
    unzip -o -q "$osz" -d "$extracted"
    osu="$(find "$extracted" -name '*.osu' -print -quit)"

    local counts stars verdict
    counts="$(summarise_map "$osu")"
    stars="$("$REPO_DIR/run.sh" check "$osu" --target-difficulty "$DIFFICULTY" 2>/dev/null \
        | sed -n 's/.*star_rating: \([0-9.]*\)\*.*/\1/p')"
    if "$REPO_DIR/run.sh" check "$osu" --target-difficulty "$DIFFICULTY" >/dev/null 2>&1; then
        verdict="pass"
    else
        verdict="FAIL"
    fi

    printf '%s\t%s\t%s\t%s\n' "$label" "$counts" "${stars:-?}" "$verdict" >> "$RESULTS"
    echo "  $label: objs/circles/sliders $counts | ${stars:-?}* | $verdict"
}

main() {
    local run_dir
    run_dir="$(find "$HOME/Mapperatorinator/logs" -mindepth 2 -maxdepth 2 -type d \
        -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"
    [[ -n "$run_dir" ]] || { echo "Error: no training run found" >&2; exit 1; }

    mkdir -p "$(dirname "$RESULTS")"
    printf 'label\tobjects\tcircles\tsliders\tstars\tverdict\n' > "$RESULTS"

    echo "Run: $run_dir"
    echo "Baseline (no LoRA), then each checkpoint; seed $SEED, difficulty $DIFFICULTY"
    evaluate_one "" "base"

    local ckpt
    while IFS= read -r ckpt; do
        [[ -d "$ckpt/lora" ]] || continue
        evaluate_one "$ckpt/lora" "$(basename "$ckpt")"
    done < <(find "$run_dir/checkpoints" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort -V)

    echo
    echo "Results: $RESULTS"
    column -t -s$'\t' "$RESULTS"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) usage ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

main
