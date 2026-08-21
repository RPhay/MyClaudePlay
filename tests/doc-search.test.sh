#!/bin/bash
# Tests for .claude/skills/doc-search/doc-search.sh
#
# Each test builds a throwaway git repo under $TMPDIR, copies the real scripts
# into it, and runs them there. Nothing touches this repository.
#
# Usage: ./tests/doc-search.test.sh [name-filter]

set -uo pipefail

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_SRC="${SRC_ROOT}/.claude/skills/doc-search"
FILTER="${1:-}"

PASS=0
FAIL=0
FAILED_NAMES=()

# --- harness ----------------------------------------------------------------

# Build a fixture repo. Every test gets its own.
new_fixture() {
  local dir
  dir=$(mktemp -d)
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
  printf '# Beta\n\nBeta summary paragraph.\n' \
    > "${dir}/docs/standards/beta.md"
  echo "$dir"
}

# Run doc-search.sh inside a fixture. Captures stdout+stderr and exit status.
# Sets: OUT, RC
run_ds() {
  local dir="$1"; shift
  OUT=$(cd "$dir" && ./.claude/skills/doc-search/doc-search.sh "$@" 2>&1)
  RC=$?
}

CURRENT_FAILED=0
fail() {
  CURRENT_FAILED=1
  echo "  FAIL: $CURRENT"
  echo "        $1"
  [[ -n "${2:-}" ]] && printf '        --- output ---\n%s\n        --------------\n' "$2"
  return 0
}

assert_contains() {
  case "$1" in
    *"$2"*) return 0 ;;
    *) fail "expected output to contain: $2" "$1"; return 1 ;;
  esac
}

assert_not_contains() {
  case "$1" in
    *"$2"*) fail "expected output NOT to contain: $2" "$1"; return 1 ;;
    *) return 0 ;;
  esac
}

assert_eq() {
  if [[ "$1" != "$2" ]]; then
    fail "expected [$2], got [$1]"
    return 1
  fi
}

assert_file() {
  [[ -f "$1" ]] || { fail "expected file to exist: $1"; return 1; }
}

assert_no_file() {
  [[ ! -f "$1" ]] || { fail "expected file NOT to exist: $1"; return 1; }
}

# Register a test. Body is a function name.
CURRENT=""
test_case() {
  local name="$1" fn="$2"
  [[ -n "$FILTER" && "$name" != *"$FILTER"* ]] && return 0
  CURRENT="$name"
  CURRENT_FAILED=0
  "$fn"
  if [[ $CURRENT_FAILED -eq 0 ]]; then
    PASS=$((PASS + 1))
    echo "  ok: $name"
  else
    FAIL=$((FAIL + 1))
    FAILED_NAMES+=("$name")
  fi
  return 0
}

# --- load mode --------------------------------------------------------------

t_load_exact() {
  local d; d=$(new_fixture)
  run_ds "$d" --load alpha.md
  assert_contains "$OUT" "### Document: alpha.md"
  assert_contains "$OUT" "More alpha body."
  assert_eq "$RC" 0
  rm -rf "$d"
}

t_load_no_extension() {
  local d; d=$(new_fixture)
  run_ds "$d" --load alpha
  assert_contains "$OUT" "More alpha body."
  rm -rf "$d"
}

t_load_multiple() {
  local d; d=$(new_fixture)
  run_ds "$d" --load alpha,beta
  assert_contains "$OUT" "More alpha body."
  assert_contains "$OUT" "Beta summary paragraph."
  rm -rf "$d"
}

t_load_summary() {
  local d; d=$(new_fixture)
  run_ds "$d" --load alpha --summary
  assert_contains "$OUT" "Size: "
  assert_contains "$OUT" "Alpha summary paragraph."
  assert_contains "$OUT" "Second line of it."
  # the heading between H1 and the paragraph must be skipped, not returned as it
  assert_not_contains "$OUT" "## Section"
  assert_not_contains "$OUT" "More alpha body."
  rm -rf "$d"
}

t_load_refs_only() {
  local d; d=$(new_fixture)
  run_ds "$d" --load alpha --refs-only
  assert_contains "$OUT" "- **alpha**: Alpha"
  assert_not_contains "$OUT" "Alpha summary paragraph."
  rm -rf "$d"
}

t_load_missing() {
  local d; d=$(new_fixture)
  run_ds "$d" --load nosuchdoc
  assert_contains "$OUT" "Document not found: nosuchdoc"
  rm -rf "$d"
}

t_load_requires_args() {
  local d; d=$(new_fixture)
  OUT=$(cd "$d" && ./.claude/skills/doc-search/doc-search.sh --summary 2>&1); RC=$?
  assert_eq "$RC" 1
  assert_contains "$OUT" "requires document names"
  rm -rf "$d"
}

t_unknown_option() {
  local d; d=$(new_fixture)
  run_ds "$d" --nonsense
  assert_eq "$RC" 1
  assert_contains "$OUT" "Unknown option"
  rm -rf "$d"
}

# Regression: a partial name matching two docs used to silently return the first.
t_ambiguous_name_reports() {
  local d; d=$(new_fixture)
  printf '# Auth API\n\nApi doc.\n' > "${d}/docs/standards/auth-api.md"
  printf '# Auth UI\n\nUi doc.\n'  > "${d}/docs/standards/auth-ui.md"
  run_ds "$d" --load auth
  assert_contains "$OUT" "ambiguous document name 'auth' matches 2 files"
  assert_contains "$OUT" "auth-api.md"
  assert_contains "$OUT" "auth-ui.md"
  # ambiguous means no document is emitted, and no misleading "not found"
  assert_not_contains "$OUT" "### Document:"
  assert_not_contains "$OUT" "Document not found"
  rm -rf "$d"
}

# An exact filename must still win even when it is a prefix of another doc.
t_exact_beats_ambiguity() {
  local d; d=$(new_fixture)
  printf '# Auth\n\nExact.\n'      > "${d}/docs/auth.md"
  printf '# Auth API\n\nOther.\n'  > "${d}/docs/standards/auth-api.md"
  run_ds "$d" --load auth
  assert_contains "$OUT" "Exact."
  assert_not_contains "$OUT" "ambiguous"
  rm -rf "$d"
}

# One bad name must not suppress the good ones alongside it.
t_ambiguous_does_not_block_siblings() {
  local d; d=$(new_fixture)
  printf '# Auth API\n\nApi.\n' > "${d}/docs/standards/auth-api.md"
  printf '# Auth UI\n\nUi.\n'   > "${d}/docs/standards/auth-ui.md"
  run_ds "$d" --load auth,beta
  assert_contains "$OUT" "ambiguous document name"
  assert_contains "$OUT" "Beta summary paragraph."
  rm -rf "$d"
}

# --- analyze mode -----------------------------------------------------------

make_skill() {
  local dir="$1" name="$2" desc="$3"
  mkdir -p "${dir}/.claude/skills/${name}"
  printf '{"name":"%s","description":"%s"}\n' "$name" "$desc" \
    > "${dir}/.claude/skills/${name}/manifest.json"
}

t_analyze_preview_does_not_write() {
  local d; d=$(new_fixture)
  make_skill "$d" demo "Implement a feature end to end"
  run_ds "$d" --analyze demo
  assert_eq "$RC" 0
  assert_contains "$OUT" "Preview generated"
  assert_no_file "${d}/.claude/skills/demo/doc-needs.md"
  rm -rf "$d"
}

t_analyze_overwrite_writes() {
  local d; d=$(new_fixture)
  make_skill "$d" demo "Implement a feature end to end"
  run_ds "$d" --analyze demo --overwrite
  assert_eq "$RC" 0
  assert_file "${d}/.claude/skills/demo/doc-needs.md"
  local body; body=$(cat "${d}/.claude/skills/demo/doc-needs.md")
  assert_contains "$body" "# Doc Needs: demo"
  assert_contains "$body" "docs/standards/feature-structure.md"
  rm -rf "$d"
}

t_analyze_keyword_matching() {
  local d; d=$(new_fixture)
  make_skill "$d" deployer "Ship and release builds"
  run_ds "$d" --analyze deployer --overwrite
  local body; body=$(cat "${d}/.claude/skills/deployer/doc-needs.md")
  assert_contains "$body" "deployment-docs/deploy-process.md"
  # no feature/implement keyword, so uix must not be recommended
  assert_not_contains "$body" "uix.md"
  rm -rf "$d"
}

t_analyze_no_conditionals_default_section() {
  local d; d=$(new_fixture)
  make_skill "$d" plain "Does something unrelated"
  run_ds "$d" --analyze plain --overwrite
  local body; body=$(cat "${d}/.claude/skills/plain/doc-needs.md")
  assert_contains "$body" "### When working with a specific feature"
  rm -rf "$d"
}

# `echo "" | wc -l` is 1, so empty scans used to report "Found 1".
t_analyze_counts_empty_scans_as_zero() {
  local d; d=$(new_fixture)
  rm -f "${d}"/docs/standards/*.md
  make_skill "$d" plain "Does something"
  run_ds "$d" --analyze plain
  assert_contains "$OUT" "Found 0 standard docs"
  assert_contains "$OUT" "Found 0 features"
  rm -rf "$d"
}

t_analyze_counts_real_scans() {
  local d; d=$(new_fixture)
  mkdir -p "${d}/docs/features/one" "${d}/docs/features/two"
  make_skill "$d" plain "Does something"
  run_ds "$d" --analyze plain
  assert_contains "$OUT" "Found 2 standard docs"
  assert_contains "$OUT" "Found 2 features"
  rm -rf "$d"
}

t_analyze_missing_skill() {
  local d; d=$(new_fixture)
  run_ds "$d" --analyze ghost --overwrite
  assert_eq "$RC" 1
  assert_contains "$OUT" "Skill not found: ghost"
  rm -rf "$d"
}

# Regression for the verified bug: analyzing doc-search itself used to write to
# <skill>/doc-search.md, which for this skill IS the manifest.
t_analyze_doc_search_preserves_manifest() {
  local d; d=$(new_fixture)
  local manifest="${d}/.claude/skills/doc-search/doc-search.md"
  local before; before=$(cat "$manifest")
  run_ds "$d" --analyze doc-search --overwrite
  assert_eq "$RC" 0
  local after; after=$(cat "$manifest")
  assert_eq "$after" "$before"
  assert_file "${d}/.claude/skills/doc-search/doc-needs.md"
  rm -rf "$d"
}

# The manifest must survive an --update run straight after an --analyze.
t_analyze_then_baseline_still_loads() {
  local d; d=$(new_fixture)
  run_ds "$d" --analyze doc-search --overwrite
  OUT=$(cd "$d" && ./.claude/skills/doc-search/load-baseline.sh --refs-only 2>&1); RC=$?
  assert_contains "$OUT" "- **alpha.md**: Alpha"
  rm -rf "$d"
}

# --- update mode ------------------------------------------------------------

t_update_preserves_baseline() {
  local d; d=$(new_fixture)
  local manifest="${d}/.claude/skills/doc-search/doc-search.md"
  printf '# Doc Search\n\n## Baseline (loads on SessionStart)\n- beta.md\n\n## All Available Docs\n' \
    > "$manifest"
  run_ds "$d" --update
  assert_eq "$RC" 0
  local body; body=$(cat "$manifest")
  assert_contains "$body" "- beta.md"
  assert_not_contains "$body" "- alpha.md
"
  rm -rf "$d"
}

t_update_defaults_baseline_when_absent() {
  local d; d=$(new_fixture)
  local manifest="${d}/.claude/skills/doc-search/doc-search.md"
  rm -f "$manifest"
  run_ds "$d" --update
  assert_contains "$(cat "$manifest")" "- feature-structure.md"
  rm -rf "$d"
}

t_update_catalogs_standards() {
  local d; d=$(new_fixture)
  run_ds "$d" --update
  local body; body=$(cat "${d}/.claude/skills/doc-search/doc-search.md")
  assert_contains "$body" "docs/standards/alpha.md"
  assert_contains "$body" "docs/standards/beta.md"
  rm -rf "$d"
}

# Previously untested: docs/features/ has always been empty in this repo.
t_update_catalogs_features() {
  local d; d=$(new_fixture)
  mkdir -p "${d}/docs/features/checkout"
  printf '# Checkout\n' > "${d}/docs/features/checkout/feature.md"
  printf '# Context\n'  > "${d}/docs/features/checkout/context.md"
  run_ds "$d" --update
  local body; body=$(cat "${d}/.claude/skills/doc-search/doc-search.md")
  assert_contains "$body" "docs/features/checkout/feature.md"
  assert_contains "$body" "docs/features/checkout/context.md"
  rm -rf "$d"
}

# Previously untested: the "Other Documentation" branch.
t_update_catalogs_other() {
  local d; d=$(new_fixture)
  printf '# Loose\n' > "${d}/docs/loose.md"
  run_ds "$d" --update
  local body; body=$(cat "${d}/.claude/skills/doc-search/doc-search.md")
  assert_contains "$body" "docs/loose.md"
  rm -rf "$d"
}

# Both optional branches empty -- the state this repo has always run in.
t_update_empty_categories() {
  local d; d=$(new_fixture)
  run_ds "$d" --update
  assert_eq "$RC" 0
  local body; body=$(cat "${d}/.claude/skills/doc-search/doc-search.md")
  assert_contains "$body" "### Features"
  assert_contains "$body" "### Other Documentation"
  rm -rf "$d"
}

# Catalogued paths must be loadable by the name the catalog prints.
t_update_output_is_loadable() {
  local d; d=$(new_fixture)
  mkdir -p "${d}/docs/features/checkout"
  printf '# Checkout\n\nCheckout body.\n' > "${d}/docs/features/checkout/feature.md"
  run_ds "$d" --update
  run_ds "$d" --load features/checkout/feature.md
  assert_contains "$OUT" "Checkout body."
  rm -rf "$d"
}

# --- load-baseline.sh -------------------------------------------------------

t_baseline_emits_policy_and_index() {
  local d; d=$(new_fixture)
  OUT=$(cd "$d" && ./.claude/skills/doc-search/load-baseline.sh --refs-only 2>&1); RC=$?
  assert_eq "$RC" 0
  assert_contains "$OUT" "## Project documentation (doc-search)"
  assert_contains "$OUT" "- **alpha.md**: Alpha"
  # refs-only means no document bodies
  assert_not_contains "$OUT" "More alpha body."
  rm -rf "$d"
}

t_baseline_missing_manifest() {
  local d; d=$(new_fixture)
  rm -f "${d}/.claude/skills/doc-search/doc-search.md"
  OUT=$(cd "$d" && ./.claude/skills/doc-search/load-baseline.sh --refs-only 2>&1); RC=$?
  assert_eq "$RC" 0
  assert_contains "$OUT" "manifest not found"
  rm -rf "$d"
}

t_baseline_multiple_docs() {
  local d; d=$(new_fixture)
  printf '# Doc Search\n\n## Baseline (loads on SessionStart)\n- alpha.md\n- beta.md\n\n## All Available Docs\n' \
    > "${d}/.claude/skills/doc-search/doc-search.md"
  OUT=$(cd "$d" && ./.claude/skills/doc-search/load-baseline.sh --refs-only 2>&1); RC=$?
  assert_contains "$OUT" "- **alpha.md**: Alpha"
  assert_contains "$OUT" "- **beta.md**: Beta"
  rm -rf "$d"
}

# --- run --------------------------------------------------------------------

echo "doc-search tests"
echo ""
echo "load:"
test_case "load exact filename"                t_load_exact
test_case "load without extension"             t_load_no_extension
test_case "load multiple docs"                 t_load_multiple
test_case "load --summary"                     t_load_summary
test_case "load --refs-only"                   t_load_refs_only
test_case "load missing doc warns"             t_load_missing
test_case "load without names errors"          t_load_requires_args
test_case "unknown option errors"              t_unknown_option
test_case "ambiguous name reports candidates"  t_ambiguous_name_reports
test_case "exact match beats ambiguity"        t_exact_beats_ambiguity
test_case "ambiguity does not block siblings"  t_ambiguous_does_not_block_siblings
echo ""
echo "analyze:"
test_case "preview does not write"             t_analyze_preview_does_not_write
test_case "--overwrite writes doc-needs.md"    t_analyze_overwrite_writes
test_case "keyword matching picks docs"        t_analyze_keyword_matching
test_case "no conditionals uses default"       t_analyze_no_conditionals_default_section
test_case "missing skill errors"               t_analyze_missing_skill
test_case "empty scans count as zero"          t_analyze_counts_empty_scans_as_zero
test_case "non-empty scans count correctly"    t_analyze_counts_real_scans
test_case "analyzing doc-search keeps manifest" t_analyze_doc_search_preserves_manifest
test_case "baseline survives analyze"          t_analyze_then_baseline_still_loads
echo ""
echo "update:"
test_case "preserves configured baseline"      t_update_preserves_baseline
test_case "defaults baseline when absent"      t_update_defaults_baseline_when_absent
test_case "catalogs standards"                 t_update_catalogs_standards
test_case "catalogs features"                  t_update_catalogs_features
test_case "catalogs other docs"                t_update_catalogs_other
test_case "empty categories do not break"      t_update_empty_categories
test_case "catalogued paths are loadable"      t_update_output_is_loadable
echo ""
echo "load-baseline:"
test_case "emits policy and index"             t_baseline_emits_policy_and_index
test_case "missing manifest is not fatal"      t_baseline_missing_manifest
test_case "multiple baseline docs"             t_baseline_multiple_docs

echo ""
echo "-----------------------------------"
echo "passed: $PASS   failed: $FAIL"
if [[ $FAIL -gt 0 ]]; then
  printf 'failing: %s\n' "${FAILED_NAMES[@]}"
  exit 1
fi
