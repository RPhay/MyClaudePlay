---
name: token-benchmark
description: Runs a controlled A/B over claude -p to test whether a change actually reduced token cost. Each arm is a directory copied into a fresh temporary workspace; every arm answers the same prompts the same number of times, and results are reported with spread rather than as a single number. Use to verify a recommendation from the audit skills before trusting it, or to check a claim made by any skill or article. Spends real money — always dry-run first.
allowed-tools: ["Read", "Glob", "Write", "Bash(python3:*)", "Bash(git:*)", "Bash(claude:*)"]
disable-model-invocation: true
argument-hint: "--arms <dir> --prompts <file> [--n 5] [--model haiku]"
---

# token-benchmark

The falsification layer. Everything else in this set reports what *is*; this one
tests whether a change *helped*.

## This spends money. Dry-run first, every time.

```
python3 "$(git rev-parse --show-toplevel)/.claude/skills/token-benchmark/scripts/bench.py" \
  --arms <dir> --prompts <file> --n 5 --dry-run
```

It prints the plan — arms, prompts, runs, total API calls, worst-case spend — and
stops. **Show the user that plan and get agreement before running for real.** The
call count is `arms x prompts x n`, which grows faster than people expect: four
arms, five prompts and n=5 is 100 invocations.

Then drop `--dry-run`.

## Setting it up

An **arm** is a directory. Its contents — `CLAUDE.md`, `.claude/`, anything else —
are copied into a fresh temporary workspace for every single run, so arms cannot
contaminate each other and no run inherits state from the last. The first arm
alphabetically is the baseline everything is compared against.

A **prompts file** is one prompt per line; `#` comments are skipped. Use prompts
that exercise the thing under test. A change to `CLAUDE.md` will not show up in a
prompt that never triggers the instructions it altered.

Runs use `--no-session-persistence`, so benchmarking does not pollute the
transcript store the audit skills read.

## Reading the result

The metric is total tokens per run: input + cache read + cache write + output.

**Overlapping ranges mean the arms were not distinguished.** That is a null
result, and it is a real result. Report it as one. The most rigorous thing in the
corpus this skill set was built in response to was a benchmark whose own README
recorded that its published headline did not reproduce; the least rigorous printed
a hardcoded constant as a measurement.

**No p-values are computed**, deliberately. At n=5, on this distribution, they
would imply more confidence than the data carries. The honest test at this sample
size is whether the observed ranges overlap, and that is what is reported.

Non-overlap at small n is suggestive, not established. Say "suggests" and give the
n. Never round a 0.7% difference up to a claim.

## Rules

1. **Never report a mean without its spread.** A single number invites the
   overclaiming this whole set exists to avoid.
2. **Report null results in the same voice as positive ones.** "No difference
   detected at n=5" is the finding, not a failed experiment.
3. **Never extrapolate across models or prompt shapes.** A result on Haiku with
   short prompts says nothing about Opus in a long agentic session.
4. **Do not tune the prompt set until an arm wins.** Fix the prompts before
   running, and say so if they change.
5. **Failed runs are reported, never silently dropped.** The output states how
   many of each cell succeeded.

## Worked example

Two arms differing only by a 420-byte `CLAUDE.md`, one prompt, n=3 on Haiku:

```
none      mean 26,037  sd 45  range 25,998-26,086
verbose   mean 26,219  sd 43  range 26,170-26,244  +0.7% vs none
```

Ranges do not overlap, so the difference is real at this n — and it is 182 tokens.
Worth knowing, not worth acting on. That distinction is the point of the skill.
