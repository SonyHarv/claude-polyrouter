---
name: dashboard
description: Generate HTML analytics dashboard for Claude Polyrouter
---

# Analytics Dashboard

Generate a standalone HTML file with Charts.js visualizations.

## Instructions

1. Read `~/.claude/polyrouter-stats.json`
2. If the file doesn't exist, report "No routing data yet — route some queries first"
3. Generate `/tmp/polyrouter-dashboard.html` with:
   - Charts.js loaded from CDN
   - Pie chart: route distribution (fast/standard/deep)
   - Line chart: daily query trends (last 30 days)
   - Bar chart: estimated savings per session
   - Summary cards: total queries, total savings, cache hit rate
   - Language usage breakdown
   - Clean, modern dark theme
4. Open the file in the default browser:
   - macOS: `open /tmp/polyrouter-dashboard.html`
   - Linux: `xdg-open /tmp/polyrouter-dashboard.html`
   - Windows: `start /tmp/polyrouter-dashboard.html`
