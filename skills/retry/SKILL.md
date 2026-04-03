---
name: retry
description: Retry last query with escalated Claude Polyrouter model tier
---

# Retry with Escalation

Retry the last query using a higher model tier.

## Instructions

1. Read `~/.claude/polyrouter-session.json` to get `last_route` and `last_query`
2. If no session data exists, report "No previous query to retry"
3. Determine escalation:
   - `fast` → `standard`
   - `standard` → `deep`
   - `deep` → report "Already at maximum tier (deep). Cannot escalate further."
4. Spawn the escalated agent with the original query:
   ```
   Agent(subagent_type="polyrouter:<escalated-agent>", prompt="<last_query>", description="Retry with <escalated-level>")
   ```
