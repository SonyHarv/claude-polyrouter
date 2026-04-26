# Adding a New Routing Tier

Status: data-driven (CALIDAD #16, v1.7).
Audience: maintainers extending claude-polyrouter when Anthropic ships a new
model family or pricing tier (e.g. an "ultra" tier above Opus 4.7).

---

## TL;DR

Adding a tier is a **config-only** change. No edits to `scorer.py`,
`effort.py`, or `classify-prompt.py` are required for the routing pipeline
to recognise the new tier.

You will:

1. Append the tier to `tier_order`.
2. Add a `levels.<tier>` entry with `model`, `agent`, `default_effort`,
   and pricing (or `null` if pricing is not yet finalised).
3. Add a `<tier>_max` threshold to `scoring.thresholds` for every
   non-terminal tier (the catch-all needs no max).
4. Run `pytest tests/test_tier_extensibility.py` to confirm the
   harness still routes correctly with your new tier.

---

## Step-by-step (worked example: adding "ultra")

### 1. Edit `~/.claude/polyrouter/config.json` (or project override)

```json
{
  "tier_order": ["fast", "standard", "deep", "ultra"],
  "levels": {
    "fast":     { "model": "haiku",      "agent": "fast-executor",      "default_effort": "low",    "cost_per_1k_input": 0.001, "cost_per_1k_output": 0.005 },
    "standard": { "model": "sonnet",     "agent": "standard-executor",  "default_effort": "medium", "cost_per_1k_input": 0.003, "cost_per_1k_output": 0.015 },
    "deep":     { "model": "opus",       "agent": "deep-executor",      "default_effort": "high",   "cost_per_1k_input": 0.015, "cost_per_1k_output": 0.075 },
    "ultra":    { "model": "opus-ultra", "agent": "deep-executor",      "default_effort": "xhigh",  "cost_per_1k_input": null,  "cost_per_1k_output": null  }
  },
  "scoring": {
    "thresholds": {
      "fast_max":     0.30,
      "standard_max": 0.55,
      "deep_max":     0.80
    }
  }
}
```

Notes:

- **Threshold count.** `tier_order` has N entries → `thresholds` has N-1
  `<tier>_max` keys (last tier is the unbounded catch-all).
- **Pricing.** `null` is allowed and yields `savings = 0` for that tier
  in stats output. Replace with real numbers once Anthropic publishes
  them (the savings calc picks them up on the next hook fire — no
  restart needed).
- **Agent.** Reuse `deep-executor` if the new tier shares dispatch
  semantics, or add a new agent definition under `agents/`.
- **default_effort.** Must be one of `low | medium | high | xhigh`.

### 2. Verify with the extensibility harness

```bash
.venv-dev/bin/python -m pytest tests/test_tier_extensibility.py -v
```

All 20 tests should pass. They exercise:
- `score_to_tier` walks the new `tier_order`
- `effort_for_tier` reads `default_effort` from your config
- `validate_config` warns on inconsistencies (missing thresholds,
  non-monotonic boundaries, levels/tier_order mismatches)
- `_calculate_savings` tolerates `null` pricing

### 3. Run the full suite + coverage gate

```bash
.venv-dev/bin/python -m pytest tests/ -q
./scripts/poly-coverage.sh
```

Both should remain green. Coverage gate is 80%.

### 4. (Optional) Add tier-specific tests

If your new tier has unusual behavior (e.g. a custom advisor flow,
mandatory `requires_advisor=true`, special prompt prefix), add a
dedicated `tests/test_<tier>_routing.py` mirroring
`test_tier_extensibility.py` patterns.

---

## What `validate_config` will catch

`load_config()` runs `validate_config()` and emits warnings to stderr
for any of these (but never blocks the hook — bad config falls back to
defaults):

| Symptom | Warning |
|---|---|
| Tier in `tier_order` but no `levels.<tier>` | `tier_order references 'X' which has no levels.X entry` |
| `levels.<tier>` defined but absent from `tier_order` | `levels.X defined but missing from tier_order` |
| Missing `<tier>_max` for a non-terminal tier | `scoring.thresholds.X_max missing; defaulting to legacy value` |
| Threshold not greater than previous one | `scoring.thresholds.X_max=N not greater than previous boundary` |
| `default_effort` outside the env-valid set | `levels.X.default_effort='Y' not in [...]` |

---

## Removing a tier

The reverse operation also requires no code changes:

1. Drop the tier from `tier_order`.
2. Remove its `levels.<tier>` entry.
3. Remove the matching `<tier>_max` from `thresholds`.
4. Re-run `pytest`. Any session-state JSON referencing the old tier name
   will be silently coerced (cache hits with stale tier names fall
   through to live re-classification).

---

## Why this design (CALIDAD #16)

Before v1.7, tier names were hardcoded across three files:
`scorer.py` (`fast_max`/`standard_max`), `effort.py` (`EFFORT_MAP`), and
`config.py` (DEFAULT_CONFIG levels). Adding a tier required editing all
three in lockstep — easy to forget one, and impossible for end users
without code changes.

The current architecture treats tier names as data:
- `tier_order` is the canonical list, used everywhere.
- `score_to_tier` walks it and looks up `<tier>_max` keys.
- `effort_for_tier` looks up `default_effort` from `levels`.
- `_calculate_savings` iterates `levels.values()` and tolerates null.

So the only required surface for a new tier is `config.json`.
