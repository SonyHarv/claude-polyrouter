---
name: advisor
description: Manual escape hatch — consult the Opus advisor with pre-loaded project context
user_invokable: true
---

<!-- POLY:ADVISOR-MANUAL:v1 -->
# /advisor Command

Manual escape hatch to consult the Opus advisor (`polyrouter:opus-orchestrator`)
with a specific architectural question. Useful when you want a deep second
opinion mid-task without triggering automatic advisor heuristics.

## Usage

```
/polyrouter:advisor "your specific question"
```

## What gets routed (v1.7)

- **Tier:** `deep`
- **Effort:** `xhigh` (locked — manual invocation already signals max-brain intent)
- **Agent:** `polyrouter:opus-orchestrator`
- **Advisor:** `required`

## Pre-loaded context

The hook pre-loads a small slice of project + conversation context into the
`[POLY:ADVISOR-MANUAL]` block so the advisor has grounding without you
restating background:

- `Project` — cwd basename
- `Branch` — current git branch (best-effort)
- `Last turn` — most recent user prompt + assistant response from the
  transcript, truncated to keep the block under ~1500 tokens

This is **not** an automatic spawn — it only fires when you invoke the
slash command. Normal advisor routing (via `requires_advisor=true`) still
emits the structured `[POLY:ADVISOR]` block but does not switch agents.
