#!/bin/bash
# Build a throwaway benchmark repo for one loading strategy.
#
#   mkfixture.sh <dir> <strategy> <doc-count> [seed] [size] [few-n]
#
# Strategies -- how documentation reaches the session:
#
#   none      nothing. No docs in context, no guidance, no tools pointed at
#             docs/. The control: what the session costs with docs uninvolved.
#   search    no system. Docs on disk; Claude greps and reads at whim.
#   claudemd  the doc index lives in CLAUDE.md, so it loads by default every
#             session, and CLAUDE.md tells Claude to read the matching file.
#   few       SessionStart hook preloads a small subset (default 3) in full.
#   all       SessionStart hook preloads the entire corpus in full.
#   agent     hook emits an index only; skill + doc-search subagent fetch just
#             what a question needs.
#
# Fixtures carry their own CLAUDE.md. The real repo's ask-before-acting rule
# makes a headless session stop and request confirmation instead of working.
set -euo pipefail

DIR="$1"; STRAT="$2"; COUNT="$3"; SEED="${4:-1729}"; SIZE="${5:-mixed}"; FEW_N="${6:-3}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL="${SRC}/.claude/skills/doc-search"

rm -rf "$DIR"; mkdir -p "$DIR/docs/standards" "$DIR/.claude"
git -C "$DIR" init -q

# The manifest holds every planted fact -- it is the answer key. It must NOT
# live inside the fixture, or the session can read it and skip the documents
# entirely. (It could, and did: a control with no docs at all still answered.)
MANIFEST="${DIR%/}.corpus.json"
python3 "${SRC}/tests/bench/gen-corpus.py" \
  --out "$DIR/docs/standards" --count "$COUNT" --seed "$SEED" \
  --size "$SIZE" --manifest "$MANIFEST" >/dev/null

PREAMBLE='# Benchmark fixture

A synthetic project. Answer questions directly and autonomously; do not ask for
confirmation before using read-only tools.'

READ_PERMS='"Bash(grep:*)", "Bash(find:*)", "Bash(cat:*)", "Bash(ls:*)", "Bash(head:*)"'
SKILL_PERMS="\"Bash(./.claude/skills/doc-search/doc-search.sh:*)\", \"Bash(./.claude/skills/doc-search/load-baseline.sh:*)\""

write_settings() {  # $1 = perms, $2 = hook args ("" = no hook)
  if [[ -z "${2:-}" && "${3:-nohook}" == "nohook" ]]; then
    cat > "$DIR/.claude/settings.json" <<JSON
{ "permissions": { "allow": [ $1 ] } }
JSON
  else
    cat > "$DIR/.claude/settings.json" <<JSON
{
  "permissions": { "allow": [ $1 ] },
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command",
        "command": "./.claude/skills/doc-search/load-baseline.sh $2 2>/dev/null || true" } ] }
    ]
  }
}
JSON
  fi
}

install_skill() {  # copies scripts, writes manifest with $1 as the baseline list
  mkdir -p "$DIR/.claude/skills/doc-search"
  cp "${SKILL}/doc-search.sh" "${SKILL}/load-baseline.sh" "$DIR/.claude/skills/doc-search/"
  { echo "# Doc Search"; echo
    echo "## Baseline (loads on SessionStart)"
    echo "$1"; echo
    echo "## All Available Docs"; echo
    echo "### Standards"
    (cd "$DIR" && ls docs/standards/*.md | sed 's/^/- /')
  } > "$DIR/.claude/skills/doc-search/doc-search.md"
}

case "$STRAT" in

  none)
    # True control: the documents are not in the repo at all. A permission
    # allowlist cannot create this state -- runs use --dangerously-skip-
    # permissions, so Claude keeps the built-in Read/Grep/Glob tools and will
    # simply read docs/ off disk, making the control identical to `search`.
    # corpus.json is kept so the runner can still pick the same target.
    rm -rf "$DIR/docs"
    printf '%s\n' "$PREAMBLE" > "$DIR/CLAUDE.md"
    write_settings '"Bash(echo:*)"' "" nohook
    ;;

  search)
    printf '%s\n' "$PREAMBLE" > "$DIR/CLAUDE.md"
    write_settings "$READ_PERMS" "" nohook
    ;;

  claudemd)
    # The index is part of CLAUDE.md, so it is carried on every turn by default.
    { printf '%s\n' "$PREAMBLE"; echo
      echo "## Documentation"; echo
      echo "Docs live in \`docs/standards/\`, one file per service covering its"
      echo "ownership, port and behaviour. To answer a question about a service,"
      echo "read the matching file below. Do not read all of them."; echo
      (cd "$DIR" && for f in docs/standards/*.md; do
         echo "- \`$f\` — $(grep -m1 '^# ' "$f" | sed 's/^# //')"; done)
    } > "$DIR/CLAUDE.md"
    write_settings "$READ_PERMS" "" nohook
    ;;

  few)
    printf '%s\n' "$PREAMBLE" > "$DIR/CLAUDE.md"
    install_skill "$(cd "$DIR/docs/standards" && ls *.md | head -"$FEW_N" | sed 's/^/- /')"
    write_settings "${SKILL_PERMS}, ${READ_PERMS}" "" hook
    ;;

  all)
    printf '%s\n' "$PREAMBLE" > "$DIR/CLAUDE.md"
    install_skill "$(cd "$DIR/docs/standards" && ls *.md | sed 's/^/- /')"
    write_settings "${SKILL_PERMS}, ${READ_PERMS}" "" hook
    ;;

  agent)
    # Baseline = ALL docs: with --refs-only that is one index line per doc,
    # which is the design (an index of everything, content of nothing). A
    # one-doc baseline left the session unaware the other docs existed.
    install_skill "$(cd "$DIR/docs/standards" && ls *.md | sed 's/^/- /')"
    write_settings "${SKILL_PERMS}, ${READ_PERMS}" "--refs-only" hook
    mkdir -p "$DIR/.claude/agents"
    cp "${SRC}/.claude/agents/doc-search.md" "$DIR/.claude/agents/"
    { printf '%s\n' "$PREAMBLE"; echo
      echo "Docs access: delegate \`docs/\` lookups to the \`doc-search\` agent"
      echo "rather than reading, grepping or globbing those files yourself. Wait"
      echo "for its actual result before acting on it."
    } > "$DIR/CLAUDE.md"
    ;;

  *) echo "unknown strategy: $STRAT" >&2; exit 1 ;;
esac

echo "$DIR"
