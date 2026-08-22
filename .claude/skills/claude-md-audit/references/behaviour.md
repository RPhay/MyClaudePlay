# CLAUDE.md graph behaviour — measured

Read this when a result from `graph.py` looks wrong, or before changing the
walker. Nothing here is from documentation; every row was triggered on a real
machine against **Claude Code 2.1.239** on 2026-08-21.

## Method

Each file in a fixture tree carries a unique `CANARY-X` string. A non-interactive
run then asks which canaries are visible in its instructions, so one run resolves
several hypotheses at once. Absence of a canary is the negative result.

```
claude -p '<canary question>' --model haiku --tools "" \
       --output-format json --no-session-persistence --max-budget-usd 0.10
```

Roughly 25 runs, ~$0.25. Note `--tools ""` disables the Skill tool as well, which
confounded an early attempt at the frontmatter arms — enable `Skill` explicitly
when measuring anything about skills.

## Verified rules

| # | Behaviour | Result | Implemented in |
|---|---|---|---|
| 1 | `@file.md` in a `CLAUDE.md` | Imports | `IMPORT` |
| 2 | Imports of imports | Transitive | `walk` |
| 3 | Depth limit | Minimum hop ≤ 4 loads; hop 5 silently does not | `MAX_HOP` |
| 4 | `@sub/g.md`, `@./sub/h.md`, `@/abs/path.md` | All import | `resolve` |
| 5 | Resolution base for a nested import | **The importing file's own directory** | `resolve` |
| 6 | `@~/path.md` | Never resolves; `~` is not expanded | `resolve` |
| 7 | Inside a ``` fence | Suppressed | `FENCE` |
| 8 | Inside a `~~~` fence | Suppressed | `FENCE` |
| 9 | Inside an inline code span | Suppressed | `INLINE_CODE` |
| 10 | Inside a 4-space indented block | Suppressed — **only when it is a true code block**; see 23 | `extract_imports` |
| 11 | Mid-sentence in prose | **Imports.** Almost never intended | `alone_on_line` |
| 12 | Import target missing | Silent. No error, no warning | `dead_import` |
| 13 | Cycle `a → b → a` | Terminates; both load once | `nodes` dedupe |
| 14 | Diamond, hop 5 one way and hop 2 another | Loads once. **Minimum hop wins** | `maybe_unreachable` filter |
| 15 | Ancestor walk | Every ancestor from `/` down to cwd. **Does not stop at the git root.** No depth cap — 11 levels loaded | `root_files` |
| 16 | Nested `sub/CLAUDE.md`, cwd at project root | Not loaded | `root_files` |
| 17 | Nested `sub/CLAUDE.md`, cwd inside `sub/` | Loaded, and so is every ancestor | `root_files` |
| 18 | Nested file when a file in `sub/` is Read from the parent cwd | Not loaded. cwd decides, not file access. *One run* | — |
| 19 | `--add-dir <dir>` | Does not bring that directory's `CLAUDE.md` into the graph | — |
| 20 | `~/.claude/CLAUDE.md` from an unrelated directory | Always loads | `root_files` |
| 21 | `CLAUDE.local.md` | Loads alongside `CLAUDE.md` | `root_files` |
| 22 | Load order | Observed outermost-first — **observed, not proven** | `root_files` |
| 23 | 4-space indent that is a **list continuation** | **Imports.** Not a code block | `in_list` |
| 24 | 2-space indent | Imports — too shallow to be a code block | `indented` |
| 25 | Inside a blockquote, `> @x.md` | Imports | `BLOCKQUOTE` |

Rule 1 was run twice and reproduced identically.

**Rules 10 and 23 together are the important pair.** Claude Code does real
markdown parsing, not naive indent-stripping: the same four-space indent is a code
block after a paragraph and a continuation after a list item, and it imports in
the second case only. A parser that skips every indented line silently misses real
imports — a false negative, which is the worse failure here.

## Why several of these matter

**Rule 11 is the sleeper.** Any prose sentence containing `@something.md` pulls
that file into every turn. Both a hidden cost and a correctness hazard: naming a
file in an instruction loads it.

**Rules 3 and 12 together are a silent-failure class.** An import past hop 4, or
one whose target moved, is present and referenced and never loads. Nothing signals
it. These are the findings no other tool produces.

**Rule 15 has real reach.** One `CLAUDE.md` at `/Users/<you>/Code/` loads into
every project beneath it, invisibly, on every turn. No root-scoped tool finds it.

**Rule 5 dictates the walker.** Resolving relative imports against the project
root instead of the importing file yields a wrong graph and wrong costs.

**Rules 7–10 require fence-awareness**, or documentation examples get counted as
live imports and every figure inflates.

**Rule 14 requires the two-pass unreachable check.** A single-pass walk flags a
diamond's shared target as unreachable even though it loads.

## Cost model

From measurement recorded in this repo's `CLAUDE-TODO.md`:

- Cache reads ~`0.1x` base input. Writes `1.25x` (5-minute TTL) or `2.0x`
  (1-hour TTL). Sessions here run the 1-hour TTL.
- `cache_read_input_tokens` must be deduplicated by `requestId` — one session had
  440 assistant records across 195 unique requests, a 2.2x inflation if summed
  naively.

## Not verified

- **Enterprise / managed-policy scope.** No managed-settings path existed on the
  test machine and creating one needs admin rights.
- **Load order** — rule 22 is an observation. The model may have sorted its output.
- **Whether the depth limit counts files or hops** in topologies other than the
  chain and diamond tested.
- **Token counts.** No tokenizer is installed. `bytes/4` and `words x1.3` differ by
  up to 40%; the report brackets them rather than picking one.
- **Permission spec syntax.** `claude --help` documents `Bash(git *)` with a space;
  this repo's `settings.json` uses `Bash(git:*)` with a colon. Unresolved.
