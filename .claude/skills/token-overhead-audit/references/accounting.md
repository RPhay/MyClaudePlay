# Where each figure comes from, and what it cannot see

## The one measured number

`cache_read_input_tokens` on `type: "assistant"` records, taken as a floor across
every transcript for the project. After a cache invalidation the read count drops
to whatever prefix survived, so the minimum across a session approximates the
static portion — system prompt, tool schemas, listings, and the instruction graph
together.

**Deduplicate by `requestId` first.** One local session held 440 assistant
records across 195 unique requests; summing naively inflates by ~2.2x.

It bounds every estimate below. Nothing identified can legitimately exceed it.

## The components

Each is sized from an `attachment` record in the transcript, so these are real
payloads that were actually sent, not reconstructions.

| Component | Record | Sized by |
|---|---|---|
| SessionStart hook output | `hook_success` | `stdout`, largest observed per distinct `hookName` + `hookEvent`, summed across hooks |
| Skill listing | `skill_listing` | serialized record; `skillCount` reported alongside |
| Deferred tool block | `deferred_tools_delta` | serialized record |
| Agent listing | `agent_listing_delta` | serialized record |
| MCP server instructions | `mcp_instructions_delta` | serialized record |
| Token-budget reminder | `total_tokens_reminder` | `text`; counted per turn, **not** cached |
| `CLAUDE.md` roots | filesystem | byte size of the user and project roots only |

The last row is deliberately shallow. `claude-md-audit` resolves the real graph —
transitive imports, ancestor nodes, the lot — and its number supersedes this one.
Sizing it properly here would duplicate that skill.

## Conversion

3.6 chars per token, measured: a control session totalled 9,513 prompt tokens, a
skill with a 120-character description made it 9,546, and the flag that removes it
from the listing returned it to 9,513 exactly. That 33-token delta over 120
characters is the constant.

One sample. It agrees with the ~424 chars / ~118 tokens per skill seen across real
`skill_listing` attachments, but it is not a tokenizer, and no tokenizer is
installed on this machine. Component figures are estimates. Say so when quoting
them.

## What the accounting cannot see

- **The system prompt and tool schemas.** They are never written to the
  transcript as a sizable payload, so they appear only as the `unaccounted`
  remainder. On a clean repo that is roughly three quarters of the baseline.
- **Whether a component is worth its cost.** Sizing a hook says nothing about
  whether its output earns the tokens.
- **Anything in a project with no transcripts.** With no history there is no
  baseline, and the report degrades to components only and says so.
- **Per-directory variation.** A nested `CLAUDE.md` loads only when the cwd is
  inside its subtree, so overhead differs by working directory. This skill
  measures the root; `claude-md-audit --dir` models others.

## Thresholds

- `HOOK_WARN = 4000` chars — **chosen, not measured.**
- `LISTED_SKILLS_WARN = 8` — **chosen, not measured.**

Both are judgments about when a number becomes worth mentioning. Neither came
from an experiment; tune them freely.
