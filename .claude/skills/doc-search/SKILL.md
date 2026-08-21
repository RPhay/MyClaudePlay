# Doc Search

Discover, load, and manage project documentation efficiently.

## What It Does

Intelligently loads documentation from your repo based on what you're working on. Supports three modes: load, update, and analyze.

## Three Modes

### Load Mode (default)
Retrieve specific documentation with flexible output formats.

Run through the **agent** when you want an answer. Run `/doc-search` inline only
when you want the raw document text in your own context — editing it, quoting it
verbatim. Inline is an escape hatch, not a cheaper path: it puts the whole
document into your context, which is the cost the agent exists to avoid.

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
Auto-generate a `doc-needs.md` for a skill.

```bash
/doc-search --analyze my-skill
/doc-search --analyze my-skill --overwrite
```

Analyzes a skill's purpose and intelligently recommends which docs it needs.
Without `--overwrite` it only previews. The generated file is
`.claude/skills/<skill>/doc-needs.md` — deliberately not `doc-search.md`, which
inside this skill's own folder is the manifest.

## How It Works

**On SessionStart:**
- Loads baseline docs automatically (currently: feature-structure.md)
- Changes to baseline update on next session start

**When Skills Run:**
- Skills declare their doc needs in `doc-needs.md` files
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

**Install the agent.** It is the part that does the work — see "What actually
saves anything" below. The skill on its own is worth about 5%.

1. Copy `.claude/agents/doc-search.md` (**the agent — this is the one that
   matters**) and `.claude/skills/doc-search/`
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

3. Allow the scripts in that repo's `.claude/settings.json`, so adopters do not
   get a permission prompt on every lookup:

```json
"permissions": {
  "allow": [
    "Bash(./.claude/skills/doc-search/doc-search.sh:*)",
    "Bash(./.claude/skills/doc-search/load-baseline.sh:*)"
  ]
}
```

4. Run `/doc-search --update` to build the manifest from that repo's docs
5. Add one line to that repo's `CLAUDE.md`:

> Docs access: follow the `doc-search` rules emitted at session start — delegate
> `docs/` lookups to the `doc-search` agent, and wait for its actual result before
> acting on it. Never report that a doc-search operation ran, or what it found,
> before the result is in hand.

Steps 1–4 make it work; step 5 is what makes it stick. The hook's output is
context, which Claude weighs but is not bound by. CLAUDE.md is loaded as
instructions that override default behavior — so the one line is what gives the
rules real force, especially "wait for the result."

Hook changes need a session restart to take effect — the settings watcher only
picks up `.claude/` when a settings file was present at session start. A repo
that had no `.claude/settings.json` before you added one will not run the hook
until the next session.

## Tests

```bash
./tests/doc-search.test.sh            # all
./tests/doc-search.test.sh ambiguous  # filter by name
```

Each test builds a throwaway git repo under `$TMPDIR` and copies the real
scripts into it, so nothing touches the working repository.

## Configuration

Edit baseline docs in `./.claude/skills/doc-search/doc-search.md`:
- Look for "## Baseline" section
- Docs listed there load automatically on each session start

## What actually saves anything

Measured 2026-08-20 over a 20-turn session asking three documentation questions.
Full working in `CLAUDE-TODO.md`.

| Strategy | Cost | vs no system |
|---|---|---|
| No system — Claude greps and reads at whim | $0.1615 | 1.00x |
| Load every doc at SessionStart | $0.1970 | **0.82x — worse than nothing** |
| This skill **without** the agent | $0.1533 | **1.05x** |
| This skill **with** the agent | $0.0486 | **3.32x** |

**The agent is the system.** The index, the manifest, the script and the three
output formats — everything except the subagent — buy about 5% over letting
Claude read at whim. Installing the skill and skipping the agent gets you
essentially nothing. Do not do that.

Two further points the numbers make:

- **Loading documents at startup is worse than having no system**, because you
  pay for every document on every turn whether the session touches docs or not.
- **The real argument is context pressure, not money.** Delegating puts ~795
  tokens into the session instead of ~11,000. The dollar saving is around $0.11
  per session; the context saving is what matters, because context is a fixed
  budget you need for actual work.

The agent is pinned to Haiku 4.5 and that pin is load-bearing: delegation is
worth 5.38x on Haiku, 1.25x on Opus 5, and **0.64x on Fable 5** — above the Haiku
tier the subagent costs more than the context it saves. Do not change or override
the model without re-measuring.
