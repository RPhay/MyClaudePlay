# TODO

Open work on this repo. Items are marked **verified** (I reproduced it) or
**suspected** (reasoned from the code, not yet triggered).

Last worked: 2026-08-21.

---

## Decisions needed

*(none open)*

---

## The context-cost model — REWRITTEN 2026-08-20

Ryan asked for this to be raised and for more scenarios to be walked through.
Done. The result is that the previously committed model was wrong in two ways
that pull in the same direction, and the headline number was overstated by
roughly 4x.

**The design conclusion survives. The magnitude does not.**

Subagent cost has since been **measured against document size** (see below),
which supersedes the assumed flat 20k run used in the first pass. On measured
costs the baseline scenario is **3.21x**, not the 1.82x computed from the
assumption, and not the 7.60x originally committed.

### What was wrong

1. **The price ratio was 15:1. It is 5:1.** Verified against the `claude-api`
   skill's pricing table (cached 2026-06-24): Claude Opus 5 input is $5.00/1M,
   Claude Haiku 4.5 input is $1.00/1M. Haiku work is 5x cheaper, not 15x. The old
   file's "at roughly 1/15 the price per token" tripled the apparent discount on
   every subagent token.

2. **Prompt caching was never in the model, and it is the dominant term.** The
   old model charged a carried document full price on every subsequent turn. It
   is not full price — it is a cache read at **~0.1x base input**. Cache writes
   are 1.25x (5-minute TTL) or 2.0x (1-hour TTL); this session runs the 1-hour
   TTL. So a doc read at turn `t` in an `N`-turn session costs
   `D x (2.0 + 0.1 x (N - t))`, not `D x (N - t + 1)`.

   At N=20, t=5 that is 3.5xD, not 16xD. The carrying cost — the entire argument
   for delegating — is about **4.6x smaller** than the file claimed.

3. **Caveat 2 was wrong on its own terms.** It said "direct wins for one-shot"
   and put the crossover at 2-3 turns. Even at the corrected 5:1 ratio, 20k Haiku
   tokens is 4,000 Opus-equivalent, against 3,877 to carry `feature-structure.md`
   once. There is no clean one-shot win for direct; with caching the agent is
   ahead from turn 1. The caveat was right that latency is real, and only that.

### The corrected numbers

Everything below is dollars, computed rather than asserted, under: index 270
tokens, agent answer 150 tokens, subagent run 20,000 tokens at 95% input / 5%
output, 1-hour cache TTL. `>1.00x` means the agent is cheaper.

| Scenario | No cache | **With cache (real)** |
|---|---|---|
| 20 turns, 3 questions — *the committed baseline* | 4.41x | **1.82x** |
| 50 turns, 3 questions | 9.05x | **3.25x** |
| 100 turns, 3 questions | 11.38x | **5.03x** |
| 200 turns, 3 questions | 12.78x | **7.29x** |

The old file's headline for row 1 was **7.6x**. It is **1.82x**.

### The seven scenarios that were owed

1. **Very short sessions (1-3 turns).** Agent wins throughout — 1.47x at a single
   turn, 1.59x at three. Caching *helps* the agent here, because the doc's first
   turn in context is a 2.0x cache write, which is worse than paying 1.0x once.
   The old "direct wins for one-shot" claim does not hold.

2. **Very long sessions (50-200 turns).** The gap does widen, but far more slowly
   than modeled: 3.25x / 5.03x / 7.29x rather than 11.67x / 13.03x / 13.70x.
   Cache reads at 0.1x flatten the compounding that drove the original argument.

3. **Many small docs vs few large ones — the framing was wrong.** Sweeping doc
   size against question count shows the deciding variable is **document size
   alone**; question count barely moves it (0.82x at 900 tokens with one
   question, 0.69x with eight). Caveat 5 is confirmed — the subagent cost is
   effectively fixed per run — but the useful form is a **crossover size**:

   | Session length | Crossover |
   |---|---|
   | 10 turns | ~1,900 tokens/doc |
   | 20 turns | ~1,450 tokens/doc |
   | 30 turns | ~1,170 tokens/doc |
   | 50 turns | ~870 tokens/doc |
   | 100 turns | ~560 tokens/doc |

   **Those figures assumed a flat 20k run and are superseded.** With the
   measured cost function the crossover is roughly 2.4x lower:

   | Session length | Assumed H=20k | **Measured H(D)** |
   |---|---|---|
   | 10 turns | ~1,860 | **~770** |
   | 20 turns | ~1,410 | **~590** |
   | 30 turns | ~1,150 | **~500** |
   | 50 turns | ~860 | **~390** |
   | 100 turns | ~560 | **~290** |

   Below the line, reading the document directly is cheaper than asking the
   agent. On measured costs **every document in this repo is above it** — at 20
   turns, `tech-stack.md` 1.25x, `feature-structure.md` 3.58x, `uix.md` 4.43x.
   An earlier version of this file said `tech-stack.md` favoured direct reading
   at 0.65x; that came from the assumed 20k run and measurement reverses it.

4. **Repeat questions about the same doc.** The old file guessed direct would
   "win outright" here. It does not — 3.92x to 4.20x in the agent's favour, and
   essentially flat from 2 questions on. The reasoning behind the guess was
   sound (direct amortises, the agent re-pays) but it ignored that re-carrying
   a 5,313-token doc for 28 more turns is itself the expensive part.

5. **A 10x corpus.** The index is ~25 tokens per doc plus ~200 fixed. 30 docs is
   ~950 tokens, 100 docs ~2,700, 300 docs ~7,700. At 300 docs the index alone
   approaches the size of one document, and the "load an index at startup"
   premise starts to erode. It holds comfortably to ~100 docs.

6. **Sessions that never touch docs.** 270 tokens per turn for nothing: 5,400
   tokens over 20 turns, 13,500 over 50 — but as cached reads after turn 1, so
   under a cent. Not worth optimising.

7. **Compaction.** Still the weakest part. Modeled as a single collapse at turn
   C summarising docs to ~200 tokens, it cuts the direct-read cost substantially
   and non-monotonically (best when compaction lands just after the last read).
   Real compaction is not one event at a known turn, and this remains
   **unexamined** rather than modeled.

### Break-even, as a usable rule

At what per-run subagent cost does direct become cheaper (cached)?

| Session | Break-even per run |
|---|---|
| 5 turns, 1 question | ~37,000 tokens |
| 20 turns, 3 questions | ~39,000 tokens |
| 50 turns, 3 questions | ~79,000 tokens |
| 100 turns, 3 questions | ~146,000 tokens |
| 30 turns, 6 small docs | ~14,000 tokens |

Or inverted, which is more useful: at a 20k run and 20 turns, delegation pays for
any document over **~1,450 tokens**.

Measured runs so far: **6,620** (`--update`, 6.2s), **20,331**, **22,186**. All
sit under break-even except in the many-small-docs case, where 20k runs are
already past it.

### Arithmetic check

The closed form above was cross-checked against a turn-by-turn simulation across
240 combinations of cached/uncached, session length, read turn, and doc size —
all agree exactly. One case by hand, for anyone re-deriving it:

```
uix.md (5,313 tokens) read at turn 5, 20-turn session, cached:
  cache write  5313 x 2.0 x $5/1M           = $0.053130
  cache reads  5313 x 0.1 x $5/1M x 15      = $0.039848
  total                                     = $0.092978
old model      5313 x $5/1M x 16            = $0.425040   (4.57x overstated)
```

### Four strategies compared — measured — 2026-08-20

An earlier version of this file compared delegation only against "read the one
correct document directly". That baseline was wrong: it granted the no-system
case a perfectly targeted single read, which is exactly the work doc-search
exists to do. The real alternatives are below.

**Measured head-to-head.** Three questions, none naming a file, asked of an
unguided reader (Grep/Glob/Read, doc-search forbidden) and of the doc-search
agent. Same model (Haiku 4.5), same harness. Both answered all three correctly.

| Question | Unguided | Calls | doc-search | Calls | Ratio |
|---|---|---|---|---|---|
| feature folder layout | 24,913 | 3 | 12,210 | 2 | 2.04x |
| db + node version | 20,358 | 2 | 7,620 | 1 | 2.67x |
| row column logic | 26,050 | 3 | 14,794 | 3 | 1.76x |
| **Mean** | **23,774** | | **11,541** | | **2.06x** |

Unguided costs 2.06x for the same answer — **not** because it reads more text
(both read the document) but because it takes more tool round-trips, and every
round-trip re-sends everything accumulated so far.

**Whole-session comparison**, 20-turn Opus 5 session, three questions, one per
document:

| Strategy | Main ctx | Billable | Subagent | $ | vs A |
|---|---|---|---|---|---|
| **A.** No system — Claude reads at whim | 11,005 | 32,298 | 0 | $0.1615 | 1.00x |
| **B.** Load all docs at SessionStart | 10,105 | 39,410 | 0 | $0.1970 | **0.82x** |
| **C.** doc-search inline, no agent | 10,375 | 30,652 | 0 | $0.1533 | 1.05x |
| **D.** doc-search via agent (current) | 795 | 2,628 | 29,544 | **$0.0486** | **3.32x** |

Two results matter more than the headline.

**B is worse than doing nothing.** Loading the corpus at startup costs 0.82x —
you pay for every document on every turn whether or not the session touches
docs. That is the design this repo already moved away from, and the number
confirms it was not merely inelegant but actively negative.

**C is worth almost nothing.** The index plus targeted loading — the whole skill,
minus the agent — beats unguided reading by **5%**. Essentially all the value is
in the subagent, not in the index or the script. That is worth knowing given
`/doc-search` was deliberately left inline: the inline path is a convenience for
getting raw text, not a cost optimisation, and should not be described as one.

Strategy A above still assumes the unguided reader finds the right document on
the first try. Applying the measured 2.06x round-trip penalty puts it at $0.3327,
or **6.8x** worse than D.

### Which model the subagent runs on — measured — 2026-08-20

Same task 22 times (`--load uix`, three-bullet summary), varying only the
subagent model. Baseline for comparison: the main session is Claude Opus 5, one
question about `uix.md` (5,319 tokens) at turn 5 of a 20-turn session.

**Tokens — the headline.**

| Strategy | Main context (Opus) | Subagent | Total |
|---|---|---|---|
| **No strategy — read it directly** | **85,104** | 0 | **85,104** |
| Delegate to Haiku 4.5 | 2,400 | 11,876 | 14,276 |
| Delegate to Sonnet 5 | 2,400 | 15,770 | 18,170 |
| Delegate to Opus 5 | 2,400 | 11,905 | 14,305 |
| Delegate to Fable 5 | 2,400 | 11,894 | 14,294 |

Reading directly moves **6.0x more tokens** than delegating, because the document
is re-sent on all 16 remaining turns. Cache-weighted, that is 18,616 billable
Opus tokens against 525.

**Token count barely varies by model — except Sonnet 5.** Haiku 11,876, Opus
11,905, Fable 11,894 all sit within 0.25% of each other. Sonnet 5 uses **15,770,
about 33% more**, consistently across both runs. Unexplained; the split between
input and output was not measured, and Sonnet's answers were visibly longer, so
it may be output rather than tokenizer.

**Opus 5 and Fable 5 runs were bit-identical in cost** — 11,905 twice, 11,894 —
matching the near-determinism seen on Haiku (sd 17 over five runs).

**Dollars per question**, subagent priced at its own model, main context always
Opus 5:

| Strategy | Main | Subagent | Total | vs direct |
|---|---|---|---|---|
| Read `uix.md` directly | $0.0931 | — | **$0.0931** | 1.00x |
| Delegate to **Haiku 4.5** | $0.0031 | $0.0143 | **$0.0173** | **5.38x** |
| Delegate to Sonnet 5 (intro) | $0.0031 | $0.0379 | $0.0409 | 2.28x |
| Delegate to Sonnet 5 (list) | $0.0031 | $0.0568 | $0.0598 | 1.56x |
| Delegate to Opus 5 | $0.0031 | $0.0714 | $0.0745 | 1.25x |
| Delegate to **Fable 5** | $0.0031 | $0.1427 | **$0.1458** | **0.64x — LOSES** |

> **Correction.** An earlier version of this table read 6.42x / 1.86x / 1.50x /
> 0.77x. Those applied a 5% output-token fraction to main-context tokens.
> Document text sitting in context is input only, so the direct-read baseline was
> overstated by 1.20x. The ordering is unchanged and Fable still loses.

Sonnet 5 intro pricing ($2/$10) runs through **2026-08-31**; after that it moves
to $3/$15 and the 2.72x becomes 1.86x.

**Crossover document size by subagent model** — below this size, reading the
document straight into Opus is cheaper than delegating:

| Subagent | 10 turns | 20 turns | 30 turns | 50 turns | 100 turns |
|---|---|---|---|---|---|
| Haiku 4.5 | 650 | 511 | 432 | 346 | 262 |
| Sonnet 5 | 2,775 | 1,890 | 1,451 | 1,015 | 620 |
| Opus 5 | 3,861 | 2,511 | 1,881 | 1,279 | 754 |
| Fable 5 | 18,683 | 7,779 | 4,953 | 2,909 | 1,487 |

Applied to this repo, 20-turn session (savings multiple; under 1.00x loses money):

| Doc | Direct | Haiku | Sonnet | Opus | Fable |
|---|---|---|---|---|---|
| `tech-stack.md` (900) | $0.0252 | 1.39x | **0.57x** | **0.47x** | **0.26x** |
| `feature-structure.md` (3,886) | $0.0879 | 4.01x | 1.49x | 1.22x | **0.65x** |
| `uix.md` (5,319) | $0.1180 | 4.97x | 1.78x | 1.46x | **0.77x** |

**Conclusion: the Haiku pin in `.claude/agents/doc-search.md` is doing most of
the work.** On Haiku every document in this repo pays. On Opus or Sonnet only the
two large ones do. On Fable delegation never pays here at all — the subagent
costs more than the context it saves. If the agent's `model: haiku` were ever
removed or overridden, the economics invert for the smallest doc immediately.

### Agent run cost — measured, 17 runs — 2026-08-20

This supersedes the doc-size fit below. Regressing subagent tokens on **the
script's output size** (not document size) unifies every mode into one function:

```
H(S) = 6,316 + 1.0486 x S        R^2 = 0.99970,  n = 17,  worst residual 112 tokens
```

where `S` is the tokens `doc-search.sh` prints. Three findings.

**1. It is effectively deterministic.** Five identical `--load uix` runs:
11,855 / 11,867 / 11,874 / 11,887 / 11,899. Mean 11,876, sd 17.1, range 0.37% of
mean. The cost function is not fitted noise.

**2. There is a hard floor of ~6,400 tokens per run**, paid before any document
is read. Measured four independent ways, all agreeing:

| Run type | Tokens |
|---|---|
| `--load` on a 5-token document | 6,366 / 6,296 |
| `--load --refs-only` | 6,297 / 6,295 |
| `--update` | 6,510 / 6,620 |
| `--analyze` | 6,509 |

Mean of all nine low-output runs: 6,410, sd 115 — and the regression's
independently-derived intercept is 6,316. This is the price of *asking*. It is
also the answer to the earlier question about why `--update` and `--analyze`
looked cheap: they are not a different kind of work, they just print very little.

**3. Output format is the largest lever available.** Cost tracks what the script
prints, so `--summary` collapses to near the floor regardless of document size:

| Doc | Format | Script output | Run cost | vs full |
|---|---|---|---|---|
| `uix.md` | full | 5,319 | 11,899 | 100% |
| `uix.md` | `--summary` | 127 | 6,405 | 54% |
| `uix.md` | `--refs-only` | 15 | 6,297 | 53% |
| `tech-stack.md` | full | 900 | 7,237 | 100% |
| `tech-stack.md` | `--summary` | 66 | 6,396 | 88% |

The saving is real but it is **not free**: `--summary` returns one paragraph, so
it answers "what is this document about" and nothing more. It is a cheaper
question, not a cheaper answer.

**Dollars per run** (Haiku 4.5, $1/1M in, $5/1M out; range spans all-input to
10% output):

| Run | Tokens | Cost |
|---|---|---|
| floor — `--refs-only`, `--update`, `--summary` | ~6,400 | $0.0064–$0.0090 |
| `--load tech-stack` | 7,267 | $0.0073–$0.0102 |
| `--load feature-structure` | 10,503 | $0.0105–$0.0147 |
| `--load uix` | 11,876 | $0.0119–$0.0166 |

**Whole session** — 20 turns, 3 questions, cached: **$0.1533 direct vs $0.0475
delegated, 3.23x**, a difference of $0.106 per session. At 20 such sessions a
month that is $3.07 against $0.95. The ratio is the interesting number; the
absolute amounts are small enough that this should be decided on context
pressure, not cost.

**Crossover on the measured function** — below this document size, reading
directly is cheaper than asking:

| Session | Crossover |
|---|---|
| 10 turns | ~760 tokens |
| 20 turns | ~590 tokens |
| 30 turns | ~490 tokens |
| 50 turns | ~390 tokens |
| 100 turns | ~285 tokens |

Every document in this repo is above the line at every session length.

### Earlier doc-size fit (superseded by the above) — 2026-08-20

Caveat 5 asked whether the ~20k per run was mostly fixed overhead. Measured by
running the agent three times with an identical task shape (`--load <doc>`, then
a three-bullet summary), varying only the document:

| Doc | Est. tokens | Subagent tokens | Duration |
|---|---|---|---|
| `tech-stack.md` | 892 | 7,297 | 7.6s |
| `feature-structure.md` | 3,877 | 10,503 | 6.3s |
| `uix.md` | 5,313 | 11,855 | 9.8s |

Least-squares fit, with residuals under 1% on all three:

```
H(D) = 6,398 + 1.038 x D
```

Two things follow. **Caveat 5's either/or was a false choice** — the cost is
~6,400 fixed *plus* ~1.04 tokens per document token, so the agent gets relatively
cheaper as documents grow without ever becoming free. And the **20,000-token
assumption was too high by 1.7x-2.7x** for a plain `--load`; the earlier 20,331
and 22,186 measurements were multi-step tasks, not comparable to these.

Caveat: three points, two parameters. A close fit is expected and is not by
itself strong evidence.

### Agent path verified against leakage — 2026-08-20

The same three runs double as the first check that the agent does what the whole
design exists for. All three returned distilled summaries; none reproduced
document text. The longest identifiers echoed back were names
(`generic-entity-tab.ejs`, `entity_types`), not prose. Document text stayed in
the subagent.

This is an observation over three runs, not a test. Nothing in the suite enforces
it, and nothing prevents a future prompt from producing a verbatim dump.

### What is still not verified

- **The ~4 bytes/token estimate.** No tokenizer is installed and the `claude-api`
  skill is explicit that `messages.count_tokens` is the right tool and `tiktoken`
  is not. Resolving it properly means sending the docs to the API, which needs a
  decision. Bracketed for now:

  | Doc | Bytes | bytes/4 | words x1.3 | words x1.5 |
  |---|---|---|---|---|
  | `feature-structure.md` | 15,508 | 3,877 | 2,727 | 3,147 |
  | `tech-stack.md` | 3,568 | 892 | 609 | 703 |
  | `uix.md` | 21,254 | 5,313 | 3,887 | 4,485 |
  | **Total** | **40,330** | **10,082** | **7,224** | **8,335** |

  The two methods differ by ~40%. `feature-structure.md` is 384 of 559 lines
  inside code fences, which tokenises denser than prose — so bytes/4 is likely
  closer for that file and likely high for `uix.md` (15 of 246 fenced). Every
  ratio above moves less than this uncertainty does, since doc size appears on
  the direct side of every comparison.

- **Whether the cost function generalises beyond this setup.** 17 runs at
  R^2=0.9997 across three modes is strong within this repo, but it is one corpus,
  one agent definition, one model. The ~6,400 floor is this agent's system prompt
  plus tool schemas; it would move if either changed, and it is the term that
  decides every small-document case.
- **The input/output token split per run.** `subagent_tokens` is a single total.
  Dollar figures above are given as a range across plausible splits rather than a
  point estimate, because the split was never measured.

- **Whether Claude Code's cache behaves as modeled.** The 0.1x/2.0x figures are
  the API's published pricing. Assuming every carried turn is a clean cache hit
  is optimistic; any miss moves that scenario toward the no-cache column, which
  favours the agent.

---

## The CLAUDE.md instruction graph — measured 2026-08-21

Gathered while designing a `claude-md-audit` skill. Nothing here is reasoned from
documentation or memory; every row was triggered on this machine.

**Method.** Each file in a fixture tree carries a unique `CANARY-X` string. A
non-interactive run then asks which canaries are visible in its instructions, so
one run resolves several hypotheses at once. Absence of a canary is the negative
result. Roughly 25 runs, ~$0.25 total.

```
claude -p '<canary question>' --model haiku --tools "" \
       --output-format json --no-session-persistence --max-budget-usd 0.10
```

Claude Code 2.1.239. Fixtures were built under the session scratchpad and are not
in this repo; they cover every row below and are worth rebuilding if any of this
needs re-testing.

### Verified behaviours

| # | Behaviour | Result |
|---|---|---|
| 1 | `@file.md` in a `CLAUDE.md` | Imports the file |
| 2 | Imports of imports | **Transitive** |
| 3 | Depth limit | Minimum hop ≤ 4 loads; **hop 5 silently does not** |
| 4 | `@sub/g.md`, `@./sub/h.md`, `@/abs/path.md` | All three forms import |
| 5 | Resolution base for a nested import | **The importing file's own directory**, not the project root |
| 6 | `@~/path.md` | **Never resolves.** Target existed; `~` is not expanded |
| 7 | Inside a ``` fence | Suppressed |
| 8 | Inside a `~~~` fence | Suppressed |
| 9 | Inside an inline code span | Suppressed |
| 10 | Inside a 4-space indented block | Suppressed — **only when it is a true code block**; see 23 |
| 11 | Mid-sentence in prose — "See @inline.md for details." | **Imports.** Almost certainly never intended |
| 12 | Import target missing | **Silent.** No error, no warning |
| 13 | Cycle `a → b → a` | Terminates; both load once |
| 14 | Diamond, target at hop 5 one way and hop 2 another | Loads, once. **Minimum hop wins** |
| 15 | Ancestor walk | Every ancestor directory from `/` down to cwd. **Does not stop at the git root.** No depth cap — 11 levels loaded |
| 16 | Nested `sub/CLAUDE.md`, cwd at project root | **Not loaded** |
| 17 | Nested `sub/CLAUDE.md`, cwd inside `sub/` | Loaded, **and so is every ancestor** |
| 18 | Nested `sub/CLAUDE.md` when a file in `sub/` is Read from the parent cwd | **Not loaded.** cwd decides, not file access. *One run* |
| 19 | `--add-dir <dir>` | Does **not** bring that directory's `CLAUDE.md` into the graph |
| 20 | `~/.claude/CLAUDE.md` from an unrelated directory | Always loads |
| 21 | `CLAUDE.local.md` | Loads alongside `CLAUDE.md` |
| 22 | Load order | Observed outermost-first, innermost-last — **observed, not proven**; the model could have sorted its own output |
| 23 | 4-space indent that is a **list continuation** | **Imports.** Not treated as a code block |
| 24 | 2-space indent | Imports — too shallow to be a code block |
| 25 | Inside a blockquote, `> @x.md` | Imports |

Row 1 was run twice and reproduced identically.

**Rows 10 and 23 together settle the parsing question.** Claude Code does real
markdown parsing, not naive indent-stripping: an identical four-space indent is a
code block after a paragraph and a continuation after a list item, and it imports
only in the second case. Any tool that skips every indented line silently misses
real imports.

### Consequences worth acting on

**Row 11 is the sleeper.** Any prose sentence anywhere in the graph containing
`@something.md` silently pulls that file into every turn. It is both a hidden cost
and a correctness hazard: naming a file in an instruction loads it.

**Rows 3 and 12 together are a silent-failure class.** An import past hop 5, or one
whose target moved, is present and referenced and never loads. Nothing signals it.

**Row 15 has real reach.** A single `CLAUDE.md` at `~/Code/` would load into every
project beneath it — this repo and every sibling — invisibly, on every turn. No
root-scoped tool can find that.

**Row 5 dictates the walker.** Resolving relative imports against the project root
instead of the importing file produces a wrong graph and wrong costs.

**Rows 7–10 mean the walker must be fence-aware**, or documentation examples get
counted as live imports and every figure inflates.

### Skill frontmatter mechanics — measured 2026-08-21

**`disable-model-invocation: true` removes the skill from the listing entirely.**

| Arm | Total prompt tokens | Description text reached the model |
|---|---|---|
| Control, no skill present | 9,513 | — |
| Skill, no flag | 9,546 | **yes** |
| Skill, `disable-model-invocation: true` | 9,513 | no |

A listed skill costs tokens proportional to its description — 33 tokens for a
120-character one here, consistent with the ~424 chars / ~118 tokens per skill
measured across the real `skill_listing` attachments in this machine's
transcripts. With the flag set the always-on cost is exactly zero, and the model
cannot know the skill exists.

**Both permission-spec spellings work.** `claude --help` documents
`Bash(git *)` with a space while settings files use `Bash(git:*)` with a colon.
Measured 2026-08-22 with `--allowed-tools` against a command that is *not*
auto-approved (`touch`): the control was denied and the file was not created,
while both `Bash(touch *)` and `Bash(touch:*)` permitted it. The discrepancy is
not a conflict — either spelling is accepted, so a linter must not flag one.

**A skill's identity is its directory name, not its `name` field.** A skill in
`dirname-alpha/` declaring `name: namefield-beta` was listed and invoked as
`dirname-alpha`, while its `description` was still read from the frontmatter.

> **Correction.** The 2026-08-21 hand audit of `../OtherClaudeSkills/Claude-Skills`
> reported that `one-skill-to-rule-them-all` declaring `name: task-observer`
> collided with the separate `task-observer/` skill. It does not. The `name` field
> is inert for identity, so the two never conflict. The divergence is still worth
> fixing as documentation, but it is not the defect it was called.

A consequence for the same collection: a skill with no frontmatter at all is
still invocable as `/<directory>`. It simply has no description and so can never
auto-trigger. That may be deliberate — this repo's own `doc-search` skill has no
frontmatter and is documented as intentionally slash-only.

**`allowed-tools` in `SKILL.md` is declarative, not enforcing** — in both
non-interactive and interactive mode. Non-interactive arms pre-approved only
`Skill`; interactive arms were driven through a PTY harness.

| Mode | Skill frontmatter | Tool attempted | Outcome |
|---|---|---|---|
| `-p` | `["Read"]` | Bash `echo` | **Ran** — `echo` is auto-approved regardless |
| `-p` | `["Read","Bash"]` | Bash `echo` | Ran |
| `-p` | `["Read"]` | Write | **Blocked** |
| `-p` | `["Read","Write"]` | Write | **Blocked** |
| interactive | `["Read"]` | Write | Prompted: *"Do you want to create probe-out.txt?"* |
| interactive | `["Read","Write"]` | Write | **Prompted identically** |

It neither restricts the skill nor grants it anything; runtime permission comes
from session settings alone. Listing `Edit`/`Write` in a skill therefore creates no
hazard — and provides no safety. Any `--apply` protection must come from the
skill's own diff-and-confirm procedure.

Two incidentals from the interactive arms, both worth knowing before writing a
skill that invokes tools:

- **Invoking a skill is itself a separate permission prompt** — *"Use skill
  `<name>`? Claude may use instructions, code, or files from this Skill"* — shown
  before any tool the skill goes on to call. A skill costs the user two
  confirmations, not one.
- **A relative path inside a skill body resolved against the skill's own
  directory**, not the session cwd: `./probe-out.txt` was proposed as
  `.claude/skills/writeprobe/probe-out.txt`. Skill bodies should use explicit
  paths.
- **Writes under `.claude/` are gated separately from ordinary file writes**, and
  `--permission-mode acceptEdits` does **not** cover them. Any skill whose fixes
  land in `.claude/` will appear to fail unless that permission is granted; it
  should report the fixes as prepared rather than as failed.

### Not verified

- **Enterprise / managed-policy scope.** No managed-settings path exists on this
  machine and creating one needs admin rights.
- **Load order** — row 22 is an observation, not a proof.
- **Whether the depth limit counts files or hops** in topologies other than the
  chain and diamond tested.

---

## Bugs

*(none open)*

### Fixed 2026-08-20

- **`--analyze <skill> --overwrite` could destroy the manifest.** `analyze_skill()`
  wrote `${skill_dir}/doc-search.md`, which inside `skills/doc-search/` *is* the
  manifest. Generated files are now `doc-needs.md`. Regression test:
  `analyzing doc-search keeps manifest`.
- **Ambiguous doc names resolved silently.** `find_doc()` took `head -1` of the
  recursive search. It now returns status 2, lists every candidate on stderr, and
  emits no document. Exact matches still win before the recursive search runs.
  Regression tests: `ambiguous name reports candidates`, `exact match beats
  ambiguity`, `ambiguity does not block siblings`.
- **Empty scans reported "Found 1".** `echo "" | wc -l` is 1. Added `count_lines()`.
- **`--analyze` complained on stderr** when `docs/features/` did not exist.
- **`--summary` returned only the document's title.** `get_summary()` ended with
  `sed '/^$/q'`, which quits at the first blank line — in markdown the one after
  the H1. Every document summarised to its own heading, while `SKILL.md`,
  `README.md`, and the function's own comment all promised a first paragraph.
  Replaced with an `awk` pass that keeps the leading heading, skips blanks and
  any further headings, then prints to the next blank. Test: `load --summary`.
- **`MANIFEST` pointed at `.claude/doc-search.md`**, a path that has never
  existed, and was unused. Repointed at the real manifest and now used by
  `update_manifest()` instead of a duplicated literal.

---

## Untested

**Tests exist again, and both suites pass.** `tests/` was removed from git in
8608c7b while staying on disk; it was re-tracked on 2026-08-22 after being run
rather than assumed. `tests/README.md` documents both.

| Suite | Cases | Covers |
|---|---|---|
| `tests/unit/doc-search.test.sh` | 29 | all three modes, `load-baseline.sh`, and the five fixed bugs |
| `tests/unit/skills.test.py` | 52 | the ten skill scripts under `.claude/skills/*/scripts/` |

Four of the six items this section previously listed as needed are now covered:
the five fixed bugs, the `--analyze --overwrite` write path, `--update`'s
`Features` and `Other Documentation` branches both populated and empty, and
documents with spaces in their filenames.

The skills suite was checked by mutation rather than by watching it pass:
reverting the list-continuation fix, dropping the minimum-hop filter, and
removing `requestId` dedupe each fail their own case and nothing else.

### Still not covered

- **The agent path.** That the subagent returns correct answers and does not leak
  document text into the caller's context. This is the actual product and it
  remains the largest gap — an observation over three runs on 2026-08-20 is not a
  test, and nothing enforces it.
- **GNU `sed` portability.** `analyze_skill()` uses BSD `sed -i ''` and will fail
  on Linux. No suite runs on Linux, so this would not be caught.
- **The skills' `--apply` paths.** All four were exercised by hand end to end and
  found six defects between them, but the unit suite covers only the pure logic.
  Exercising an apply path needs a live session, which belongs in `tests/bench/`
  if it is ever automated.

---

## Gaps

- **`docs/features/` does not exist.** `feature-structure.md` specifies a
  per-feature layout nothing in this repo uses, so `--analyze`'s
  conditional-loading paths point at directories that aren't there. The `--update`
  Features branch is now covered by a fixture instead. Declined 2026-08-20 —
  no new content this pass.
- **The `doc-needs.md` pattern has still never run.** A skill declares its
  documentation needs and the agent fetches them; documented, never exercised.
  The 2026-08-20 note that "one skill and one agent is the intended footprint"
  no longer holds — there are ten skills as of 2026-08-22 — but none of the nine
  new ones declare doc needs, because none of them read `docs/`. The pattern
  is still unexercised for a different reason than before.
- **Two unverified graph items are one canary run each.** Load order (rule 22 is
  observed, not proven — the model may have sorted its own output) and whether the
  depth limit counts files or hops in a topology other than the chain and diamond
  already tested. Both use the fixture-and-canary method recorded above; neither
  has been scheduled. The third unverified item, enterprise/managed-policy scope,
  needs admin rights and stays open.
- **The token-optimization skills are unpushed.** Nine skills, their tests and
  the measured findings sit on `doc-search-fixes-and-cost-model`, 24 commits
  ahead of `main` and never pushed. Nothing is lost, but nothing is backed up
  either.

---

## Housekeeping

- **Hook changes need a session restart** to take effect. The settings watcher
  only picks up `.claude/` when a settings file was present at session start.
  Now documented in `SKILL.md`'s install steps.
- **`README.md` describes `docs/standards/` as a sample corpus.** If this repo
  ever adopts those standards for itself, that framing needs updating.
- **Permissions moved to committed `.claude/settings.json`** (2026-08-20), so a
  clone works without each person adding the rule. `.gitignore` still excludes
  `settings.local.json`; no such file exists in the repo. Note the rule syntax is
  `Bash(<prefix>:*)` — colon. Measured 2026-08-22: the space form
  `Bash(<prefix> *)` works too, so both are valid and neither is wrong.
