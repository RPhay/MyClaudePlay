---
name: skill-lint
description: Checks SKILL.md files for conformance defects and reports what each skill costs in listing tokens on every turn. Finds missing or malformed frontmatter, a name field disagreeing with its directory, missing description, descriptions over the length limit, oversized bodies that should defer detail to references, directories in a skills root with no SKILL.md, duplicate name fields, and descriptions similar enough to compete for triggers. Use before installing an unfamiliar skill collection, when auditing your own, or when a skill fails to trigger. --apply fixes the mechanical defects.
allowed-tools: ["Read", "Glob", "Bash(python3:*)", "Bash(git:*)", "Edit", "Write"]
disable-model-invocation: true
argument-hint: "[--apply] [--apply=2] [--scope project|user|all] [--path <dir>]"
---

# skill-lint

Every defect this checks was found in a real community skill collection. See
`references/defects.md` for which, and for the measurement behind the cost figures.

## Run it

```
python3 "$(git rev-parse --show-toplevel)/.claude/skills/skill-lint/scripts/lint.py" --scope project --root "$PWD"
```

Default to `--scope project`. `--scope all` includes every installed plugin and
on a well-stocked machine emits more than is readable in one pass — ask for it
only when the question is actually about the user's whole installation.

**If that command cannot run — Bash denied, python3 missing, script not found —
report that and stop.** Do not read the skill files by hand and describe them
yourself. A hand-read audit is indistinguishable from a measured one and is not one.

`--path <dir>` scans an arbitrary directory instead of the installed scopes,
which is how an unfamiliar collection gets vetted *before* it is installed.
`--scope project|user|all` selects which installed scopes to check. `--json`
emits the same data.

**`--apply` is an argument to this skill, not to the script.** `lint.py` only
reports. You perform fixes yourself with `Edit`.

## The fact that governs most of this

**A skill's identity is its directory name, not its `name` field.** Measured: a
skill in `dirname-alpha/` declaring `name: namefield-beta` is listed and invoked
as `dirname-alpha`. The `name` field is documentation.

Three consequences the report depends on. A `name` that disagrees with its
directory is inert rather than broken, so aligning it is safe. Two skills
declaring the same `name` are **not** in conflict. And a skill with no
frontmatter at all is still invocable as `/<directory>` — it simply has no
description, so it can never auto-trigger. That may be exactly what its author
intended.

## Decision table

| Finding | Action | Class |
|---|---|---|
| `name` field disagrees with directory | Rewrite `name` to the directory. Never rename the directory — that changes the identifier | 1 |
| Frontmatter has no `name` | Insert `name: <directory>` | 1 |
| `description` over 1024 chars | Report the length. Shortening changes trigger behaviour | 3 |
| No frontmatter | Add `name` and a `description` drawn from the body. Say plainly that the description is newly written, not recovered | 2 |
| No `description` | Same as above | 2 |
| Listed on every turn | Add `disable-model-invocation: true` **only if** the skill is meant to be slash-only. It stops the model auto-invoking | 2 |
| Oversized body | Move detail into `references/`. Editorial judgment | 3 |
| Directory with no SKILL.md | Report. Deleting a directory is not diff-visible and is not automated | 3 |
| Duplicate `name` fields | Report. Not a functional collision | 3 |
| Overlapping descriptions | Report. Similarity is inferred from word overlap, not meaning | 3 |

## --apply

Default is report-only. `--apply` performs class 1; `--apply=2` adds class 2.
Class 3 is never applied.

1. **Batch per file.** Compose every fix to one `SKILL.md` into a single `Edit`.
   Prompts are per tool call, and a user facing a dialog storm selects "don't ask
   again", which grants blanket write access and removes the protection.
2. **Never modify a file through Bash.** No `sed -i`, no redirection. `Edit` and
   `Write` render a diff in the permission dialog; shell writes bypass it.
   `allowed-tools` above grants nothing and restricts nothing — the dialog is the
   only real control.
3. **Refuse unversioned files without `--force`.**
   Note that every file this skill fixes lives under `.claude/`, and Claude Code
   gates writes there behind a permission separate from ordinary file writes. If
   the edits are declined, say that the fixes are prepared and awaiting that
   approval — do not report the run as failed, and do not try to route around it
   with Bash.
4. **Re-run the lint after each write** and confirm the findings cleared.
5. **Never stop to ask which remedy to use.** Every class 1 and 2 finding has one
   prescribed fix above. Record judgment calls in the summary instead.

A class 2 fix that writes a `description` is writing new trigger behaviour, not
restoring lost text. Always say so.
