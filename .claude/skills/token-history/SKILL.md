---
name: token-history
description: Longitudinal token cost across every recorded session for a project — per-session peak context, static baseline, cache writes and reads, output, cache-read ratio, and cache-invalidation events with their causes. Its most useful signal is a moving static baseline, which means the repo's fixed overhead changed. --all compares every project on the machine. Use to see whether an optimisation held up in real work, or to find which project is actually expensive. Reports only.
allowed-tools: ["Read", "Glob", "Bash(python3:*)", "Bash(git:*)"]
disable-model-invocation: true
argument-hint: "[--all] [--price-in <usd/1M>] [--price-out <usd/1M>] [--json]"
---

# token-history

The observational counterpart to `token-benchmark`. That one shows whether a
change helps under controlled conditions; this shows what actually happened over
real work.

## Run it

```
python3 "$(git rev-parse --show-toplevel)/.claude/skills/token-history/scripts/history.py" --root "$PWD"
```

`--all` lists every project on the machine by cache writes, which answers "where
is the money going" in one pass. `--price-in` and `--price-out` add a rough
dollar column; omit them and no cost claim is made.

**If the command cannot run, report that and stop.** Do not reconstruct history
from memory.

## The column that matters

**`baseline`** is the floor of `cache_read_input_tokens` for that session — the
static prefix: system prompt, tool schemas, listings, instruction graph. It should
be flat across sessions.

**When it moves, the repo's fixed overhead changed.** A skill was added, a hook
started emitting more, an MCP server was connected, `CLAUDE.md` grew. That is the
one thing this report can detect which nothing else can, because it needs sessions
separated in time to be visible at all. It detects the change; it does not
diagnose it — run `token-overhead-audit` for that.

## Reading the rest

**Cache reads dwarf writes** and should. The whole prefix is re-read every turn,
so reads accumulate with turn count. They bill at roughly 0.1x against writes at
2.0x on the 1-hour TTL, so the two token counts are not comparable as they stand.
The report says so rather than letting a large number imply a large bill.

**`busts`** counts cache invalidations by attributed cause — model switch, TTL
expiry, or unattributed. A session that never invalidated shows `-`.

**Sessions are not comparable to each other.** They differ in length, task and
model. A rise between two sessions is not evidence that anything got worse; it is
usually evidence that the second session was bigger. The report states this and
you should repeat it rather than reading a trend into four rows.

## What it cannot do

Attribute cause. Every column is confounded by what the session was for. If you
need to know whether a change helped, run `token-benchmark`, which controls for
the task by holding the prompts fixed.

It also cannot see sessions run with `--no-session-persistence`, including every
run made by `token-benchmark` itself. That is deliberate: benchmarking does not
pollute the history it would otherwise distort.

## No --apply

History is a record. Nothing here is editable, and every action it might suggest
belongs to `token-overhead-audit`, `skill-lint`, or `session-handoff`.
