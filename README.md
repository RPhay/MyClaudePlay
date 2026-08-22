# MyClaudePlay

A sandbox for learning and sharing Claude skills — experiments in extending
Claude Code with skills, subagents, and hooks.

Two things live here. **`doc-search`** answers questions from `docs/` without
loading the documents into your context. **Nine token-optimization skills**
measure what a repo and a session actually cost, and fix what is safely fixable.

Everything here is meant to be borrowed. Each piece is self-contained enough to
copy into another repository.

---

## What's in here

### `doc-search` — skill + agent

A documentation system that answers questions from your `docs/` folder without
loading those documents into the session's context.

The problem it solves: context is a fixed budget you need for actual work, and
documentation crowds it out. Letting Claude grep and read at whim puts ~11,000
tokens of documents into a 20-turn session. Delegating puts ~795. This repo's own
docs total 40KB.

There is a cost saving too, but it is the weaker argument — about $0.11 a
session. Context pressure is the reason.

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

**The agent is the part that matters.** Measured over a 20-turn session asking
three documentation questions:

| Strategy | Cost | vs no system |
|---|---|---|
| No system — Claude greps and reads at whim | $0.1615 | 1.00x |
| Load every doc at SessionStart | $0.1970 | **0.82x — worse than nothing** |
| Skill without the agent | $0.1533 | **1.05x** |
| Skill with the agent | $0.0486 | **3.32x** |

Everything except the subagent — index, manifest, script, output formats — buys
about 5%. Copying the skill without the agent gets you almost nothing. The
startup-load approach is actively negative: you pay for every document on every
turn whether the session touches docs or not.

The agent is pinned to Haiku 4.5, and that pin is load-bearing — delegation is
worth 5.38x on Haiku, 1.25x on Opus 5, and **0.64x on Fable 5**, where the
subagent costs more than the context it saves. Working in
[CLAUDE-TODO.md](CLAUDE-TODO.md).

### Three modes

```bash
/doc-search --load feature-structure,tech-stack   # fetch docs
/doc-search --update                              # rescan repo, rebuild manifest
/doc-search --analyze my-skill --overwrite        # generate a skill's doc-needs.md
```

`--load` takes `--summary` (first paragraphs) or `--refs-only` (paths and
headings only).

Which caller to use depends on what the output is *for*:

- **`--load` through the agent** when you want an answer. The documents stay in
  the subagent.
- **`--load` through the skill** when you want the raw document text in your own
  context — editing it, quoting it verbatim. This is an escape hatch, not a
  cheaper path; it puts the whole document into your context.
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
Short version: copy `.claude/agents/doc-search.md` (**the agent — the part that
carries the value**) and `.claude/skills/doc-search/`, add the SessionStart hook
and the script permissions, run `/doc-search --update`, add the `CLAUDE.md` line.

The permission rules live in the committed `.claude/settings.json` rather than a
gitignored `settings.local.json`, so a clone works without each person adding
them by hand. That does mean the repo asks for a trust decision it would
otherwise leave to the individual — a deliberate trade for a skill meant to be
copied.

---

## Token-optimization skills

Nine skills that answer "what is this costing me, and what can I do about it."

They came out of auditing five published community skill collections. Four of the
five advertise token savings with no measurement behind them — one ships a hook
that computes `SAVED_TOKENS=$(( (TOOL_CALLS * 1000) + 5000 ))` and prints the
product to the user as a measurement. The fifth built a real benchmark, and its
own README records that its published headline did not reproduce.

So there is one rule, and it drives every design decision here: **every figure
traces to data on this machine, and a measured number is never mixed with an
estimate in the same figure.**

| Skill | Reports | `--apply` |
|---|---|---|
| `claude-md-audit` | The `CLAUDE.md` import graph and its per-turn cost; dead, unreachable and accidental imports | fixes them |
| `skill-lint` | `SKILL.md` conformance and what each skill costs in listing tokens | fixes frontmatter |
| `token-overhead-audit` | Fixed per-turn cost of the setup, and how much is not yours to control | — |
| `token-layout-audit` | What the codebase's shape costs when Claude explores it | writes `.claudeignore` |
| `token-session-audit` | Where a session's tokens went; every cache invalidation with its cause | — |
| `token-history` | Cost across every recorded session; detects when fixed overhead changed | — |
| `token-benchmark` | Controlled A/B over `claude -p`. The falsification layer | — |
| `session-handoff` | — | writes a handoff so you can `/clear` instead of compacting |
| `doc-index` | `docs/` coverage and staleness | writes `docs/INDEX.md` |

All are slash-command only. `disable-model-invocation: true` was measured to
remove a skill from the listing entirely — a control session totalled 9,513
prompt tokens, adding a skill made it 9,546, and the flag returned it to 9,513
exactly. Nine skills, zero always-on cost.

### What was measured

Not assumed, not read from documentation. The full record with method and
caveats is in [CLAUDE-TODO.md](CLAUDE-TODO.md); the load-bearing ones:

- **25 rules for how the `CLAUDE.md` graph loads.** Imports are transitive to a
  minimum of 4 hops and silently stop at 5. Relative paths resolve against the
  *importing file*, not the project root. The ancestor walk has no boundary and
  does not stop at the git root — a `CLAUDE.md` above a project loads into every
  project beneath it. An `@file.md` mid-sentence in prose is a live import.
- **`allowed-tools` in a `SKILL.md` grants nothing and restricts nothing**, in
  both `-p` and interactive mode. The permission dialog is the only real control,
  which is why no skill here writes files through Bash.
- **A skill's identity is its directory name**, not its `name` field.
- **Cache invalidation dominates.** In one local session four events rewrote
  1,365,798 tokens — 77% of all cache writes — from two model switches and two
  TTL expiries.

### Running them

```bash
python3 .claude/skills/<skill>/scripts/<script>.py --root "$PWD"
```

Or as slash commands: `/claude-md-audit`, `/skill-lint --apply`, and so on. Each
skill refuses to hand-read its inputs if its script cannot run — a hand-built
figure is indistinguishable from a measured one and is not one.

---

## Repository layout

```
.claude/
├── settings.json                    SessionStart hook + script permissions
├── agents/
│   └── doc-search.md                the subagent
└── skills/
    ├── doc-search/
    │   ├── SKILL.md                 slash-command definition + install guide
    │   ├── doc-search.sh            implementation
    │   ├── load-baseline.sh         SessionStart entry point
    │   ├── doc-search.md            manifest — baseline + catalog
    │   └── manifest.json            skill metadata
    ├── claude-md-audit/             CLAUDE.md graph, its cost and its defects
    ├── skill-lint/                  SKILL.md conformance + listing cost
    ├── token-overhead-audit/        fixed per-turn cost of the setup
    ├── token-layout-audit/          what the codebase's shape costs
    ├── token-session-audit/         where a session's tokens went
    ├── token-history/               cost across every recorded session
    ├── token-benchmark/             controlled A/B — the falsification layer
    ├── session-handoff/             end a session instead of compacting it
    └── doc-index/                   docs/ coverage + INDEX.md
docs/
├── INDEX.md                         generated by doc-index
└── standards/
    ├── feature-structure.md
    ├── tech-stack.md
    └── uix.md
tests/
├── unit/doc-search.test.sh          29 cases, free
├── unit/skills.test.py              52 cases, free
└── bench/                           paid — real sessions, real token counts
CLAUDE.md                            project instructions
CLAUDE-TODO.md                       open work, and every measurement behind it
CHANGELOG.md
LICENSE                              MIT
```

Each token-optimization skill holds a `SKILL.md`, a `scripts/` directory whose
source never enters context, and — where the detail earns it — a `references/`
file read only when a result needs explaining.

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
- **`--analyze` uses BSD `sed -i ''`.** It will fail on GNU sed. macOS only for
  now.
- **A skill's generated file is `doc-needs.md`.** Not `doc-search.md`, which
  inside `skills/doc-search/` is the manifest. Writing there destroyed it.

See [CHANGELOG.md](CHANGELOG.md) for what has changed.
