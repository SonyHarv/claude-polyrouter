---
name: stats
description: Display Claude Polyrouter usage statistics and cost savings
---

# Routing Statistics

Display usage statistics from `~/.claude/polyrouter-stats.json`.

## Instructions

1. Read `~/.claude/polyrouter-stats.json`
2. If the file doesn't exist, report "No routing data yet"
3. Format the output as a table showing:
   - Total queries routed
   - Cache hit rate: percentage and count
   - Estimated savings vs always using the highest tier
   - Route distribution with visual bars (fast/standard/deep with percentages)
   - Language distribution (top languages with percentages)
   - Last 7 days breakdown (date, query count, savings)

## Output Format

```
╔══════════════════════════════════════════╗
║        Claude Polyrouter Stats           ║
╠══════════════════════════════════════════╣
║ Total queries:     <N>                   ║
║ Cache hit rate:    <N>% (<hits>/<total>) ║
║ Estimated savings: $<amount>             ║
╠══════════════════════════════════════════╣
║ Routes:                                  ║
║   fast     ████████████░░ <N>% (<count>) ║
║   standard ████████░░░░░░ <N>% (<count>) ║
║   deep     ███░░░░░░░░░░░ <N>% (<count>) ║
╠══════════════════════════════════════════╣
║ Languages:                               ║
║   <lang1> <N>% | <lang2> <N>% | ...     ║
╚══════════════════════════════════════════╝
```

Note: Stats are global — they track routing across all your projects.
