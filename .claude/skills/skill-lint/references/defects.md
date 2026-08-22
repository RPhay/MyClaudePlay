# Where each check came from

Every defect `lint.py` looks for was found in a real, published skill collection —
none is hypothetical. The five MIT-licensed repos surveyed in 2026-08 were
`claude-code-optimizer`, `Claude-Skills`, `claude-token-optimizer`,
`claude-token-efficient`, and `claude-code-token-optimization`.

## Measured facts the checks rely on

**A skill's identity is its directory name.** A skill in `dirname-alpha/`
declaring `name: namefield-beta` is listed and invoked as `dirname-alpha`, while
its `description` is still read from the frontmatter. Measured against Claude
Code 2.1.239 with a canary run.

This demotes two checks that look alarming. A `name` disagreeing with its
directory is inert. Two skills declaring the same `name` are not in conflict —
an earlier hand audit of `Claude-Skills` called `one-skill-to-rule-them-all`
declaring `task-observer` a collision with the real `task-observer/`; it is not.

**A listed skill costs tokens on every turn, proportional to its description.**
Measured: a control session with no skill totalled 9,513 prompt tokens; adding one
skill with a 120-character description made it 9,546; adding
`disable-model-invocation: true` returned it to 9,513 exactly. So the flag removes
the skill from the listing entirely and its always-on cost is zero. The 3.6
chars/token constant in `lint.py` comes from that 33-token delta, and agrees with
the ~424 chars / ~118 tokens per skill seen across real `skill_listing`
attachments in local transcripts.

**`allowed-tools` in SKILL.md grants nothing and restricts nothing.** Measured in
both `-p` and interactive mode: a skill listing only `Read` still ran Bash `echo`,
and a skill listing `Write` was still blocked from writing. Runtime permission
comes from session settings alone. This is why the `--apply` rules forbid Bash
writes — the permission dialog is the only real control, and `Edit`/`Write` are
the only tools that render a diff inside it.

## Checks, and where each was observed

| Check | Observed in |
|---|---|
| No frontmatter at all | 4 skills in `Claude-Skills` (`ExploitGym-paper-to-security-skill`, `find-bugs`, `promptor-council`, `skill-creator`) and `claude-token-optimizer/antigravity`, whose YAML was flattened onto one unfenced line |
| Frontmatter with no `name` | `Claude-Skills/repo-security-audit` |
| `name` disagreeing with directory | `Intellectual-Sparring-Partner` → `collaborative-technical-peer-review`; `one-skill-to-rule-them-all` → `task-observer`; `antigravity2.0` → `antigravity-protocol`; `ultimate-protocol` → `ultimate-protocol-simulator` |
| Duplicate `name` fields | `task-observer`, declared by two directories in `Claude-Skills` |
| Directory in a skills root with no SKILL.md | `Claude-Skills/skills/charge-sentry-kit` — 37 directories, 36 skill files |
| Oversized body | 14 of 36 in `Claude-Skills`. `skill-factory` is 956 lines / 26 KB in one file *while having 7 supporting files it could have used* |
| Description near the length limit | `one-skill-to-rule-them-all` at 1002 of 1024 characters |
| Overlapping descriptions | `claude-code-optimizer` ships both `plan` and `planning` |

## Thresholds, and their standing

- `DESC_LIMIT = 1024` — a hard limit, not a preference.
- `BODY_WARN = 8000` bytes — **chosen, not measured.** A judgment about where
  progressive disclosure starts to matter. Tune it freely.
- `OVERLAP_MIN = 0.55` Jaccard — **inferred.** Word-set similarity is not meaning.
  It surfaces candidates for a human to judge; it does not decide.
- `CHARS_PER_TOKEN = 3.6` — measured, see above, but it is a ratio derived from a
  single 120-character sample and should be re-derived if precision matters.

## Not checked

- Whether a description actually triggers well. That needs behavioural testing,
  not static analysis.
- Whether a skill's body does what its description claims.
- Whether `allowed-tools` entries are valid tool names. The CLI documents
  `Bash(git *)` with a space while settings files use `Bash(git:*)` with a colon;
  both appear in the wild and the discrepancy is unresolved, so flagging either
  form would produce false positives.
