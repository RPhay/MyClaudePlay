#!/bin/bash
# Unit tests for .claude/skills/doc-search/doc-search.sh
#
# Each test builds a throwaway git repo under $TMPDIR, copies the real scripts
# into it, and runs them there. Nothing touches this repository. No model calls,
# no cost -- for the cost/behaviour comparison see tests/bench/.
#
#   ./tests/unit/doc-search.test.sh [name-filter]

set -uo pipefail

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL_SRC="${SRC_ROOT}/.claude/skills/doc-search"
FILTER="${1:-}"

PASS=0; FAIL=0; CURRENT=""; CURRENT_FAILED=0
FAILED_NAMES=()

new_fixture() {
  local dir; dir=$(mktemp -d)
  git -C "$dir" init -q
  mkdir -p "${dir}/.claude/skills/doc-search" "${dir}/docs/standards"
  cp "${SKILL_SRC}/doc-search.sh" "${SKILL_SRC}/load-baseline.sh" \
     "${dir}/.claude/skills/doc-search/"
  cat > "${dir}/.claude/skills/doc-search/doc-search.md" <<'EOF'
# Doc Search

## Baseline (loads on SessionStart)
- alpha.md

## All Available Docs

### Standards
EOF
  printf '# Alpha\n\n## Section\n\nAlpha summary paragraph.\nSecond line of it.\n\nMore alpha body.\n' \
    > "${dir}/docs/standards/alpha.md"
  printf '# Beta\n\nBeta summary paragraph.\n' > "${dir}/docs/standards/beta.md"
  echo "$dir"
}

run_ds() { local d="$1"; shift
  OUT=$(cd "$d" && ./.claude/skills/doc-search/doc-search.sh "$@" 2>&1); RC=$?; }

run_baseline() { local d="$1"; shift
  OUT=$(cd "$d" && ./.claude/skills/doc-search/load-baseline.sh "$@" 2>&1); RC=$?; }

fail() { CURRENT_FAILED=1; echo "  FAIL: $CURRENT"; echo "        $1"
         [[ -n "${2:-}" ]] && printf '        --- output ---\n%s\n' "$2"; return 0; }

assert_contains()     { case "$1" in *"$2"*) return 0;; *) fail "expected to contain: $2" "$1";; esac; }
assert_not_contains() { case "$1" in *"$2"*) fail "expected NOT to contain: $2" "$1";; *) return 0;; esac; }
assert_eq()           { [[ "$1" == "$2" ]] || fail "expected [$2], got [$1]"; }
assert_file()         { [[ -f "$1" ]] || fail "expected file: $1"; }
assert_no_file()      { [[ ! -f "$1" ]] || fail "expected NO file: $1"; }

test_case() {
  local name="$1" fn="$2"
  [[ -n "$FILTER" && "$name" != *"$FILTER"* ]] && return 0
  CURRENT="$name"; CURRENT_FAILED=0
  "$fn"
  if [[ $CURRENT_FAILED -eq 0 ]]; then PASS=$((PASS+1)); echo "  ok: $name"
  else FAIL=$((FAIL+1)); FAILED_NAMES+=("$name"); fi
  return 0
}

make_skill() {
  mkdir -p "${1}/.claude/skills/${2}"
  printf '{"name":"%s","description":"%s"}\n' "$2" "$3" > "${1}/.claude/skills/${2}/manifest.json"
}

# --- load -------------------------------------------------------------------

t_load_exact()    { local d; d=$(new_fixture); run_ds "$d" --load alpha.md
  assert_contains "$OUT" "### Document: alpha.md"; assert_contains "$OUT" "More alpha body."
  assert_eq "$RC" 0; rm -rf "$d"; }

t_load_no_ext()   { local d; d=$(new_fixture); run_ds "$d" --load alpha
  assert_contains "$OUT" "More alpha body."; rm -rf "$d"; }

t_load_multi()    { local d; d=$(new_fixture); run_ds "$d" --load alpha,beta
  assert_contains "$OUT" "More alpha body."; assert_contains "$OUT" "Beta summary paragraph."
  rm -rf "$d"; }

t_load_missing()  { local d; d=$(new_fixture); run_ds "$d" --load nosuchdoc
  assert_contains "$OUT" "Document not found: nosuchdoc"; rm -rf "$d"; }

t_load_no_args()  { local d; d=$(new_fixture)
  OUT=$(cd "$d" && ./.claude/skills/doc-search/doc-search.sh --summary 2>&1); RC=$?
  assert_eq "$RC" 1; assert_contains "$OUT" "requires document names"; rm -rf "$d"; }

t_unknown_opt()   { local d; d=$(new_fixture); run_ds "$d" --nonsense
  assert_eq "$RC" 1; assert_contains "$OUT" "Unknown option"; rm -rf "$d"; }

# BUG: --summary used `sed '/^$/q'`, which quits at the blank line after the H1,
# so every doc summarised to its own title.
t_summary_is_paragraph() { local d; d=$(new_fixture); run_ds "$d" --load alpha --summary
  assert_contains "$OUT" "Size: "
  assert_contains "$OUT" "Alpha summary paragraph."
  assert_contains "$OUT" "Second line of it."
  assert_not_contains "$OUT" "## Section"
  assert_not_contains "$OUT" "More alpha body."
  rm -rf "$d"; }

t_refs_only()     { local d; d=$(new_fixture); run_ds "$d" --load alpha --refs-only
  assert_contains "$OUT" "- **alpha**: Alpha"
  assert_not_contains "$OUT" "Alpha summary paragraph."; rm -rf "$d"; }

# BUG: find_doc() took `head -1`, silently returning a wrong-but-plausible doc.
t_ambiguous_reports() { local d; d=$(new_fixture)
  printf '# Auth API\n\nApi.\n' > "${d}/docs/standards/auth-api.md"
  printf '# Auth UI\n\nUi.\n'   > "${d}/docs/standards/auth-ui.md"
  run_ds "$d" --load auth
  assert_contains "$OUT" "ambiguous document name 'auth' matches 2 files"
  assert_contains "$OUT" "auth-api.md"; assert_contains "$OUT" "auth-ui.md"
  assert_not_contains "$OUT" "### Document:"
  assert_not_contains "$OUT" "Document not found"
  rm -rf "$d"; }

t_exact_beats_ambiguity() { local d; d=$(new_fixture)
  printf '# Auth\n\nExact.\n'     > "${d}/docs/auth.md"
  printf '# Auth API\n\nOther.\n' > "${d}/docs/standards/auth-api.md"
  run_ds "$d" --load auth
  assert_contains "$OUT" "Exact."; assert_not_contains "$OUT" "ambiguous"; rm -rf "$d"; }

t_ambiguity_not_contagious() { local d; d=$(new_fixture)
  printf '# Auth API\n\nApi.\n' > "${d}/docs/standards/auth-api.md"
  printf '# Auth UI\n\nUi.\n'   > "${d}/docs/standards/auth-ui.md"
  run_ds "$d" --load auth,beta
  assert_contains "$OUT" "ambiguous document name"
  assert_contains "$OUT" "Beta summary paragraph."; rm -rf "$d"; }

t_spaces_in_name() { local d; d=$(new_fixture)
  printf '# Spaced\n\nSpaced body.\n' > "${d}/docs/standards/my doc.md"
  run_ds "$d" --load "my doc.md"
  assert_contains "$OUT" "Spaced body."; rm -rf "$d"; }

# --- analyze ----------------------------------------------------------------

t_analyze_preview_no_write() { local d; d=$(new_fixture); make_skill "$d" demo "Implement a feature"
  run_ds "$d" --analyze demo; assert_eq "$RC" 0
  assert_contains "$OUT" "Preview generated"
  assert_no_file "${d}/.claude/skills/demo/doc-needs.md"; rm -rf "$d"; }

t_analyze_writes() { local d; d=$(new_fixture); make_skill "$d" demo "Implement a feature"
  run_ds "$d" --analyze demo --overwrite; assert_eq "$RC" 0
  assert_file "${d}/.claude/skills/demo/doc-needs.md"
  assert_contains "$(cat "${d}/.claude/skills/demo/doc-needs.md")" "# Doc Needs: demo"
  rm -rf "$d"; }

t_analyze_keywords() { local d; d=$(new_fixture); make_skill "$d" deployer "Ship and release builds"
  run_ds "$d" --analyze deployer --overwrite
  local b; b=$(cat "${d}/.claude/skills/deployer/doc-needs.md")
  assert_contains "$b" "deployment-docs/deploy-process.md"
  assert_not_contains "$b" "uix.md"; rm -rf "$d"; }

t_analyze_missing_skill() { local d; d=$(new_fixture); run_ds "$d" --analyze ghost --overwrite
  assert_eq "$RC" 1; assert_contains "$OUT" "Skill not found: ghost"; rm -rf "$d"; }

# BUG: analyze_skill() wrote <skill>/doc-search.md -- for doc-search that IS the
# manifest, so the run destroyed the baseline and catalog.
t_analyze_keeps_manifest() { local d; d=$(new_fixture)
  local m="${d}/.claude/skills/doc-search/doc-search.md"
  local before; before=$(cat "$m")
  run_ds "$d" --analyze doc-search --overwrite; assert_eq "$RC" 0
  assert_eq "$(cat "$m")" "$before"
  assert_file "${d}/.claude/skills/doc-search/doc-needs.md"; rm -rf "$d"; }

# BUG: `echo "" | wc -l` is 1, so empty scans reported "Found 1".
t_counts_empty_as_zero() { local d; d=$(new_fixture)
  rm -f "${d}"/docs/standards/*.md; make_skill "$d" plain "Does something"
  run_ds "$d" --analyze plain
  assert_contains "$OUT" "Found 0 standard docs"
  assert_contains "$OUT" "Found 0 features"; rm -rf "$d"; }

t_counts_real() { local d; d=$(new_fixture)
  mkdir -p "${d}/docs/features/one" "${d}/docs/features/two"
  make_skill "$d" plain "Does something"
  run_ds "$d" --analyze plain
  assert_contains "$OUT" "Found 2 standard docs"
  assert_contains "$OUT" "Found 2 features"; rm -rf "$d"; }

# --- update -----------------------------------------------------------------

t_update_keeps_baseline() { local d; d=$(new_fixture)
  local m="${d}/.claude/skills/doc-search/doc-search.md"
  printf '# Doc Search\n\n## Baseline (loads on SessionStart)\n- beta.md\n\n## All Available Docs\n' > "$m"
  run_ds "$d" --update; assert_eq "$RC" 0
  assert_contains "$(cat "$m")" "- beta.md"; rm -rf "$d"; }

t_update_default_baseline() { local d; d=$(new_fixture)
  rm -f "${d}/.claude/skills/doc-search/doc-search.md"; run_ds "$d" --update
  assert_contains "$(cat "${d}/.claude/skills/doc-search/doc-search.md")" "- feature-structure.md"
  rm -rf "$d"; }

t_update_standards() { local d; d=$(new_fixture); run_ds "$d" --update
  local b; b=$(cat "${d}/.claude/skills/doc-search/doc-search.md")
  assert_contains "$b" "docs/standards/alpha.md"
  assert_contains "$b" "docs/standards/beta.md"; rm -rf "$d"; }

t_update_features() { local d; d=$(new_fixture)
  mkdir -p "${d}/docs/features/checkout"
  printf '# Checkout\n' > "${d}/docs/features/checkout/feature.md"
  run_ds "$d" --update
  assert_contains "$(cat "${d}/.claude/skills/doc-search/doc-search.md")" "docs/features/checkout/feature.md"
  rm -rf "$d"; }

t_update_other() { local d; d=$(new_fixture); printf '# Loose\n' > "${d}/docs/loose.md"
  run_ds "$d" --update
  assert_contains "$(cat "${d}/.claude/skills/doc-search/doc-search.md")" "docs/loose.md"; rm -rf "$d"; }

t_update_empty_categories() { local d; d=$(new_fixture); run_ds "$d" --update
  assert_eq "$RC" 0
  local b; b=$(cat "${d}/.claude/skills/doc-search/doc-search.md")
  assert_contains "$b" "### Features"; assert_contains "$b" "### Other Documentation"; rm -rf "$d"; }

t_update_loadable() { local d; d=$(new_fixture)
  mkdir -p "${d}/docs/features/checkout"
  printf '# Checkout\n\nCheckout body.\n' > "${d}/docs/features/checkout/feature.md"
  run_ds "$d" --update; run_ds "$d" --load features/checkout/feature.md
  assert_contains "$OUT" "Checkout body."; rm -rf "$d"; }

# --- load-baseline ----------------------------------------------------------

t_baseline_policy_and_index() { local d; d=$(new_fixture); run_baseline "$d" --refs-only
  assert_eq "$RC" 0
  assert_contains "$OUT" "## Project documentation (doc-search)"
  assert_contains "$OUT" "- **alpha.md**: Alpha"
  assert_not_contains "$OUT" "More alpha body."; rm -rf "$d"; }

t_baseline_no_manifest() { local d; d=$(new_fixture)
  rm -f "${d}/.claude/skills/doc-search/doc-search.md"; run_baseline "$d" --refs-only
  assert_eq "$RC" 0; assert_contains "$OUT" "manifest not found"; rm -rf "$d"; }

t_baseline_multi() { local d; d=$(new_fixture)
  printf '# Doc Search\n\n## Baseline (loads on SessionStart)\n- alpha.md\n- beta.md\n\n## All Available Docs\n' \
    > "${d}/.claude/skills/doc-search/doc-search.md"
  run_baseline "$d" --refs-only
  assert_contains "$OUT" "- **alpha.md**: Alpha"
  assert_contains "$OUT" "- **beta.md**: Beta"; rm -rf "$d"; }

# --- run --------------------------------------------------------------------

echo "doc-search unit tests"; echo
echo "load:"
test_case "load exact filename"               t_load_exact
test_case "load without extension"            t_load_no_ext
test_case "load multiple docs"                t_load_multi
test_case "load missing doc warns"            t_load_missing
test_case "load without names errors"         t_load_no_args
test_case "unknown option errors"             t_unknown_opt
test_case "summary returns first paragraph"   t_summary_is_paragraph
test_case "refs-only returns heading"         t_refs_only
test_case "ambiguous name reports candidates" t_ambiguous_reports
test_case "exact match beats ambiguity"       t_exact_beats_ambiguity
test_case "ambiguity does not block siblings" t_ambiguity_not_contagious
test_case "filename with spaces"              t_spaces_in_name
echo; echo "analyze:"
test_case "preview does not write"            t_analyze_preview_no_write
test_case "overwrite writes doc-needs.md"     t_analyze_writes
test_case "keyword matching picks docs"       t_analyze_keywords
test_case "missing skill errors"              t_analyze_missing_skill
test_case "analyzing doc-search keeps manifest" t_analyze_keeps_manifest
test_case "empty scans count as zero"         t_counts_empty_as_zero
test_case "non-empty scans count correctly"   t_counts_real
echo; echo "update:"
test_case "preserves configured baseline"     t_update_keeps_baseline
test_case "defaults baseline when absent"     t_update_default_baseline
test_case "catalogs standards"                t_update_standards
test_case "catalogs features"                 t_update_features
test_case "catalogs other docs"               t_update_other
test_case "empty categories do not break"     t_update_empty_categories
test_case "catalogued paths are loadable"     t_update_loadable
echo; echo "load-baseline:"
test_case "emits policy and index"            t_baseline_policy_and_index
test_case "missing manifest is not fatal"     t_baseline_no_manifest
test_case "multiple baseline docs"            t_baseline_multi

echo; echo "-----------------------------------"
echo "passed: $PASS   failed: $FAIL"
if [[ $FAIL -gt 0 ]]; then printf 'failing: %s\n' "${FAILED_NAMES[@]}"; exit 1; fi
