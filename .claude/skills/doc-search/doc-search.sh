#!/bin/bash

set -euo pipefail

# Doc Search Skill - Discover and load project documentation
# Runs as a Claude Code skill/subagent

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
DOCS_DIR="${REPO_ROOT}/docs"
CLAUDE_DIR="${REPO_ROOT}/.claude"
MANIFEST="${CLAUDE_DIR}/doc-search.md"

# Parse arguments
MODE="load"
DOCS=""
OUTPUT_FORMAT="full"
ANALYZE_SKILL=""
OVERWRITE=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --load)
      MODE="load"
      DOCS="$2"
      shift 2
      ;;
    --analyze)
      MODE="analyze"
      ANALYZE_SKILL="$2"
      shift 2
      ;;
    --update)
      MODE="update"
      shift
      ;;
    --summary)
      OUTPUT_FORMAT="summary"
      shift
      ;;
    --refs-only)
      OUTPUT_FORMAT="refs"
      shift
      ;;
    --overwrite)
      OVERWRITE=true
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# Helper: Find a document file by name
find_doc() {
  local name="$1"
  local found=""

  # Search in docs directory with exact match
  if [[ -f "${DOCS_DIR}/${name}" ]]; then
    echo "${DOCS_DIR}/${name}"
    return 0
  fi

  # Search for file with .md extension if not provided
  if [[ ! "${name}" =~ \.md$ ]]; then
    if [[ -f "${DOCS_DIR}/${name}.md" ]]; then
      echo "${DOCS_DIR}/${name}.md"
      return 0
    fi
  fi

  # Recursive search in docs directory
  found=$(find "${DOCS_DIR}" -name "*${name}*" -type f 2>/dev/null | head -1)
  if [[ -n "$found" ]]; then
    echo "$found"
    return 0
  fi

  return 1
}

# Helper: Get file summary (first paragraph + metadata)
get_summary() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    return 1
  fi

  echo "File: $file"
  echo "Size: $(wc -c < "$file") bytes"
  echo "---"
  # Extract first paragraph or first 5 lines
  head -20 "$file" | sed '/^$/q'
}

# Mode: Load documentation
load_docs() {
  local docs_list="$1"
  local format="$2"

  IFS=',' read -ra DOC_ARRAY <<< "$docs_list"

  case "$format" in
    full)
      for doc in "${DOC_ARRAY[@]}"; do
        doc=$(echo "$doc" | xargs)  # trim whitespace
        if doc_path=$(find_doc "$doc"); then
          echo "### Document: $doc"
          echo ""
          cat "$doc_path"
          echo ""
          echo "---"
          echo ""
        else
          echo "Warning: Document not found: $doc" >&2
        fi
      done
      ;;
    summary)
      for doc in "${DOC_ARRAY[@]}"; do
        doc=$(echo "$doc" | xargs)
        if doc_path=$(find_doc "$doc"); then
          get_summary "$doc_path"
          echo ""
        else
          echo "Warning: Document not found: $doc" >&2
        fi
      done
      ;;
    refs)
      for doc in "${DOC_ARRAY[@]}"; do
        doc=$(echo "$doc" | xargs)
        if doc_path=$(find_doc "$doc"); then
          echo "- **$doc**: $(grep -m1 '^#' "$doc_path" 2>/dev/null | sed 's/^# //')"
        else
          echo "Warning: Document not found: $doc" >&2
        fi
      done
      ;;
  esac
}

# Mode: Analyze a skill and generate doc-search.md
analyze_skill() {
  local skill_name="$1"
  local skill_dir="${CLAUDE_DIR}/skills/${skill_name}"
  local overwrite="${OVERWRITE:-false}"

  if [[ ! -d "$skill_dir" ]]; then
    echo "Error: Skill not found: $skill_name" >&2
    exit 1
  fi

  echo "Analyzing skill: $skill_name"
  echo ""

  # Read skill metadata
  local description=""
  local skill_keywords=""

  if [[ -f "${skill_dir}/manifest.json" ]]; then
    description=$(jq -r '.description // ""' "${skill_dir}/manifest.json" 2>/dev/null || true)
  fi

  # Extract keywords from skill name and description
  skill_keywords="${skill_name} ${description}"
  skill_keywords=$(echo "$skill_keywords" | tr '[:upper:]' '[:lower:]')

  echo "Skill description: $description"
  echo "Keywords: $skill_keywords"
  echo ""

  # Scan repo for available docs
  echo "Scanning repo for documentation..."
  local standards_docs=$(find "${DOCS_DIR}/standards" -name "*.md" -type f 2>/dev/null | xargs -I {} basename {} | sort)
  local features=$(find "${DOCS_DIR}/features" -maxdepth 1 -type d | tail -n +2 | xargs -I {} basename {})
  echo "Found $(echo "$standards_docs" | wc -l) standard docs"
  echo "Found $(echo "$features" | wc -l) features"
  echo ""

  # Build intelligent recommendations
  local recommended_docs=()
  local conditional_docs=()

  # Always include standards
  recommended_docs+=("docs/standards/feature-structure.md")
  recommended_docs+=("docs/standards/tech-stack.md")

  # Pattern matching for special keywords
  if echo "$skill_keywords" | grep -qi "feature\|implement"; then
    recommended_docs+=("docs/standards/uix.md")
    conditional_docs+=("docs/features/[feature-name]/feature.md")
    conditional_docs+=("docs/features/[feature-name]/context.md")
    conditional_docs+=("docs/features/[feature-name]/requirements.md")
  fi

  if echo "$skill_keywords" | grep -qi "deploy\|release\|build\|ship"; then
    conditional_docs+=("deployment-docs/deploy-process.md")
    conditional_docs+=("deployment-docs/environments.md")
  fi

  if echo "$skill_keywords" | grep -qi "test\|spec\|validation"; then
    conditional_docs+=("docs/standards/test-standards.md")
    conditional_docs+=("docs/features/[feature-name]/plan-current.md")
  fi

  if echo "$skill_keywords" | grep -qi "bug\|fix\|issue"; then
    conditional_docs+=("docs/features/[feature-name]/bugs/")
    conditional_docs+=("docs/features/[feature-name]/plan-current.md")
  fi

  if echo "$skill_keywords" | grep -qi "enhance\|add\|improve"; then
    conditional_docs+=("docs/features/[feature-name]/enhancements/")
    conditional_docs+=("docs/features/[feature-name]/plan-phases.md")
  fi

  if echo "$skill_keywords" | grep -qi "status\|report\|check"; then
    conditional_docs+=("docs/features/[feature-name]/plan-current.md")
    conditional_docs+=("docs/features/[feature-name]/feature.md")
  fi

  # Generate doc-search.md content
  local output_file="${skill_dir}/doc-search.md"
  local temp_file=$(mktemp)

  cat > "$temp_file" << 'EOF'
# Doc Search: [SKILL_NAME]

Documents this skill needs to function effectively.

## Always Load

EOF

  # Add always-load docs
  for doc in "${recommended_docs[@]}"; do
    echo "- $doc" >> "$temp_file"
  done

  # Add conditional docs if any
  if [[ ${#conditional_docs[@]} -gt 0 ]]; then
    cat >> "$temp_file" << 'EOF'

## Conditional Loading

EOF
    for doc in "${conditional_docs[@]}"; do
      echo "- $doc" >> "$temp_file"
    done
  else
    cat >> "$temp_file" << 'EOF'

## Conditional Loading

### When working with a specific feature
- docs/features/[feature-name]/feature.md
- docs/features/[feature-name]/context.md
- docs/features/[feature-name]/plan-current.md

EOF
  fi

  # Replace placeholder
  sed -i '' "s/\[SKILL_NAME\]/$skill_name/" "$temp_file"

  # Show what will be written
  echo "Generated doc-search.md:"
  echo "---"
  cat "$temp_file"
  echo "---"
  echo ""

  if [[ "$overwrite" == "true" ]]; then
    mv "$temp_file" "$output_file"
    echo "✓ Written to: $output_file"
  else
    echo "Preview generated. To write, run:"
    echo "  /doc-search --analyze $skill_name --overwrite"
    rm "$temp_file"
  fi
}

# Mode: Update global manifest
update_manifest() {
  echo "Scanning repository for documentation..."
  echo ""

  local manifest_file="${CLAUDE_DIR}/skills/doc-search/doc-search.md"
  local temp_manifest=$(mktemp)

  # Preserve the configured baseline -- this rewrites the whole manifest, so
  # without this the user's SessionStart selection is lost on every --update.
  local existing_baseline=""
  if [[ -f "$manifest_file" ]]; then
    existing_baseline=$(sed -n '/^## Baseline/,/^## /p' "$manifest_file" | grep "^- " || true)
  fi
  if [[ -z "$existing_baseline" ]]; then
    existing_baseline="- feature-structure.md"
  fi

  cat > "$temp_manifest" << 'EOF'
# Doc Search

Discover, load, and manage project documentation efficiently.

## Modes

### Load Mode (default)
Load specific documentation based on skill needs.

```bash
/doc-search --load feature-structure,tech-stack
```

### Generate Mode
Analyze a skill and auto-generate its `doc-search.md` file.

```bash
/doc-search --analyze my-skill --overwrite
```

### Update Mode
Scan entire repository for documentation and update this manifest.

```bash
/doc-search --update
```

---

# Manifest

## Baseline (loads on SessionStart)
EOF

  echo "$existing_baseline" >> "$temp_manifest"

  cat >> "$temp_manifest" << 'EOF'

## All Available Docs

### Standards
EOF

  # Find all .md files in docs/standards
  if [[ -d "${DOCS_DIR}/standards" ]]; then
    find "${DOCS_DIR}/standards" -name "*.md" -type f | sort | while read -r file; do
      rel_path="${file#${REPO_ROOT}/}"
      echo "- ${rel_path}" >> "$temp_manifest"
    done
  fi

  cat >> "$temp_manifest" << 'EOF'

### Features
EOF

  # Find all feature folders
  if [[ -d "${DOCS_DIR}/features" ]]; then
    find "${DOCS_DIR}/features" -name "*.md" -type f | sort | while read -r file; do
      rel_path="${file#${REPO_ROOT}/}"
      echo "- ${rel_path}" >> "$temp_manifest"
    done
  fi

  cat >> "$temp_manifest" << 'EOF'

### Other Documentation
EOF

  # Find other .md files not in standards or features
  find "${DOCS_DIR}" -maxdepth 1 -name "*.md" -type f | sort | while read -r file; do
    rel_path="${file#${REPO_ROOT}/}"
    echo "- ${rel_path}" >> "$temp_manifest"
  done

  # Move temp file to manifest location
  mkdir -p "$(dirname "$manifest_file")"
  mv "$temp_manifest" "$manifest_file"

  echo "Updated manifest: $manifest_file"
  echo ""
  echo "Contents:"
  cat "$manifest_file"
}

# Main dispatch
case "$MODE" in
  load)
    if [[ -z "$DOCS" ]]; then
      echo "Error: --load requires document names" >&2
      exit 1
    fi
    load_docs "$DOCS" "$OUTPUT_FORMAT"
    ;;
  analyze)
    if [[ -z "$ANALYZE_SKILL" ]]; then
      echo "Error: --analyze requires skill name" >&2
      exit 1
    fi
    analyze_skill "$ANALYZE_SKILL"
    ;;
  update)
    update_manifest
    ;;
  *)
    echo "Error: Unknown mode: $MODE" >&2
    exit 1
    ;;
esac
