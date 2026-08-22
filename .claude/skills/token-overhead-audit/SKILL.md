---
name: token-overhead-audit
description: Accounts for the fixed context cost a repo imposes on every turn before any work happens. Sizes each component that lands in the cached prefix — SessionStart hook output, the skill listing, deferred tool blocks, the agent listing, MCP server instructions and the CLAUDE.md roots — from this project's transcripts, then sets the total against the measured static-prefix baseline and states how much is unaccounted for. Use when a repo feels expensive from the first turn, when setting one up, or before adding hooks, skills or MCP servers. Reports only; fixes live in skill-lint and claude-md-audit.
allowed-tools: ["Read", "Glob", "Bash(python3:*)", "Bash(git:*)"]
disable-model-invocation: true
argument-hint: "[--root <dir>] [--json]"
---

# token-overhead-audit

What this repo charges you on every turn, before you ask it anything.

## Run it

```
python3 "$(git rev-parse --show-toplevel)/.claude/skills/token-overhead-audit/scripts/overhead.py" --root "$PWD"
```

**If that command cannot run — Bash denied, python3 missing, script not found —
report that and stop.** Do not size the components by hand. A hand-built estimate
is indistinguishable from a measured one and is not one.

## Reading the report

**MEASURED** is the static prefix baseline: the floor of
`cache_read_input_tokens` across this project's transcripts, deduplicated by
`requestId`. It is the whole fixed prefix, and it is the only hard number here.

**COMPONENTS** are sized from `attachment` records in those same transcripts —
real observed payloads, converted to tokens at 3.6 chars/token. That ratio is
measured but derived from one sample, so treat component figures as estimates and
the baseline as fact.

**`unaccounted`** is the baseline minus everything identified: the system prompt
and tool schemas, which you do not control. Expect it to dominate. On a clean
repo it runs near 75%, and that is the honest headline — most of your fixed cost
is not yours to optimise, and a skill that implied otherwise would be lying.

If `accounted` ever exceeds the baseline, the estimate is wrong and the report
says so. Believe the baseline.

**PER TURN, NOT CACHED** is separate because it is re-sent rather than cached, so
its cost scales with turn count rather than sitting in the prefix once.

## What to do about each finding

| Finding | Where the fix lives |
|---|---|
| Many skills in the listing | `skill-lint` — `disable-model-invocation: true` removes a skill from the listing entirely, measured at exactly zero always-on cost |
| Large `CLAUDE.md` roots | `claude-md-audit` — it resolves the full import graph, which this skill only samples at the roots |
| A hook emitting large output every session | Yours. Nothing here edits hooks |
| MCP instructions you do not use | Yours. Disconnect the server |

## Why this one has no --apply

Every fix it could make belongs to another skill or to a config file that is
yours to own. Duplicating `skill-lint`'s frontmatter edits here would create two
tools that fix the same defect differently — which is the `plan` versus
`planning` overlap this set exists to avoid. It reports; you decide; the other
skills act.

## Reference

`references/accounting.md` covers where each component figure comes from, and
what the accounting cannot see.
