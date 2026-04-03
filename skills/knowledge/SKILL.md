---
name: knowledge
description: Display Claude Polyrouter knowledge base status
---

# Knowledge Base Status

## Instructions

1. Read `<project>/.claude-polyrouter/learnings/` directory
2. If the directory doesn't exist, report "No knowledge base found for this project"
3. Count entries in each file:
   - `patterns.md` — recurring patterns
   - `quirks.md` — project-specific exceptions
   - `decisions.md` — user preferences
4. Show the last 5 entries across all files (sorted by date)
5. Report whether informed routing is active (check if learning is enabled in config)
