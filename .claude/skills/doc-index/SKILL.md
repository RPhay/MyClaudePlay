---
name: doc-index
description: Reports on docs/ coverage and staleness and generates a plain INDEX.md listing every document with its title and a one-line summary. Finds index entries pointing at missing files, documents absent from the index, documents with no summary paragraph, and documents referenced nowhere outside docs/. Use when documentation has drifted, when onboarding a repo, or when nothing lists what documentation exists. --apply writes the index.
allowed-tools: ["Read", "Glob", "Grep", "Bash(python3:*)", "Bash(git:*)", "Edit", "Write"]
disable-model-invocation: true
argument-hint: "[--apply] [--docs <dir>]"
---

# doc-index

## Run it

```
python3 "$(git rev-parse --show-toplevel)/.claude/skills/doc-index/scripts/index.py" --root "$PWD"
```

Add `--emit` to print the proposed index. `--docs <dir>` points at a
documentation tree other than `docs/`.

**The script never writes anything.** It prints the proposed index and you write
it with `Write`, so the change goes through the permission dialog as a visible
diff. `--apply` is an argument to this skill, not to the script.

**If the command cannot run, report that and stop.** Do not enumerate the docs by
hand — the point of the index is that it matches what is actually on disk.

## Standalone by design

The index is plain markdown with relative links. It is readable by a person, by
Claude, by GitHub, and by any future agent. It does not require, produce for, or
depend on any particular documentation tooling, so it keeps working if the tooling
around it is replaced or removed.

## Decision table

| Finding | Action | Class |
|---|---|---|
| No `INDEX.md` | Generate it | 1 |
| Index entry points at a missing file | Regenerate; the entry disappears | 1 |
| Document missing from the index | Regenerate; it gets added | 1 |
| Document with no summary paragraph | Report. Writing a summary is authoring, and it belongs to whoever owns the document | 2 |
| Document referenced nowhere outside `docs/` | Report only. It may be reference material nobody links to, which is fine | 3 |
| Corpus past ~100 documents | Report. An always-loaded index stops paying around there — the scaling note is in `CLAUDE-TODO.md` | 3 |

## --apply

Class 1 only: write `docs/INDEX.md` from the script's proposed output.

1. **One `Write` for the whole file.** It is generated wholesale, so a single
   write gives the dialog one coherent diff.
2. **Never write it through Bash.** No redirection, no heredoc. `Write` renders
   a diff in the permission dialog; shell redirection bypasses it entirely, and
   `allowed-tools` grants nothing and restricts nothing.
3. **Never invent a summary.** The script takes each summary from the document's
   own first paragraph. A document with none is reported as unsummarised, not
   given a summary you wrote — that would put words in the document's mouth in a
   file people trust to describe it.
4. **Never delete a document** because nothing references it.
5. **Re-run afterwards** and confirm the findings cleared.

## What it cannot tell you

Whether a summary is *accurate* — it is the document's own first paragraph, which
may be stale even when the index is fresh. And whether a document is worth
keeping; "referenced nowhere" is a prompt to look, not a verdict.
