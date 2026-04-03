---
name: learn
description: Extract routing insights from Claude Polyrouter conversation
---

# Extract Routing Insights

Analyze the current conversation for routing patterns worth learning.

## Instructions

1. Review the conversation for:
   - Queries that were manually escalated via `/polyrouter:retry`
   - Queries where the user complained about response quality
   - Repeated routing to the same level for similar query types
   - Patterns in misrouted queries
2. For each insight found, create an entry in the appropriate file under `<project>/.claude-polyrouter/learnings/`:
   - `patterns.md` — recurring routing patterns
   - `quirks.md` — project-specific exceptions
   - `decisions.md` — explicit user preferences
3. Entry format:
   ```
   ## <Pattern Title>
   - **Discovered:** <date>
   - **Context:** <what happened>
   - **Insight:** <what to do differently>
   - **Keywords:** <comma-separated keywords for matching>
   - **Confidence:** <high|medium|low>
   ```
4. Create the learnings directory if it doesn't exist
5. Report what was learned to the user
