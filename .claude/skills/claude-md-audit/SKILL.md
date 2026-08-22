---
name: claude-md-audit
description: Audits the CLAUDE.md instruction graph and reports its per-turn token cost. Walks every CLAUDE.md and CLAUDE.local.md from the filesystem root down to the working directory plus ~/.claude, follows @-imports transitively, and reports dead imports, imports past the depth limit that silently never load, accidental imports created by @file mentions in prose, and instructions duplicated across scopes. Use when diagnosing token cost, auditing repo setup, or before changing CLAUDE.md. --apply fixes safe findings.
allowed-tools: ["Read", "Glob", "Bash(python3:*)", "Bash(git:*)", "Edit", "Write"]
disable-model-invocation: true
argument-hint: "[--apply] [--apply=2] [--dir <path>]"
---

# claude-md-audit

Reports what the loaded instruction graph costs on every turn, and what in it is
broken. Every graph rule below was measured against Claude Code 2.1.239, not read
from documentation — see `references/behaviour.md`.

## Run it

```
python3 "$(git rev-parse --show-toplevel)/.claude/skills/claude-md-audit/scripts/graph.py" --root "$PWD"
```

Use an explicit `--root`. Never a bare relative path: a relative path inside a
skill body resolves against the skill's own directory, not the session cwd.

`--dir <path>` audits a different working directory. This matters — a nested
`CLAUDE.md` loads only when the cwd is inside its subtree, so cost is per
directory, not per repo. `--json` emits the same data for scripting.

## Reading the report

Two blocks, deliberately separated.

**MEASURED** is the fixed prefix baseline: the floor of `cache_read_input_tokens`
across this project's transcripts. It covers the *entire* static prefix — system
prompt, tool schemas, skill listing and the instruction graph together. It bounds
the graph. It does not isolate it. Say so if you quote it.

**ESTIMATED** is the graph itself, as a bracket between `words x1.3` and
`bytes/4`. Those two methods differ by up to 40% and no tokenizer is installed.
Never collapse the bracket to one number. If the high end exceeds the measured
baseline the estimator is wrong and the report says so — believe the baseline.

Costs shown are `2.0x` on the first turn (1-hour TTL cache write) and `0.1x` on
every turn after (cache read).

## Decision table

| Finding | Action | Class |
|---|---|---|
| Dead import — target missing | Fix the path or delete the line | 1 |
| Tilde import — `@~/…` never resolves | Replace with an absolute path, or delete | 1 |
| Accidental import — `@x.md` mid-sentence in prose | Wrap in backticks to neutralise, or confirm it was meant | 1 |
| Unreachable import — minimum hop ≥ 5 | Re-parent onto a shallower node, or delete | 2 |
| Duplicated instruction across nodes | Delete from the lower-precedence node | 2 |
| Node outside the repo | Report only. It costs every project on this machine | 3 |
| Oversized node | Move detail into an on-demand reference | 3 |

Contradictions between nodes are **not** auto-detected. The report lists every
node so they can be compared by hand; do not claim the audit checked for them.

## --apply

Default is report-only. `--apply` performs class 1; `--apply=2` adds class 2.
Class 3 is never applied.

1. **Batch per file, not per fix.** Compose all fixes to one node into a single
   `Edit`. Prompts are per tool call, so per-fix application produces a dialog
   storm, and a user facing eleven dialogs selects "don't ask again" — which
   grants blanket write access and removes the protection entirely.
2. **Never modify a file through Bash.** No `sed -i`, no redirection, no `tee`.
   `Edit` and `Write` always render a diff in the permission dialog; shell writes
   bypass it, and a repo whose settings pre-approve `Bash(sed:*)` would let this
   skill rewrite `CLAUDE.md` with no prompt at all. The permission dialog is the
   review surface — `allowed-tools` above grants nothing and restricts nothing.
3. **Refuse unversioned files without `--force`.** `~/.claude/CLAUDE.md` is the
   case that matters: it is usually untracked and has no undo.
4. **Re-run the walk after each write.** Every finding in that batch must clear.
   Revert and report any that does not.

## References

Read `references/behaviour.md` when a result looks wrong or the walker needs
changing — it holds the 22 verified rules and the evidence for each. Read
`references/apply-classes.md` before applying anything for the first time.
