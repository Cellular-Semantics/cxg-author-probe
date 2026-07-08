# ROADMAP — cxg-author-probe

Larger design directions to validate/decide over time. (For concrete, near-term
follow-ups see `TODO.md`.)

## Validate the skill / sub-agent split before optimizing it

- [ ] **Test whether the skill+sub-agent split is actually needed for context
  hygiene; if not, collapse to all-skills for token efficiency.**

  **Why.** The orchestrator-skill + judgment-sub-agent pattern — the
  `author-annotations` skill dispatching the `author-category-picker` sub-agent —
  is justified primarily by **context isolation** (keeping per-dataset /
  exploratory work out of the caller's context), plus parallelism and
  tool-scoping. If that isolation isn't actually needed, sub-agents cost more: a
  fresh context per dispatch, re-loading of shared context, and the final-message
  handoff. Collapsing sub-agents into skills would be more token-efficient.

  **Action.** Compare the split vs an all-skills variant on representative tasks
  (the n=73 picker corpus; `read-source` on the GEO/SCP/cherita examples).
  Measure token cost, output quality, and whether the caller's context is
  actually polluted enough to matter. Decide per component.

  **Breaking-change caveat.** On the *plugin* surface, skills/agents are
  addressed by name; converting a sub-agent to a skill (or renaming) breaks
  consumers that invoke by name (`subagent_type=`, `/commands`). Signal via a
  `plugin.json` version bump + changelog. The Python/CLI/schema surface is
  unaffected. `read-source` is greenfield; `author-category-picker` is released +
  benchmarked (treat carefully).

## Enforce agentic writers' output schemas with predeclare + write-hook

- [ ] **Every agentic writer (skill/sub-agent that writes an artifact) both
  predeclares its output schema AND has a `PostToolUse(Write|Edit)` hook that
  enforces it.** (Standard: memory `skill-design-principles` #5.)

  **Why.** Programmatic stages (`probe`/`pull`/`cas`) already validate by
  constructing/validating a typed model at write. LLM-written artifacts are only
  soft-enforced by orchestrator prose today — a bad `picks-v1` (or future
  agent-written `cas-v1`) can slip through until something loads it as a model.

  **What.** Per writer: (a) predeclare `output: {schema: …}` in the SKILL.md /
  agent `.md` frontmatter (the contract); (b) add a **plugin-level** hook
  (plugin-shipped agents cannot declare `hooks` in frontmatter) on `Write|Edit`,
  matched to the artifact's output path, that runs the check and blocks + returns
  errors as a correction signal. The hook can be a thin wrapper over the existing
  CLI: `cxg-author validate <file>` (sniffs `schema_version`) for JSON artifacts;
  `cxg-author verify <obs>` for the behavioural obs contract.

  **Targets.**
  | Writer | Output | Hook runs |
  |---|---|---|
  | `author-category-picker` (sub-agent) | `picks-v1` | `cxg-author validate` |
  | future cas / enrichment writer | `cas-v1` | `cxg-author validate` |
  | `read-source` (skill) | obs contract | `cxg-author verify` |

  Generalises the atlas-reporter pattern (`check_*.py` in `.claude/settings.json`)
  to the module plugin. The module ships no plugin `hooks/` today — that's the gap.
