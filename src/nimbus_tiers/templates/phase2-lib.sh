#!/usr/bin/env bash
# phase2-lib.sh — pure helper functions for phase2.sh.
#
# Every function here is parameter-in/stdout-out (or exit-code-out) with no
# dependence on phase2.sh globals, so each is unit-testable in isolation:
#
#   bash -c 'source phase2-lib.sh; _strip_md_path "- \`src/Foo.java\` (new)"'
#
# phase2.sh sources this file from its own directory and refuses to run
# without it; the two files are scaffolded together by nimbus-tiers and
# updated together by nimbus-update. Behavior notes that used to live next
# to the extracted code in phase2.sh have moved here with their functions.

# ── process / step bookkeeping ────────────────────────────────────────────────

get_proc_start_time() {
    # Linux procfs start time (clock ticks since boot), field 22 in /proc/<pid>/stat.
    # Empty output means unavailable (non-Linux, vanished process, or inaccessible procfs).
    local pid="$1"
    [ -r "/proc/${pid}/stat" ] || return 1
    awk '{print $22}' "/proc/${pid}/stat" 2>/dev/null || return 1
}

nimbus_next_step() {
    # Lowest step number not recorded DONE in CompletedSteps.md (in $PWD).
    python3 -c "
import re, os
done = set()
if os.path.exists('CompletedSteps.md'):
    with open('CompletedSteps.md') as f:
        for line in f:
            m = re.search(r'Step (\d+): DONE', line)
            if m:
                done.add(int(m.group(1)))
n = 1
while n in done:
    n += 1
print(n)
"
}

# ── step-file parsing ─────────────────────────────────────────────────────────

nimbus_planned_entries() {
    # Print the raw "- path" list items from the "## Files to change" section
    # of a step file, one per line. Section ends at the next "##" heading.
    awk '/^## Files to change/{found=1; next} found && /^##/{exit} found && /^- /{print}' "$1"
}

# Parse a path entry from a "## Files to change" list item. Strips the leading
# "- " marker, any remaining leading whitespace (handles the double-space typo
# '- ⎵⎵src/...'), a trailing "(annotation)" suffix, and one layer of `/"/'
# wrapping.
_strip_md_path() {
    local p="${1#- }"
    # Strip any leading whitespace left after removing the "- " prefix.
    # Without this, '- ⎵⎵src/Foo.java' (double space) leaves ' src/Foo.java'
    # which the embedded-space guard would silently skip rather than check.
    p="${p#"${p%%[![:space:]]*}"}"
    # Strip trailing annotation: shortest-match " (*" removes only the trailing
    # " (note)" suffix. Using % not %% avoids truncating at the first ( in a
    # directory component (e.g. com/example(v1)/Foo.java is left intact).
    p="${p% (*}"
    p="${p%"${p##*[![:space:]]}"}"
    p="${p#\`}"; p="${p%\`}"
    p="${p#\"}"; p="${p%\"}"
    p="${p#\'}"; p="${p%\'}"
    printf '%s' "$p"
}

# ── malformed-path guards ─────────────────────────────────────────────────────

# Extended regex matching a malformed JVM source path. Java/Kotlin/Scala/Groovy
# package names map to directories by replacing each `.` with `/`, so a
# legitimate source *directory* never contains a `.` or `()`. Two forms of the
# canonical local-model layout bug are caught:
#   1. A dotted directory component under a source root, e.g.
#      `src/main/java/com.example/Foo.java` — the first alternative matches a
#      `.`-bearing component that is FOLLOWED BY A SLASH (so it is a directory).
#      The final filename (`Foo.java`, no trailing slash) is therefore never
#      flagged, and a legitimately dotted filename like `Foo.Bar.java` is safe.
#   2. A parenthesised source root, e.g. `src/main/java(com.example.app)/...` —
#      the second alternative matches the lang dir immediately followed by `(`.
# Match against RAW paths (do not append a trailing slash, which would make the
# final filename look like a directory and false-positive every valid path).
_JVM_DOTTED_DIR_RE='(src/(main|test)/(java|kotlin|scala|groovy)/([^/]*/)*[^/]*\.[^/]*/)|(src/(main|test)/(java|kotlin|scala|groovy)\()'

nimbus_is_malformed_jvm_path() {
    printf '%s' "$1" | grep -qE "$_JVM_DOTTED_DIR_RE"
}

# ── build-file guards ─────────────────────────────────────────────────────────

# Known coordinate-corruption class: a local model regenerating pom.xml /
# build.gradle can mangle well-known coordinates by a few characters
# (observed: spring-boot-starter-parent -> spring-boot-starters-parent,
# spring-boot-starter-* -> spring-boot-started-*). Those near-miss names
# resolve to nothing. `spring-boot-start(ed|ers)` matches the corruptions but
# not the legitimate `spring-boot-starter*` names ('er' is neither 'ed' nor
# 'ers' at that offset).
_BUILD_COORD_CORRUPTION_RE='spring-boot-start(ed|ers)'

nimbus_has_corrupt_build_coords() {
    grep -qE "$_BUILD_COORD_CORRUPTION_RE" "$1"
}

nimbus_is_build_file() {
    # JVM build files are never whole-format-safe regardless of size:
    # dependency coordinates are verbatim identifiers, and whole-file
    # regeneration makes the model re-emit every one of them — the observed
    # corruption vector. A diff edit only touches the lines the step adds.
    case "${1##*/}" in
        pom.xml|build.gradle|build.gradle.kts|settings.gradle|settings.gradle.kts)
            return 0 ;;
        *)
            return 1 ;;
    esac
}

# ── verify.sh gate lint ───────────────────────────────────────────────────────

nimbus_gate_swallows_exit() {
    # Returns 0 if the gate contains the known exit-code-swallowing pattern
    # `if ! wait "$pid"; then status=$?`. Inside that branch $? holds the
    # status of the NEGATED test (always 0), so every build failure reports
    # success and a broken step gets committed as DONE. Capture the real
    # status instead: `wait "$pid" || status=$?`. The regex is anchored to the
    # start of an executable line on purpose: the helper templates warn
    # against this exact pattern in comments that a correctly generated
    # verify.sh copies verbatim, and an unanchored match would reject the good
    # gate along with the bad one.
    grep -qE '^[[:space:]]*if[[:space:]]+![[:space:]]+wait\b' "$1"
}

# ── .aider.conf.yml / model-card parsing ─────────────────────────────────────

_read_aider_conf_scalar() {
    # Print the value of a top-level `key: value` scalar from an aider config
    # (default ./.aider.conf.yml), with quotes stripped. Only the flat subset
    # of YAML the template config uses is supported — see NIMBUS_GUIDE.md
    # "Aider config note".
    local key="$1" conf="${2:-.aider.conf.yml}"
    [ -f "$conf" ] || return 0
    grep -m1 "^${key}:" "$conf" 2>/dev/null \
        | sed "s/^${key}:[[:space:]]*//" \
        | tr -d '"'"'" || true
}

nimbus_max_seq_len() {
    # Extract max_seq_len from a TabbyAPI /v1/model card on stdin. Prints the
    # digits, or nothing when the payload is not a TabbyAPI model card (e.g. a
    # vLLM /models listing) — callers treat empty as "skip the check". Total
    # function: exits 0 even on no match, so it is safe under set -e/pipefail.
    { grep -oE '"max_seq_len"[[:space:]]*:[[:space:]]*[0-9]+' || true; } \
        | head -n1 | tr -cd '0-9'
}

# ── .gitignore repair ─────────────────────────────────────────────────────────

_gitignore_has() {
    # Whole-line literal match: a commented-out or glued-onto-another-line
    # variant counts as missing and gets a clean rule line.
    grep -qxF -- "$1" "${2:-.gitignore}" 2>/dev/null
}

nimbus_missing_gitignore_entries() {
    # Print (one per line, in append order) the required .gitignore entries
    # missing from the given file (default ./.gitignore). Empty output means
    # the file is intact. .gitignore negations are order-dependent:
    # `!.aider.conf.yml` and `!.aiderignore` only re-include the files if they
    # appear AFTER the `.aider*` glob they carve out of. So when the glob line
    # is missing, the whole ordered block is re-emitted even if the negations
    # survived — appending `.aider*` alone after them would re-ignore both
    # config files.
    local gi="${1:-.gitignore}"
    local _append=()
    if ! _gitignore_has '.aider*' "$gi"; then
        _append+=('.aider*' '!.aider.conf.yml' '!.aiderignore')
    else
        _gitignore_has '!.aider.conf.yml' "$gi" || _append+=('!.aider.conf.yml')
        _gitignore_has '!.aiderignore' "$gi"    || _append+=('!.aiderignore')
    fi
    _gitignore_has 'plans/*.log' "$gi" || _append+=('plans/*.log')
    if [ "${#_append[@]}" -gt 0 ]; then
        printf '%s\n' "${_append[@]}"
    fi
}

# ── Aider log classification ──────────────────────────────────────────────────
# Two very different failures both surface as "token limit" and must NOT be
# conflated: INPUT/context overflow (the prompt did not fit — fix by reducing
# input) vs OUTPUT truncation at finish_reason=length (usually a degenerate
# repetition loop burning the output budget — a model/cache QUALITY problem).
# See the failure-classification block in phase2.sh for the guidance given
# per case.

nimbus_log_input_overflow() {
    grep -qiE "(context\.length exceeded|maximum context length|input is too long|KV cache is full|Prompt is too long|Prompt exceeds context|context overflow)" "$1" 2>/dev/null
}

nimbus_log_token_limit() {
    grep -qiE "(has hit a token limit|token limit exceeded|n_predict tokens limit|finish_reason.{0,12}length)" "$1" 2>/dev/null
}

nimbus_log_max_repeat() {
    # Longest run of CONSECUTIVE identical non-trivial lines in the log.
    # Trailing whitespace is stripped before the trivial-line filter (Aider
    # pads log lines to terminal width, so a blank diff line becomes "+" plus
    # spaces and would otherwise pass length>10). Total-occurrence counting
    # would falsely fire on lines that legitimately recur across a file
    # (blank lines, closing braces, the same mock-setup line in every test).
    awk '
        { s=$0; sub(/[ \t]+$/,"",s)
          if (length(s) <= 10) { prev=""; run=0; next }
          if (s==prev) run++; else { prev=s; run=1 }
          if (run>max) max=run }
        END { print max+0 }' "$1" 2>/dev/null
}

nimbus_log_max_total_repeat() {
    # Highest TOTAL occurrence count of any single non-trivial line — used
    # only to decide whether a token-cap exit followed a repetition loop
    # (where consecutive-run counting can be defeated by interleaved output).
    awk 'length > 10' "$1" 2>/dev/null | sort | uniq -c | sort -rn | awk 'NR==1{print $1; exit}'
}
