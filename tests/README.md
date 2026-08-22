# Tests

Two independent suites. The unit suite is free and fast; the benchmark spends
real money on real model calls.

```
tests/
├── unit/
│   ├── doc-search.test.sh     shell-level behaviour, no model calls
│   └── skills.test.py         the ten skill scripts, no model calls
└── bench/                     real headless sessions, real token counts
    ├── selfcheck.py           asserts harness invariants before any API call
    ├── gen-corpus.py          deterministic corpus with verifiable facts
    ├── mkfixture.sh           builds one architecture variant
    ├── run-bench.py           runs the sweep, writes .bench/*.jsonl
    └── report.py              aggregates into comparison tables
```

## Unit

Both suites take an optional positional filter, build their fixtures under
`$TMPDIR`, and touch nothing in the working repository.

### doc-search

```bash
./tests/unit/doc-search.test.sh            # all
./tests/unit/doc-search.test.sh ambiguous  # filter by name
```

Each case builds a throwaway git repo and copies the real scripts into it.
Covers the five fixed bugs, all three modes, and `load-baseline.sh`.

### skills

```bash
./tests/unit/skills.test.py            # all
./tests/unit/skills.test.py graph      # filter by name
```

48 cases over the ten token-optimization skill scripts under
`.claude/skills/*/scripts/`. Stdlib only; each script is imported by path.

Every assertion corresponds to a behaviour **measured** against Claude Code
2.1.239 and recorded in `CLAUDE-TODO.md` — the instruction-graph rules, the
frontmatter results, the cache multipliers. When a case fails, check whether
Claude Code changed before changing the test.

Coverage is weighted toward the rules that were actually wrong at some point
rather than toward line count: fence and indent handling, list continuations
versus code blocks, `@`-import resolution against the importing file, minimum
hop winning in a diamond, `requestId` dedupe, binary exclusion, and
truncation-banner parsing.

Graph traversal cases stub `root_files`. The real ancestor walk has no
boundary — it does not stop at the git root — so without the stub a test in
`$TMPDIR` would pick up `~/.claude/CLAUDE.md` and any `CLAUDE.md` above the
temp directory, and results would depend on the machine.

The suite was checked by mutation, not by observing it pass. Reverting the
list-continuation fix, dropping the minimum-hop filter, and removing
`requestId` dedupe each fail their own case and nothing else.

## Benchmark

Answers the question the whole design rests on: **is delegating to a subagent
actually better than the alternatives?** It compares four architectures over a
multi-turn session, because the argument for delegation is about *carrying*
cost — what a document costs on every turn after the one that read it. A
single-shot run cannot see that.

| | Architecture |
|---|---|
| **A** | No system. Docs present; no hook, no skill, no agent. Claude greps and reads. |
| **B** | Preload. SessionStart hook dumps every document in full. |
| **C** | Inline skill. Hook emits an index; script available; **no agent**. |
| **D** | Agent. Hook emits an index; skill + `doc-search` subagent + the `CLAUDE.md` routing line. |

```bash
python3 tests/bench/selfcheck.py                     # free; exit 0 = safe to spend
python3 tests/bench/run-bench.py --arch A,B,C,D --models haiku --docs 8 --turns 10 --repeats 2
python3 tests/bench/report.py .bench/results-main.jsonl
```

Run `selfcheck.py` first, every time. Every bug this harness has had was an
invariant discoverable for free — the control could answer, the answer key sat
inside the fixture, the facts were guessable — and each one was found by paying
for a run instead.

Options: `--models` (comma-separated, sets the **main session** model — the
subagent model is pinned in the agent's own frontmatter), `--docs` corpus size,
`--turns` session length, `--repeats` for variance, `--seed`, `--size`.

### How it measures

Turn 1 asks a question only one document can answer. Turns 2..N are trivial
filler that use no tools, so their cost is almost entirely re-sent context —
that difference *is* the carrying cost.

Cost comes from the CLI's own `total_cost_usd`. Nothing in the harness models
cache pricing or guesses an input/output split, which is what made the earlier
arithmetic estimates wrong.

Every generated document carries one unique fact (`widget-N` listens on port
`80NN`), so each run is scored for **correctness**, not only cost. A strategy
that is cheap because it failed to find the answer is not cheap.

`cache_create` is the column that shows whether the mechanism works at all: it
is how much new text entered the session. A document that stays inside a
subagent never appears there.

### Notes

- Fixtures carry their own `CLAUDE.md` with no ask-before-acting rule. The real
  repo's rule makes a headless session stop and request confirmation instead of
  doing the task.
- Runs use `--dangerously-skip-permissions`. Fixtures are throwaway directories
  under `.bench/` containing generated markdown, and the task is a read-only
  lookup — but that flag is why this is not something to point at a real repo.
- `.bench/` is working output. Delete it freely.
