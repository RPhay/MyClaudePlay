# --apply: fix procedures by class

Read before applying anything for the first time.

## The two rules that are not negotiable

**Never modify a file through Bash.** No `sed -i`, no `>` redirection, no `tee`.
`Edit` and `Write` render a diff inside the permission dialog; shell writes do
not. A repo whose `settings.json` pre-approves something like `Bash(sed:*)` would
let this skill rewrite `CLAUDE.md` with no prompt at all.

This matters more than it looks, because **`allowed-tools` in SKILL.md grants
nothing and restricts nothing** — measured in both `-p` and interactive mode. The
only thing between this skill and a silent edit is which tool it picks.

**Batch per file, not per fix.** Permission prompts are per tool call. Applying
ten fixes individually produces eleven dialogs, and a user facing eleven dialogs
selects "Yes, and don't ask again" — granting blanket write access and destroying
the protection. Compose every fix to one node into a single `Edit`.

Also note: invoking a skill is *itself* a separate dialog, shown before any tool
the skill goes on to call. Budget the user's attention accordingly.

## Preconditions

1. The file is tracked by git, or `--force` was passed. `~/.claude/CLAUDE.md` is
   the case that matters — usually untracked, and there is no undo.
2. The walk has just run. Never apply against a stale finding list.

## Class 1 — mechanical, no semantic change

Applied by `--apply`.

| Finding | Fix |
|---|---|
| Dead import | If exactly one file of that basename exists under the importing file's directory, rewrite the path to it. Otherwise delete the line and report the deletion. |
| Tilde import | Rewrite `@~/x` to the expanded absolute path if the target exists; otherwise delete the line. |
| Accidental prose import | Wrap the token in backticks — `` @x.md `` — which suppresses the import while leaving the sentence readable. Never delete the sentence. |

Backticks are the correct neutraliser because inline code spans are verified to
suppress imports (rule 9). Do not indent the line or fence it; both change how the
surrounding prose renders.

## Class 2 — semantic, requires `--apply=2`

| Finding | Fix |
|---|---|
| Unreachable import | Re-parent: move the `@` line from its current node up to one whose hop is ≤ 3, so the target lands at ≤ 4. If no such node exists without changing meaning, delete and report. |
| Duplicated instruction | Delete from the **lower-precedence** node. Load order is outermost-first, so the innermost occurrence is the one that survives. Rule 22 is observed rather than proven — if precedence is load-critical, report instead of applying. |

Re-parenting changes which file an instruction lives in and therefore which
working directories load it. Show the user both nodes in the diff.

## Class 3 — never applied

Reported only, always.

| Finding | Why it is not auto-fixed |
|---|---|
| Node outside the repo | It costs every project on the machine, and it is not this repo's file to edit. |
| Oversized node | Deciding what becomes an on-demand reference is an editorial judgment about the instructions' meaning. |
| Contradiction between nodes | **Not detected at all.** The report lists every node so they can be compared by hand. Do not claim the audit checked. |

## After every write

Re-run the walk. Every finding in the applied batch must be gone. If one is not,
revert that file and report it — a fix that does not clear its own finding is a
bug in the fix, not in the detector.
