# Doc Search

Discover, load, and manage project documentation efficiently.

## What It Does

Intelligently loads documentation from your repo based on what you're working on. Supports three modes: load, update, and analyze.

## Three Modes

### Load Mode (default)
Retrieve specific documentation with flexible output formats.

```bash
/doc-search --load feature-structure,tech-stack
/doc-search --load deployment-docs --summary
/doc-search --load standards/uix --refs-only
```

Output options:
- `--load docs` → full content (default)
- `--load docs --summary` → summaries + metadata
- `--load docs --refs-only` → references only (paths + headings)

### Update Mode
Scan entire repository and refresh the documentation manifest.

```bash
/doc-search --update
```

Discovers all docs and updates the manifest with:
- Baseline (what loads on SessionStart)
- Full catalog organized by category

### Analyze Mode
Auto-generate documentation manifests for skills.

```bash
/doc-search --analyze my-skill
/doc-search --analyze my-skill --overwrite
```

Analyzes a skill's purpose and intelligently recommends which docs it needs.

## How It Works

**On SessionStart:**
- Loads baseline docs automatically (currently: feature-structure.md)
- Changes to baseline update on next session start

**When Skills Run:**
- Skills declare their doc needs in `doc-search.md` files
- Skills call `/doc-search --load docs1,docs2` to load them
- Doc-search returns docs in the requested format

**Keep Manifest Updated:**
```bash
/doc-search --update
```

## Examples

Check documentation:
```bash
/doc-search --load feature-structure.md --summary
```

Load multiple docs for feature work:
```bash
/doc-search --load feature-structure,tech-stack,uix,features/my-feature/feature
```

Auto-generate docs for a new skill:
```bash
/doc-search --analyze my-new-skill --overwrite
```

## Installing in another repo

Self-contained — no CLAUDE.md changes needed.

1. Copy `.claude/skills/doc-search/` and `.claude/agents/doc-search.md`
2. Add the SessionStart hook to `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "./.claude/skills/doc-search/load-baseline.sh --refs-only 2>/dev/null || true",
        "statusMessage": "Loading baseline documentation..."
      }]
    }]
  }
}
```

3. Run `/doc-search --update` to build the manifest from that repo's docs
4. Add one line to that repo's `CLAUDE.md`:

> Docs access: follow the `doc-search` rules emitted at session start — delegate
> `docs/` lookups to the `doc-search` agent, and wait for its actual result before
> acting on it. Never report that a doc-search operation ran, or what it found,
> before the result is in hand.

Steps 1–3 make it work; step 4 is what makes it stick. The hook's output is
context, which Claude weighs but is not bound by. CLAUDE.md is loaded as
instructions that override default behavior — so the one line is what gives the
rules real force, especially "wait for the result."

## Configuration

Edit baseline docs in `./.claude/skills/doc-search/doc-search.md`:
- Look for "## Baseline" section
- Docs listed there load automatically on each session start

## Token Efficiency

- SessionStart loads only what's essential (baseline)
- Skills load only what they need, when they need it
- Flexible output formats minimize context bloat
