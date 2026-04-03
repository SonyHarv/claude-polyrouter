# Commands

## Command Reference

| Command | Purpose |
|---------|---------|
| `/polyrouter:route <level\|model> [query]` | Manual override — force a specific tier |
| `/polyrouter:stats` | Display routing statistics in terminal |
| `/polyrouter:dashboard` | Generate HTML analytics dashboard with Charts.js |
| `/polyrouter:config` | Show active merged configuration |
| `/polyrouter:learn` | Extract routing insights from conversation |
| `/polyrouter:learn-on` | Enable continuous learning mode |
| `/polyrouter:learn-off` | Disable continuous learning mode |
| `/polyrouter:knowledge` | Display knowledge base status |
| `/polyrouter:learn-reset` | Clear knowledge base |
| `/polyrouter:retry` | Retry last query with escalated tier |

## Details

### /polyrouter:route

Accepts both levels and model names:
- `/polyrouter:route fast "query"` — uses the model configured for `fast`
- `/polyrouter:route haiku "query"` — finds which level has `haiku` and uses it
- `/polyrouter:route opus` — sets rest of conversation to opus

### /polyrouter:stats

Terminal output with:
- Total queries routed
- Cache hit rate
- Estimated savings vs always using highest tier
- Route distribution with visual bars
- Language distribution
- Last 7 days breakdown

### /polyrouter:dashboard

Generates a standalone HTML file with Charts.js:
- Pie chart: route distribution
- Line chart: daily query trends (30 days)
- Bar chart: savings per session
- Summary cards: total queries, savings, distribution
- Language usage breakdown
- Opens automatically in browser

### /polyrouter:config

Shows the effective merged configuration:
- Levels with model/agent mapping
- Default level, confidence threshold
- Cache settings
- Learning settings
- Config sources (global + project)

### /polyrouter:learn

Extracts routing insights from the current conversation:
- Identifies queries that were misrouted or manually escalated
- Generates entries for `patterns.md`, `quirks.md`, or `decisions.md`
- Saves to `<project>/.claude-polyrouter/learnings/`

### /polyrouter:learn-on / learn-off

Toggle continuous learning mode. When on, the system suggests extracting learnings every 10 queries.

### /polyrouter:knowledge

Shows knowledge base status:
- Entry counts per file (patterns, quirks, decisions)
- Last 5 insights with dates
- Whether informed routing is active

### /polyrouter:learn-reset

Clears all three learning files. Requires user confirmation before proceeding.

### /polyrouter:retry

Escalation path: `fast → standard → deep → (already at maximum)`

Reads `last_route` from session state, escalates one level, re-executes the last query with the higher tier.
