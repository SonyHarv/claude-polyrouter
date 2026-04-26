---
name: retry
description: Retry last query with escalated model tier
user_invokable: true
---

<!-- POLY:RETRY:v1 -->
# /retry Command

Retry the last query with a higher model tier.

## Usage

```
/polyrouter:retry
```

## Escalation Path (v1.7)

- fast/* → standard/medium
- standard/* → deep/medium
- deep/medium → deep/high
- deep/high → deep/xhigh
- deep/xhigh → already at maximum (HUD shows ⚠max)

The HUD displays the trajectory while a retry is active, e.g.:
`haiku·fast → sonnet·std`. The arrow is cleared on the next normal
prompt (any prompt without the retry marker).
