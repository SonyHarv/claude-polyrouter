# Claude Polyrouter

Intelligent multilingual model routing for Claude Code. Automatically routes queries to the optimal model tier (Haiku/Sonnet/Opus) based on complexity, with native support for 10 languages.

## Features

- **Automatic routing** — Every query is classified and routed to the right model tier via a UserPromptSubmit hook
- **10 languages** — English, Spanish, Portuguese, French, German, Russian, Chinese, Japanese, Korean, Arabic, plus Spanglish detection
- **Zero API keys** — Pure rule-based classification with pre-compiled regex patterns (~1ms latency)
- **Cost savings** — 50-80% reduction by routing simple queries to cheaper models
- **Two-level cache** — In-memory LRU + file-based persistent cache for repeated queries
- **Multi-turn awareness** — Detects follow-up queries and maintains conversation context
- **Project learning** — Optional knowledge base that fine-tunes routing per project
- **Configurable levels** — Routing tiers abstracted from models; update models in config, not code
- **Analytics** — Terminal stats and HTML dashboard with Charts.js visualizations

## Installation

```bash
claude plugin add sonyharv/claude-polyrouter
```

## Quick Start

After installation, routing works automatically. Every query you type is classified and routed to the optimal model tier.

No configuration needed — it works out of the box.

## Commands

| Command | Description |
|---------|-------------|
| `/polyrouter:route <tier> [query]` | Manual routing override |
| `/polyrouter:stats` | View routing statistics |
| `/polyrouter:dashboard` | Open HTML analytics dashboard |
| `/polyrouter:config` | Show active configuration |
| `/polyrouter:learn` | Extract routing insights |
| `/polyrouter:learn-on` | Enable continuous learning |
| `/polyrouter:learn-off` | Disable continuous learning |
| `/polyrouter:knowledge` | View knowledge base status |
| `/polyrouter:learn-reset` | Clear knowledge base |
| `/polyrouter:retry` | Retry with escalated tier |

## Configuration

### Global Config

Create `~/.claude/polyrouter/config.json` to customize:

```json
{
  "default_level": "fast",
  "confidence_threshold": 0.7,
  "levels": {
    "fast":     { "model": "haiku",  "agent": "fast-executor" },
    "standard": { "model": "sonnet", "agent": "standard-executor" },
    "deep":     { "model": "opus",   "agent": "deep-executor" }
  }
}
```

### Project Override

Create `<project>/.claude-polyrouter/config.json` to override per-project:

```json
{
  "default_level": "standard",
  "confidence_threshold": 0.8
}
```

### Model Updates

When new models release, update config — no code changes needed:

```json
{
  "levels": {
    "fast": { "model": "haiku-next", "agent": "fast-executor" }
  }
}
```

## How It Works

1. **Exception check** — Slash commands and meta-queries bypass routing
2. **Cache lookup** — Two-level cache (memory + file) for repeated queries
3. **Language detection** — Stopword-based scoring identifies the query language
4. **Pattern classification** — Pre-compiled regex patterns per language determine complexity
5. **Context boost** — Multi-turn awareness adjusts confidence for follow-up queries
6. **Learned adjustments** — Optional project knowledge base fine-tunes routing

## Supported Languages

| Language | Code | Status |
|----------|------|--------|
| English | en | Native patterns |
| Spanish | es | Native patterns |
| Portuguese | pt | Native patterns |
| French | fr | Native patterns |
| German | de | Native patterns |
| Russian | ru | Native patterns |
| Chinese | zh | Native patterns |
| Japanese | ja | Native patterns |
| Korean | ko | Native patterns |
| Arabic | ar | Native patterns |
| Spanglish | en+es | Auto-detected |

## Adding a Language

Create `languages/<code>.json` with stopwords and patterns. No code changes needed — the plugin auto-discovers language files.

## License

MIT
