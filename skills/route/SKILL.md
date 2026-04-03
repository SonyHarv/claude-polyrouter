---
name: route
description: Manually route a query to the optimal Claude model (Haiku/Sonnet/Opus)
---

# Manual Route Override

The user wants to manually specify which model tier to use.

## Instructions

1. Parse the first argument as either a level name (`fast`, `standard`, `deep`) or a model name (`haiku`, `sonnet`, `opus`)
2. If a model name is given, find which level maps to that model in the active config
3. If a query follows, spawn the appropriate subagent with that query
4. If no query follows, inform the user that subsequent queries will use that tier

## Level-to-Model Mapping (defaults)

- `fast` / `haiku` → `polyrouter:fast-executor`
- `standard` / `sonnet` → `polyrouter:standard-executor`
- `deep` / `opus` → `polyrouter:deep-executor`

## Action

Spawn the appropriate subagent:
```
Agent(subagent_type="polyrouter:<agent>", prompt="<user's query>", description="Manual route to <model>")
```
