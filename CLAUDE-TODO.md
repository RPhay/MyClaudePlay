# TODO

Open work on this repo. Items are marked **verified** (I reproduced it) or
**suspected** (reasoned from the code, not yet triggered).

---

## Decisions needed

### Route `/doc-search` to the agent, or leave it inline?

Right now `/doc-search` loads the skill, which runs the script inline — output
lands in the caller's context. Only the agent path keeps documents out.

Rewiring means cutting `SKILL.md` down to a few lines that hand the arguments to
the agent. The skill still loads (a few hundred tokens); it just delegates
instead of executing.

The tradeoff: `/doc-search --load feature-structure` would stop returning raw
document text, since the agent summarizes by design. Leaving it inline preserves
that as a deliberate escape hatch for when you *want* the full document — editing
it, quoting it verbatim. `CLAUDE.md` already routes the normal path to the agent,
so this only affects the explicit slash command.

**Not decided.**

### Revisit the context-cost model — OPEN DISCUSSION, resume this

**Ryan asked to be reminded of this and to walk through more scenarios. Raise it
next session; do not let it drop.**

The numbers below assume one usage shape. They are the basis for the whole
delegate-by-default design, so if the assumptions are wrong the design is wrong.
Scenarios still to work through are listed at the end.

#### Measured inputs

Corpus (measured on disk):

| Doc | Bytes | ≈ Tokens |
|---|---|---|
| `feature-structure.md` | 15,508 | 3,900 |
| `tech-stack.md` | 3,568 | 900 |
| `uix.md` | 21,254 | 5,300 |
| **Total** | **40,330** | **~10,100** |

Token counts are estimated at ~4 bytes/token. Byte counts are measured.

Agent runs (measured, actual): 20,331 and 22,186 subagent tokens, returning ~4
and ~10 lines respectively. Durations 22.4s and 7.9s.

Startup hook: 1,076 bytes ≈ 270 tokens (was 15,550 bytes before the index
change).

#### The modeled scenario

A 20-turn session asking three doc questions, at turns 5, 10, and 15.

| | Direct read | Via agent |
|---|---|---|
| Startup | 270 | 270 |
| Q1 (feature-structure) | +3,900, persists | +150 |
| Q2 (tech-stack) | +900, persists | +150 |
| Q3 (uix) | +5,300, persists | +150 |
| Docs in main context at end | **10,370** | **~720** |

Because context is re-sent every turn, the end-state figure understates it. Cost
carried across the session:

| | Direct read | Via agent |
|---|---|---|
| Opus token-turns carried | **~94,000** | **~4,500** |
| Haiku tokens (paid once, not re-sent) | 0 | ~60,000 |

At roughly 1/10–1/20 the price per token, that Haiku load is ~3–6k
Opus-equivalent. **Net ≈ 94k vs ≈ 10k Opus-equivalent, so 9–10x.**

#### Caveats — these are the important part

1. **The agent burns MORE raw tokens, not fewer.** ~20k per question versus 3,900
   to read the file directly. The entire win is *where* they are spent: on a cheap
   model, once, never re-sent. Anyone reading "9-10x cheaper" as "does less work"
   has it backwards.
2. **Direct wins for one-shot.** One question at the end of a session: 3,900
   tokens immediately, versus ~20k plus 8–22 seconds of latency. The crossover is
   roughly **2–3 turns of remaining session**. Past that, compounding dominates.
3. **Latency is real and was measured** — 7.9s and 22.4s. Not free, and it is
   paid on every question.
4. **The ~4 bytes/token estimate is unverified.** Only byte counts and subagent
   token totals are measured. Worth checking against a real tokenizer before
   leaning harder on these figures.
5. **The 20k-per-run agent cost may be mostly fixed overhead**, not proportional
   to doc size — both runs cost about the same despite doing different work. If
   so, the agent gets relatively cheaper as docs grow, and relatively worse for
   small ones. Not yet tested.
6. **Two data points is not a sample.** Both runs were on this repo, this corpus,
   this pair of tasks.

#### Scenarios still to walk through

- Very short sessions (1–3 turns) — does delegation ever pay?
- Very long sessions (50+ turns) — does the gap widen as modeled?
- Many small docs vs. few large ones, given caveat 5
- Repeat questions about the *same* doc — direct read amortizes, the agent re-pays
  ~20k every time. This may be where direct actually wins outright.
- A much larger corpus (10x the docs) — does the startup index stay small enough?
- Sessions that never touch docs at all — currently paying 270 tokens for nothing
- Auto-compaction interacting with all of this: compaction may already collapse a
  large loaded doc, which would weaken the carrying-cost argument. **Unexamined.**

---

## Bugs

### `--analyze <skill> --overwrite` can destroy that skill's manifest — verified

`analyze_skill()` writes its output to `${skill_dir}/doc-search.md`. For the
doc-search skill itself, that path *is* the manifest holding the baseline and
catalog. Running `--analyze doc-search --overwrite` would replace it with a
doc-needs file, wiping the SessionStart configuration.

Verified by running the preview (no `--overwrite`), which reports that exact
target path. Not triggered destructively.

The root cause is one filename serving two purposes: `doc-search.md` means
"manifest" inside the doc-search skill and "docs this skill needs" everywhere
else. Same shape as the baseline bug already fixed in `update_manifest()`.

Options: rename the generated file (`doc-needs.md`), rename the manifest, or
refuse to analyze the doc-search skill.

### Ambiguous doc names resolve silently — suspected

`find_doc()` falls back to `find "${DOCS_DIR}" -name "*${name}*" | head -1`.
With two docs matching a partial name, the first wins and nothing warns. As the
docs folder grows this gets more likely, and a wrong-but-plausible doc is worse
than a miss. Consider erroring on multiple matches, or reporting which was
chosen.

---

## Untested

- **`--analyze` has never been run with `--overwrite`.** Preview works; the write
  path is unexercised — and per the bug above, should not be run against
  `doc-search` until that is resolved.
- **Empty-category paths in `--update`.** `Features` and `Other Documentation`
  have been empty on every run so far, so those branches have only ever produced
  empty sections. Untested against real content.
- **No tests exist** for `doc-search.sh`. The two bugs found so far were both
  found by hand, one of them only by running the real thing. A small fixture repo
  plus a handful of assertions would have caught both.

---

## Gaps

- **`docs/features/` does not exist.** `feature-structure.md` specifies a whole
  per-feature layout that nothing in this repo uses. Until something does, the
  conditional-loading paths in `--analyze` point at directories that aren't there.
- **No second skill.** The design intends skills to declare their doc needs in a
  `doc-search.md` and have the agent fetch them. That path is documented in
  `SKILL.md` and `README.md` but has never run, because doc-search is the only
  skill here. Building one real consumer would validate the pattern.
- **Adopters may hit permission prompts.** The rule allowing
  `Bash(./.claude/skills/doc-search/doc-search.sh *)` lives in
  `.claude/settings.local.json`, which is gitignored. Someone cloning this repo
  gets the skill but not the permission. Moving it to the committed
  `.claude/settings.json` would fix that — but project settings are shared and
  trusted differently, so it is a deliberate call, not an oversight to silently
  correct.

---

## Housekeeping

- **Hook changes need a session restart** to take effect. The settings watcher
  only picks up `.claude/` when a settings file was present at session start.
  This applies to anyone pulling the repo for the first time too.
- **`README.md` describes `docs/standards/` as a sample corpus.** If this repo
  ever adopts those standards for itself, that framing needs updating.
