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
