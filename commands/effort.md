---
name: effort
description: One-shot effort override for the next prompt — accesses xhigh (polyrouter-only)
user_invokable: true
---

<!-- POLY:EFFORT:v1 -->
# /polyrouter:effort Command

Sets a **one-shot** effort override applied to the next normal prompt.
Complements (does not replace) Claude Code's native `/effort` slider —
this command exists primarily to access **`xhigh`** (a polyrouter-only
effort level above CC's native ceiling) and to write through to the
polyrouter session so the HUD reflects the chosen effort.

## Usage

```
/polyrouter:effort <level>
```

`<level>` ∈ `{low, medium, high, xhigh}`.

Example:
```
/polyrouter:effort xhigh
```

## Behaviour (v1.7)

- **One-shot:** Applies to the **next** prompt only. Cleared automatically
  after consumption — does not contaminate subsequent turns.
- **Auto-promote on `xhigh`:** xhigh implies `deep`. If the next prompt
  would otherwise route to `fast`/`standard`, polyrouter promotes the
  tier to `deep` so the effort budget is meaningful.
- **No tier change for `low`/`medium`/`high`:** Override only the effort
  field; the classifier's tier choice stands.
- **Validation:** Invalid levels emit a `[POLY:EFFORT-ERROR]` block with
  the list of valid values; the override is **not** stored, so the next
  prompt routes normally.

## Why this exists alongside the native `/effort`

- `xhigh` — polyrouter-only level; the native slider does not reach it.
- **Visible in the polyrouter HUD** — the native slider does not write
  to `~/.claude/polyrouter-session.json`, so the HUD effort segment
  cannot reflect it.
- **One-shot semantics** — temporary boost without disturbing the
  global slider state.
