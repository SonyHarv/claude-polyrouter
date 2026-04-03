---
name: config
description: Show active Claude Polyrouter configuration
---

# Configuration Display

Show the active merged configuration.

## Instructions

1. Check for config files:
   - Global: `~/.claude/polyrouter/config.json`
   - Project: `<project-root>/.claude-polyrouter/config.json`
2. Display which files were found and which were applied
3. Show the effective merged configuration:
   - Level mappings (fast→model, standard→model, deep→model)
   - Default level
   - Confidence threshold
   - Cache settings (L1 size, L2 size, L2 TTL)
   - Learning settings (enabled, suggest interval, max boost)
4. Highlight any values that differ from defaults
