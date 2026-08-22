---
name: session-handoff
description: Writes a dense handoff document so a long session can be ended and resumed in a fresh one instead of compacted. Captures decisions and the reasons behind them, alternatives that were rejected and why, verified facts with pointers to where they are recorded, exact repo state, open questions, and the precise next action. Use when a session is large, before /clear, when stopping for the day, or when handing work to someone else. Compaction re-reads the whole context to summarise it and loses the reasoning; this does not.
allowed-tools: ["Read", "Glob", "Grep", "Bash(python3:*)", "Bash(git:*)", "Bash(date:*)", "Write", "Edit"]
disable-model-invocation: true
argument-hint: "[--out <path>]"
---

# session-handoff

## Why this exists rather than compacting

Compaction re-reads the entire context to produce a summary, and a summary keeps
conclusions while dropping the reasoning that produced them. What makes a session
resumable is not what was decided but *why*, and what was already ruled out.

A session measured locally peaked at 351,751 tokens. Restarting from a good
handoff costs a fresh baseline of roughly 25,000. The saving is not the point —
the point is that the next session starts with the reasoning intact instead of a
lossy précis of it.

## Gather the facts first

```
python3 "$(git rev-parse --show-toplevel)/.claude/skills/session-handoff/scripts/state.py" --root "$PWD"
```

This supplies what you should not have to remember: peak context, request count,
every file actually written this session, commands run, subagents spawned, branch,
uncommitted paths, recent commits.

**If it cannot run, say so and write the handoff anyway** from what you know —
but mark the repo-state section as unverified. This skill degrades usefully; the
audit skills do not, which is why they stop instead.

## Write the document

Default path `.claude/handoff/<YYYY-MM-DD>-<short-slug>.md`, or `--out <path>`.
Note that `.claude/` writes are gated behind a permission separate from ordinary
file writes; if declined, say the document is prepared and awaiting approval.

Use exactly these sections.

```markdown
# Handoff: <one-line objective>

## Objective
What we are trying to achieve, in two sentences. Not what was done — what for.

## Decisions, and why
- <decision> — because <reason>. <what it rules out>
Reasons are the part compaction loses. A decision without its reason will be
relitigated in the next session.

## Rejected, and why
- <alternative> — rejected because <reason>
Without this the next session re-proposes what was already dismissed.

## Verified facts
- <fact> — recorded in <file>
Point at durable records. Do NOT restate their contents; if something is only in
this document, it was not persisted properly and should be written down first.

## Repo state
Branch, uncommitted paths, relevant recent commits, files written this session.
Straight from state.py.

## Open questions
- <question> — blocked on <what>, or: unresolved, needs <test/decision>
Mark which are blocking and which are not.

## Next action
One concrete action. Not a list, not a direction — the single thing to do first,
specific enough to start without rereading anything above.
```

## Rules

1. **Reasons, not just outcomes.** "Chose per-file batching" is useless. "Chose
   per-file batching because prompts are per tool call and eleven dialogs makes a
   user click *don't ask again*" survives.
2. **Point at records, do not copy them.** If findings live in a TODO or a
   reference file, cite the path. A handoff that restates them will drift out of
   sync with the file that owns them.
3. **Anything unverified must say so.** Carrying a guess forward as though it were
   established is the one failure that makes a handoff worse than nothing.
4. **One next action.** A list of five is a session that has not decided.
5. **Do not summarise the conversation.** The transcript already exists. Write
   what a competent stranger needs to continue, not a narrative of what happened.
