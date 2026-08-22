# What this audit knows, and what it does not

## The Read cap is read, not assumed

Claude Code emits an `attachment` record of type `read_truncation_notice` when a
`Read` exceeds the cap. Its banner carries the path, the total line count, the
file's real token count, and the cap that was applied:

```
[Truncated: PARTIAL view — /Users/…/digikamrc: showing lines 1-1648 of 2264
 total (29189 tokens, cap 25000). Call Read with offset=1649 limit=1648 …]
```

`layout.py` parses the cap out of that banner, so the figure stays correct if the
cap ever changes. `DEFAULT_CAP = 25000` applies only when no notice has ever been
recorded for the project, and in that case nothing is reported as having
truncated anyway.

The token count in the notice is Claude Code's own, not an estimate. It is the
only real token measurement in this skill.

## Everything else in the inferred half is an estimate

File sizes are converted at 3.6 chars/token, measured elsewhere in this repo from
a 120-character skill description costing 33 listing tokens. It is one sample and
not a tokenizer; no tokenizer is installed. Prose and code tokenise differently —
a file that is mostly fenced code will run denser than the estimate suggests.

The repo's own `CLAUDE-TODO.md` records `bytes/4` and `words x1.3` differing by
about 40% on the same documents. Treat any inferred size as indicative only.

## Binary files are excluded

By extension first, then a NUL-byte sniff of the first 8 KB. Without this the
audit reported two PNGs in a surveyed collection as "~454,752 tokens — a
whole-file Read would truncate", which is meaningless: images are not read as
text and bytes-per-token does not apply to them.

## What it cannot see

- **Whether a large file is ever read.** A 400 KB file nothing opens costs
  nothing. Only the measured half distinguishes cost from potential cost.
- **Whether `.claudeignore` is doing anything.** The audit checks that heavy
  trees which exist are covered. It cannot tell whether the exclusion changed any
  behaviour.
- **Glob and Grep cost.** Only `Read` results are attributed. A wide directory
  matters when something globs it, and that is not tracked.
- **Files outside the repo.** The most-read table includes them when a session
  read them — the truncation above was a file in `~/Library/Preferences` — but
  the filesystem half only walks the root.
- **Whether splitting a file would help.** That depends on how it is read, not
  how large it is.

## Thresholds

- `FANOUT_WARN = 40` entries — **chosen, not measured.**
- `HEAVY` directory list — conventional names, not discovered.

Both are judgments about when something is worth mentioning. Tune freely.
