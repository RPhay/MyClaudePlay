---
name: token-layout-audit
description: Reports what a codebase's shape costs Claude when it explores. The measured half comes from this project's transcripts — files that actually hit the Read token cap, and what reading each file actually returned. The inferred half is filesystem heuristics: files large enough to truncate if read whole, wide directories, and heavy trees a missing or incomplete .claudeignore does not cover. Use when exploration feels expensive, when onboarding a repo, or before adding generated directories. --apply writes .claudeignore entries only.
allowed-tools: ["Read", "Glob", "Grep", "Bash(python3:*)", "Bash(git:*)", "Edit", "Write"]
disable-model-invocation: true
argument-hint: "[--apply] [--root <dir>] [--json]"
---

# token-layout-audit

## Run it

```
python3 "$(git rev-parse --show-toplevel)/.claude/skills/token-layout-audit/scripts/layout.py" --root "$PWD"
```

**If the command cannot run, report that and stop.** Do not size the tree by hand.

`--apply` is an argument to this skill, not to the script. `layout.py` only reports.

## The two halves are not equally trustworthy

**MEASURED** comes from transcript records. Files listed as having hit the Read
cap really did: the cap value itself is read out of the truncation notice rather
than assumed, so it stays correct if the cap ever changes. The most-read table is
bytes actually returned by `Read`, so it shows what exploration really cost in
this repo, not what it might cost.

**INFERRED** is a filesystem guess about files that may never be read at all. A
large file nothing ever opens costs nothing. Treat this half as a prompt to look,
never as a defect list — and say which half a number came from when you quote it.

Binary files are excluded from both. A bytes-per-token estimate is meaningless for
a PNG, and images are not read as text.

## Decision table

| Finding | Action | Class |
|---|---|---|
| Heavy trees present with no `.claudeignore` | Create one covering them | 1 |
| `.claudeignore` missing a heavy tree that exists | Add the entry | 1 |
| A file that actually truncated | Read it by section with `offset`/`limit`, or split it. This is measured — it already cost you | 3 |
| A file large enough to truncate but never read | Note it. Do nothing unless it is about to be read | 3 |
| Wide directory | Editorial. Fan-out only matters if something globs it | 3 |

## --apply

Class 1 only, and class 1 here is exclusively `.claudeignore` entries.

1. **Batch into one write.** All entries at once, so the permission dialog shows
   one coherent diff. Prompts are per tool call.
2. **Never modify a file through Bash.** `Edit`/`Write` render a diff in the
   dialog; `sed -i` and redirection bypass it. `allowed-tools` grants nothing and
   restricts nothing, so the dialog is the only real control.
3. **Never add an entry for a directory that does not exist.** Speculative ignore
   rules are noise, and the script only reports trees it actually found.
4. **Splitting a source file is never automatic.** It changes the codebase, not
   its configuration, and belongs to whoever owns the code.
5. **Re-run after writing** and confirm the finding cleared.

## Reference

`references/limits.md` records where the cap figure comes from and what this
audit cannot see.
