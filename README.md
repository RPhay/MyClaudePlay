# MyClaudePlay

A sandbox for learning and sharing Claude skills — experiments in extending
Claude Code with skills, subagents, and hooks.

Everything here is meant to be borrowed. Each piece is self-contained enough to
copy into another repository.

---

## What's in here

### `doc-search` — skill + agent

A documentation system that answers questions from your `docs/` folder without
loading those documents into the session's context.

The problem it solves: project documentation is large, and a naive
"load the docs at startup" hook spends thousands of tokens every session on
documents most sessions never need. This repo's own docs total 40KB.

The approach: **load an index at startup, fetch content on demand, and do the
fetching in a subagent.**

```
session start   →  index of available docs (~1KB)  →  main context
question asked  →  subagent reads the docs         →  main context gets the answer
```

Full document text only ever exists in a Haiku subagent's context. Yours holds a
list of what exists, and answers after that.

---

## How it fits together

Four parts, each doing one thing:

| Part | File | Role |
|---|---|---|
| **Script** | `.claude/skills/doc-search/doc-search.sh` | All the actual work — finding, loading, cataloging docs |
| **Skill** | `.claude/skills/doc-search/SKILL.md` | `/doc-search` slash command; runs the script inline |
| **Agent** | `.claude/agents/doc-search.md` | Runs the script in a subagent and reports back distilled |
| **Hook** | `SessionStart` in `.claude/settings.json` | Emits the doc index and the delegation rules at startup |

One script, two callers. The agent doesn't carry its own copy — two copies of the
same 9.5KB script would drift silently.

### Three modes

```bash
/doc-search --load feature-structure,tech-stack   # fetch docs
/doc-search --update                              # rescan repo, rebuild manifest
/doc-search --analyze my-skill --overwrite        # generate a skill's doc needs
```

`--load` takes `--summary` (first paragraphs) or `--refs-only` (paths and
headings only).

Which caller to use depends on what the output is *for*:

- **`--load` through the agent** when you want an answer. The documents stay in
  the subagent.
- **`--load` through the skill** when you want the raw document text in your own
  context — editing it, quoting it verbatim.
- **`--update` / `--analyze` through the agent**, always. Their real product is a
  file on disk; the terminal output is scan chatter worth discarding.

### What makes delegation actually happen

Three layers, because each has different force:

1. **Agent description** — loads every session in the agent listing. This is the
   field Claude consults when deciding whether to route to an agent, so the
   "don't read `docs/` yourself" rule lives here.
2. **Hook output** — the full rules plus the doc index. Travels with the skill,
   so adopting repos get the behavior by installing the hook.
3. **One line in `CLAUDE.md`** — `CLAUDE.md` is loaded as instructions that
   override default behavior, which hook output is not. This is what gives the
   rules real force, particularly *wait for the agent's result before reporting
   it*.

Layers 1 and 2 are portable. Layer 3 is one line an adopter adds by hand — see
`SKILL.md` for the exact text.

---

## Installing doc-search elsewhere

See [`.claude/skills/doc-search/SKILL.md`](.claude/skills/doc-search/SKILL.md).
Short version: copy `.claude/skills/doc-search/` and
`.claude/agents/doc-search.md`, add the SessionStart hook, run `/doc-search
--update`, add the `CLAUDE.md` line.

---

## Repository layout

```
.claude/
├── settings.json                    SessionStart hook
├── settings.local.json              permissions (gitignored in most setups)
├── agents/
│   └── doc-search.md                the subagent
└── skills/
    └── doc-search/
        ├── SKILL.md                 slash-command definition + install guide
        ├── doc-search.sh            implementation
        ├── load-baseline.sh         SessionStart entry point
        ├── doc-search.md            manifest — baseline + catalog
        └── manifest.json            skill metadata
docs/
└── standards/
    ├── feature-structure.md
    ├── tech-stack.md
    └── uix.md
CLAUDE.md                            project instructions
CHANGELOG.md
```

### The `docs/standards/` content

These are the sample corpus doc-search operates on — they describe a separate
application project, and are here as realistic material to search against.

- **`feature-structure.md`** — a standardized system for documenting features:
  prescribed folder structures and file templates (feature, context, decisions,
  plan phases, requirements, resources) defining what each contains and when to
  update it.
- **`tech-stack.md`** — baseline technologies for Node.js/Express/MySQL
  applications: directory structure, development tooling (Jest, ESLint,
  Prettier), and common build and test scripts.
- **`uix.md`** — architecture for a generic entity rendering system where every
  entity type shares one engine for trees, rows, and editors, driven by schema
  definitions in the database rather than per-type implementations.

---

## Notes and limitations

- **Hook changes need a restart.** The settings watcher only picks up `.claude/`
  when a settings file was present at session start.
- **`SessionStart` cannot run an agent.** Agent hooks are available only for tool
  events (`PreToolUse`, `PostToolUse`, `PermissionRequest`). Startup is limited
  to `command` and `prompt` hooks — which is why the index is generated by a
  shell script rather than delegated.
- **Waiting for a subagent is an instruction, not a lock.** Nothing in the
  harness prevents Claude from proceeding on an assumption while an agent is
  still running. The `CLAUDE.md` line is the guard against that.

See [CHANGELOG.md](CHANGELOG.md) for what has changed.
