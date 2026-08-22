---
name: token-session-audit
description: Diagnoses a live or past session — how much context it holds, what filled it, every cache-invalidation event with its cause and cost in rewritten tokens, and what subagents spent. Attributes each invalidation to a model switch, a cache TTL expiry, or neither, straight from the transcript. Use when a session feels slow or expensive, before deciding between compacting and handing off, or to find out where a session's tokens actually went. Reports only.
allowed-tools: ["Read", "Glob", "Bash(python3:*)", "Bash(git:*)"]
disable-model-invocation: true
argument-hint: "[--session <id>] [--window <tokens>] [--json]"
---

# token-session-audit

Where a session's tokens went, from recorded counts rather than inference.

## Run it

```
python3 "$(git rev-parse --show-toplevel)/.claude/skills/token-session-audit/scripts/session.py" --root "$PWD"
```

Defaults to the most recently modified transcript for this project — normally the
current session. `--session <id>` picks another. `--window <tokens>` enables
percentage-of-window statements; **without it the report makes none**, because
the context window size is not recorded in the transcript and guessing it would
put a fabricated denominator under every percentage.

**If the command cannot run, report that and stop.** Do not reconstruct token
counts by reading the conversation. A hand-built figure is indistinguishable from
a recorded one and is not one.

## Reading the report

**OCCUPANCY** is recorded, not estimated: per-request
`input + cache_read + cache_creation`, deduplicated by `requestId`. Skipping that
dedupe inflates totals by roughly 2.2x.

**CACHE INVALIDATION** is the section that usually matters. A rebuilt prefix is
charged as a cache write at 2.0x, so a single invalidation late in a long session
can cost more than the work that session did. Each event is attributed from the
record itself: a change in `message.model`, a timestamp gap past the 1-hour TTL,
or `unattributed` when neither explains it. Nothing is guessed — if the cause is
not in the data it says so.

**LARGEST CONTEXT ADDITIONS** ranks by measured bytes; the token column is an
estimate at 3.6 chars/token and is labelled as such.

**SUBAGENTS** reports cache writes, reads and output per agent type, and what
they returned into the main context. It deliberately stops short of a verdict:
subagent cost is a one-time write, while text kept out of context would have been
re-read at 0.1x on every remaining turn, so the comparison needs session length
and document size. The crossover model in `CLAUDE-TODO.md` does that arithmetic.

## What to do with each finding

| Finding | Action |
|---|---|
| Invalidation from a model switch | Choose a model at session start. Switching rewrites the entire prefix — measured at 335,084 and 425,569 tokens in one local session |
| Invalidation from TTL expiry | The prefix does not survive a long break. Finish the thread, or run `session-handoff` and resume fresh |
| A single tool result dominating | Narrow the read, or delegate it so its text never enters this context |
| Context large and the task continuing | `session-handoff`, then `/clear`. Compaction re-reads everything to summarise it and keeps conclusions while dropping the reasoning |
| Context large and the task finished | `/clear` |

## Why it has no --apply

A session's history is not editable. Everything actionable is a change to how the
next session is run, which is `session-handoff`'s job.
