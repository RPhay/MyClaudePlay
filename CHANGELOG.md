# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This repo has no commits yet, so everything below is unreleased.

## [Unreleased]

### Added

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

- **SessionStart hook now loads an index, not documents.** Baseline output went
  from 15,550 bytes to 1,076 — and covers all three standards docs instead of
  one. Full document text now loads on demand, through the agent.
- **Baseline expanded** from `feature-structure.md` alone to all three standards
  docs.
- **`CLAUDE.md` reduced** to a project description plus one line pointing at the
  doc-search rules. Previously carried a stack/standards section that duplicated
  what the docs themselves say.

### Fixed

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

- `--analyze doc-search --overwrite` would overwrite the doc-search manifest,
  since `analyze_skill()` writes to `<skill>/doc-search.md` and that path is the
  manifest for this particular skill. Not yet fixed.
- `/doc-search` still runs the skill inline, so its output lands in the caller's
  context. Only the agent path keeps documents out.
- Hook changes require a restart; the settings watcher only picks up `.claude/`
  when a settings file was present at session start.
