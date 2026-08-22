#!/bin/bash

# ============================================================================
# The whole blind test in one command: import the pack into lazer, then ask
# one plain question per difficulty and print the score.
#
# Exists because the two-step version (play, then hand-write
# "A=ai B=human ...") put the answer format in the user's way. Here the only
# thing typed is a or h, six times, after playing.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
readonly SCRIPT_DIR REPO_DIR
readonly DATA_ROOT="${OSU_AUTOMAPPER_DATA:-$HOME/osu-automapper_data}"
readonly BLIND_DIR="$DATA_ROOT/blindtest"

PACK=""
KEY=""

usage() {
    echo "Usage: $(basename "$0") [PACK.osz]"
    echo "Plays the newest verified blind-test pack unless one is named."
    exit 0
}

# Newest pack, and the key sharing its timestamp.
find_newest_pack() {
    PACK="$(find "$BLIND_DIR" -maxdepth 1 -name 'blindtest-*.osz' -printf '%T@ %p\n' |
        sort -rn | head -1 | cut -d' ' -f2-)"
    if [[ -z "$PACK" ]]; then
        echo "Error: no blindtest-*.osz in $BLIND_DIR" >&2
        exit 1
    fi
}

resolve_key() {
    local stamp
    stamp="$(basename "$PACK" .osz)"
    stamp="${stamp#blindtest-}"
    KEY="$BLIND_DIR/$stamp.json"
    if [[ ! -f "$KEY" ]]; then
        echo "Error: no key for $(basename "$PACK") at $KEY" >&2
        exit 1
    fi
}

# A pack whose answer is readable in a text editor is worse than no test, so
# this refuses to run one rather than reporting a score nobody can trust.
verify_no_leaks() {
    if ! "$REPO_DIR/.venv/bin/python" "$SCRIPT_DIR/check_blindtest_leaks.py" \
        "$PACK" "$KEY" >/dev/null 2>&1; then
        echo "Error: $(basename "$PACK") leaks its answer -- refusing to run it." >&2
        echo "Run scripts/check_blindtest_leaks.py on it to see how." >&2
        exit 1
    fi
}


# One question per map, in words rather than an argument format to fill in.
ask_one() {
    local label="$1" answer
    while true; do
        read -r -p "  $label - human or ai?  [h/a] " answer || true
        case "${answer,,}" in
            h|human) verdict[$label]="human"; return ;;
            a|ai)    verdict[$label]="ai";    return ;;
            *) echo "        type h for human or a for ai" ;;
        esac
    done
}

ask_each() {
    echo
    echo "For each one: was it made by a HUMAN or by the AI?"
    for label in A B C D E F; do
        ask_one "$label"
    done
}

# Answers are only scored once they have all been seen together, so a later
# map can still correct an earlier impression.
review_and_revise() {
    while true; do
        echo
        echo "Your answers:"
        for label in A B C D E F; do
            printf "  %s = %s\n" "$label" "${verdict[$label]}"
        done
        local change
        read -r -p "Change any? [letter to change, or Enter to score] " change || true
        [[ -z "$change" ]] && return
        change="${change^^}"
        if [[ "$change" =~ ^[A-F]$ ]]; then
            ask_one "$change"
        else
            echo "  type a letter A-F, or press Enter to score"
        fi
    done
}

ask_all() {
    # Nothing is asked until every map has been played. kuhy scored 5/6 on the
    # first run and only recognised A as human once B gave them a reference
    # point -- but A's answer was already locked in, because the prompts were
    # available from the start. An early answer is a worse measurement than a
    # slow one, so this waits, and then lets every answer be revised before any
    # of them is scored.
    echo
    echo "Play all six difficulties (A-F) in lazer first."
    echo "Answering before you have played them all makes the early ones"
    echo "guesses -- there is nothing to compare them against yet."
    echo
    local ready
    while true; do
        read -r -p "Played all six? [y] " ready || true
        case "${ready,,}" in
            y|yes) break ;;
            *) echo "  take your time -- press y when all six are played" ;;
        esac
    done

    declare -A verdict
    ask_each
    review_and_revise

    local guesses=()
    for label in A B C D E F; do
        guesses+=("$label=${verdict[$label]}")
    done
    echo
    "$REPO_DIR/run.sh" blindtest-score "$KEY" "${guesses[@]}"

}

main() {
    if [[ -n "${1:-}" ]]; then
        PACK="$1"
    else
        find_newest_pack
    fi
    resolve_key
    verify_no_leaks

    echo "Pack: $(basename "$PACK")"
    echo "Opening it in osu!lazer ..."
    # Lazer imports the .osz and keeps running; detach so this script can go on
    # to ask the questions while the game is up.
    osu-lazer "$PACK" >/dev/null 2>&1 &
    ask_all
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
fi

main "$@"
