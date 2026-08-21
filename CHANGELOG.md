# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This repo has no commits yet, so everything below is unreleased.

## [Unreleased]

### Added

- **Ambiguity reporting in `find_doc()`.** A partial name matching more than one
  document now lists every candidate on stderr and returns status 2 instead of
  silently resolving to the first match.
- **`count_lines()` helper**, because `echo "" | wc -l` reports 1 and made empty
  scans print "Found 1 standard docs".
- **Script permissions in the committed `.claude/settings.json`**, so a clone gets
  a working skill without each person adding the rule to a gitignored
  `settings.local.json`.

- **`doc-search` agent** (`.claude/agents/doc-search.md`) — runs doc-search
  operations in a subagent so document text stays out of the main session's
  context. Runs on Haiku; shells out to the skill's existing script rather than
  carrying its own copy.
- **`--refs-only` baseline loading.** `load-baseline.sh` now passes extra
  arguments through to `doc-search.sh`, letting the SessionStart hook request an
  index instead of full document content.
- **Delegation policy in the hook output.** `load-baseline.sh` emits the routing
  and wait-for-result rules alongside the doc index, so the skill carries its own
  behavior contract and adopting repos need no separate setup.
- **Install instructions** in `SKILL.md` for using the skill and agent in another
  repository.
- **This changelog** and a project `README.md`.

### Changed

- **A skill's generated doc list is now `doc-needs.md`, not `doc-search.md`.**
  One filename was serving two purposes: inside `skills/doc-search/` that name is
  the manifest. See Fixed.
- **The context-cost model was recomputed and is materially different.** The
  committed figure of 7.6x for the baseline scenario is **1.82x**. Two errors,
  both in the same direction: the Opus:Haiku price ratio is 5:1, not 15:1, and
  prompt caching — carried context is a cache read at ~0.1x base input — was
  never in the model at all. The delegate-by-default conclusion holds; the
  magnitude does not. Subagent cost was then measured against document size —
  `H(S) = 6,316 + 1.0486 x S` against script output size, R^2=0.9997 over 17
  runs — which puts the baseline scenario at **3.23x** ($0.153 vs $0.048 per
  session). Runs are near-deterministic (sd 17 tokens over 5 identical runs) and
  carry a ~6,400-token floor before any document is read. Also measured across
  four strategies (no system / load-everything / inline / agent) and across
  subagent models. Loading all docs at SessionStart is **worse than having no
  system at all** (0.82x); the skill without the agent beats unguided reading by
  only **5%**; the agent is worth 3.32x. Delegation pays 5.38x on Haiku 4.5,
  1.25x on Opus 5, and **loses money on Fable 5** — the `model: haiku` pin is
  load-bearing. Full working and all seven walked scenarios are in
  `CLAUDE-TODO.md`.

- **SessionStart hook now loads an index, not documents.** Baseline output went
  from 15,550 bytes to 1,076 — and covers all three standards docs instead of
  one. Full document text now loads on demand, through the agent.
- **Baseline expanded** from `feature-structure.md` alone to all three standards
  docs.
- **`CLAUDE.md` reduced** to a project description plus one line pointing at the
  doc-search rules. Previously carried a stack/standards section that duplicated
  what the docs themselves say.

### Fixed

- **`--analyze <skill> --overwrite` could destroy the doc-search manifest.**
  `analyze_skill()` wrote `${skill_dir}/doc-search.md`; for the doc-search skill
  that path is the manifest holding the baseline and catalog, so the run would
  have wiped the SessionStart configuration. Generated files are now
  `doc-needs.md`, removing the collision rather than guarding against it.
- **Ambiguous document names resolved silently** to whichever file
  `find | head -1` returned first. A wrong-but-plausible document is worse than a
  miss, so `find_doc()` now returns status 2, lists every candidate on stderr, and
  emits nothing. Exact filenames still resolve before the recursive search runs.
- **`--summary` returned only the document's title.** `get_summary()` ended with
  `sed '/^$/q'`, which quits at the first blank line — in markdown, the one right
  after the H1. It now keeps the heading, skips blanks and any further headings,
  and prints through to the next blank: the first paragraph the docs always
  claimed it returned.
- **Empty scans reported "Found 1".** `echo "" | wc -l` is 1, so `--analyze`
  claimed one standard doc and one feature when it had found none.
- **`--analyze` printed a `find` error** when `docs/features/` did not exist.
- **`MANIFEST` pointed at `.claude/doc-search.md`**, a path that has never
  existed. It was unused; it is now correct and used by `update_manifest()` in
  place of a duplicated literal.
- **`--update` destroyed the baseline configuration.** `update_manifest()`
  rewrites the whole manifest, and the baseline section was hardcoded to
  `feature-structure.md` inside its heredoc — so every `--update` silently
  discarded whatever the user had configured to load at session start. It now
  reads the existing baseline and carries it forward. Found by running the first
  real `--update`, which reset this repo's own three-doc baseline to one.
- **Baseline documents were silently truncated.** The old full-content load
  exceeded the harness output limit, so `feature-structure.md` arrived cut off
  roughly 2KB in while appearing complete. Loading an index removes the
  truncation entirely.

### Removed

- **`.claude/DOC_SEARCH_SETUP.md`** — predated the agent and was stale in several
  places: wrong manifest path, a `SKILL_TEMPLATE.md` that never existed, and the
  pre-`--refs-only` hook command. Superseded by `README.md` and `SKILL.md`.

### Known issues

See [CLAUDE-TODO.md](CLAUDE-TODO.md) for the full list. Notably:

- `/doc-search` runs the skill inline, so its output lands in the caller's
  context. This is deliberate — it is the escape hatch for wanting raw document
  text. Normal questions still route to the agent via `CLAUDE.md`.
- Hook changes require a restart; the settings watcher only picks up `.claude/`
  when a settings file was present at session start.
- `--analyze` uses BSD `sed -i ''` and will fail on GNU sed. macOS only.
- The subagent path itself is untested. The suite exercises the script; nothing
  verifies that the agent reports back without leaking document text, which is
  the actual product.
