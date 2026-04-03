---
name: route
description: Manually route a query to a specific model tier
user_invokable: true
---

# /route Command

Manually override automatic routing and force a specific model tier.

## Usage

```
/polyrouter:route <level|model> [query]
```

## Examples

- `/polyrouter:route fast "what is a closure"` — force fast tier
- `/polyrouter:route opus` — set conversation to opus tier
- `/polyrouter:route haiku "git status"` — use haiku by model name
