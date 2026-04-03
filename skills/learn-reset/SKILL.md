---
name: learn-reset
description: Clear Claude Polyrouter knowledge base
---

# Clear Knowledge Base

## Instructions

1. Ask the user for confirmation: "This will clear all learned routing patterns for this project. Continue? (yes/no)"
2. If confirmed:
   - Clear contents of `<project>/.claude-polyrouter/learnings/patterns.md`
   - Clear contents of `<project>/.claude-polyrouter/learnings/quirks.md`
   - Clear contents of `<project>/.claude-polyrouter/learnings/decisions.md`
3. Report what was cleared (entry counts per file before clearing)
4. If not confirmed, report "Knowledge base preserved"
