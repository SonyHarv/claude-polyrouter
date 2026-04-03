---
name: retry
description: Retry last query with escalated model tier
user_invokable: true
---

# /retry Command

Retry the last query with a higher model tier.

## Usage

```
/polyrouter:retry
```

## Escalation Path

fast → standard → deep → (already at maximum)
