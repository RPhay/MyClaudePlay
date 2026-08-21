#!/bin/bash
# Helper script to load baseline docs on SessionStart

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
SKILL_DIR="${REPO_ROOT}/.claude/skills/doc-search"
MANIFEST="${SKILL_DIR}/doc-search.md"

if [[ ! -f "$MANIFEST" ]]; then
  echo "Warning: doc-search manifest not found" >&2
  exit 0
fi

# Extract baseline section
baseline_docs=$(sed -n '/^## Baseline/,/^## /p' "$MANIFEST" | grep "^- " | sed 's/^- //' | tr '\n' ',' | sed 's/,$//')

if [[ -z "$baseline_docs" ]]; then
  echo "No baseline docs configured" >&2
  exit 0
fi

# Emit the routing policy alongside the index. This travels with the skill, so
# adopting repos need no CLAUDE.md changes -- installing the hook is enough.
cat <<'POLICY'
## Project documentation (doc-search)

Consult anything under docs/ through the `doc-search` agent. Do not read or glob
those files yourself -- that is what the agent is for, and it keeps document text
out of this session's context. Applies even when you only have a partial name or
are unsure a relevant doc exists: ask the agent. Read directly only when the user
names a specific file and wants its contents, or when you are editing a doc.

After dispatching, wait for the agent's actual returned result before acting on
it. Never predict or describe what it will report -- that arrives as a
notification, it is never something you write yourself. Never state that an
operation ran until the result is in hand; if asked while it is still running,
say so. If the agent fails or returns nothing usable, say that plainly and stop
rather than filling the gap with a plausible answer.

Docs available in this repo:
POLICY

# Load baseline docs. Extra args pass through to doc-search.sh, so the
# SessionStart hook can ask for --refs-only instead of full content.
"${SKILL_DIR}/doc-search.sh" --load "$baseline_docs" "$@"
