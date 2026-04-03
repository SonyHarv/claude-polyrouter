<![CDATA[[![Version](https://img.shields.io/badge/version-1.2.0-blue)](https://github.com/SonyHarv/claude-polyrouter/releases/tag/v1.2.0)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-105%2F105-brightgreen)]()
[![Languages](https://img.shields.io/badge/languages-10-orange)]()

# Claude Polyrouter

Intelligent multilingual model routing for Claude Code. Automatically routes queries to the optimal model tier (Haiku/Sonnet/Opus) based on complexity, with native support for 10 languages.

## Features

- **Automatic routing** — Every query is classified and routed to the right model tier via a UserPromptSubmit hook
- **Length-based pre-classification** — Short queries (<5 words) route to fast tier at 90% confidence
- **10 languages** — English, Spanish, Portuguese, French, German, Russian, Chinese, Japanese, Korean, Arabic, plus Spanglish detection
- **CJK-aware word counting** — Accurate tokenization for Chinese, Japanese, and Korean
- **Zero API keys** — Pure rule-based classification with pre-compiled regex patterns (~1ms latency)
- **Cost savings** — 50-80% reduction by routing simple queries to cheaper models
- **Two-level cache** — In-memory LRU + file-based persistent cache for repeated queries
- **Multi-turn awareness** — Detects follow-up queries and maintains conversation context
- **Project learning** — Optional knowledge base that fine-tunes routing per project
- **Configurable levels** — Routing tiers abstracted from models; update models in config, not code
- **Analytics** — Terminal stats and HTML dashboard with Charts.js visualizations
- **HUD integration** — Real-time status line showing route, model, confidence, and language

## Routing Examples

| Query | Tier | Model | Why |
|-------|------|-------|-----|
| `hola` | fast | Haiku | Greeting, 1 word |
| `what is a variable?` | fast | Haiku | Simple question, short |
| `crea una función que ordene un array` | standard | Sonnet | Implementation task |
| `fix the login bug in auth.service.ts` | standard | Sonnet | Targeted bugfix |
| `diseña arquitectura de auth con JWT multi-tenant` | deep | Opus | Architecture design |
| `refactor the entire payment module for scalability` | deep | Opus | Large-scale refactor |

## Installation

```bash
# Add the marketplace source
claude plugin marketplace add claude-polyrouter SonyHarv/claude-polyrouter

# Install the plugin
claude plugin install claude-polyrouter@claude-polyrouter
```

## Quick Start

After installation, routing works automatically. Every query you type is classified and routed to the optimal model tier.

No configuration needed — it works out of the box.

## Commands

| Command | Description |
|---------|-------------|
| `/claude-polyrouter:route <tier> [query]` | Manual routing override |
| `/claude-polyrouter:stats` | View routing statistics |
| `/claude-polyrouter:dashboard` | Open HTML analytics dashboard |
| `/claude-polyrouter:config` | Show active configuration |
| `/claude-polyrouter:learn` | Extract routing insights |
| `/claude-polyrouter:learn-on` | Enable continuous learning |
| `/claude-polyrouter:learn-off` | Disable continuous learning |
| `/claude-polyrouter:knowledge` | View knowledge base status |
| `/claude-polyrouter:learn-reset` | Clear knowledge base |
| `/claude-polyrouter:retry` | Retry with escalated tier |

## HUD (Status Line)

Claude Polyrouter integrates with Claude Code's status line to show real-time routing information:

```
[polyrouter] sonnet · standard · 85% · es
```

The HUD displays: **model** · **tier** · **confidence** · **language** — updated on every query.

To enable, ensure the HUD path is configured in your `~/.claude/settings.json`:

```json
{
  "projects": {
    "statusLines": [
      "~/.claude/hud/polyrouter-hud.mjs"
    ]
  }
}
```

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
3. **Length pre-classification** — Queries under 5 words route to fast tier at 90% confidence
4. **Language detection** — Stopword-based scoring identifies the query language
5. **Pattern classification** — Pre-compiled regex patterns per language determine complexity
6. **Context boost** — Multi-turn awareness adjusts confidence for follow-up queries
7. **Learned adjustments** — Optional project knowledge base fine-tunes routing

## Supported Languages

| Language | Code | Status |
|----------|------|--------|
| English | en | Native patterns |
| Spanish | es | Native patterns |
| Portuguese | pt | Native patterns |
| French | fr | Native patterns |
| German | de | Native patterns |
| Russian | ru | Native patterns |
| Chinese | zh | Native patterns + CJK counting |
| Japanese | ja | Native patterns + CJK counting |
| Korean | ko | Native patterns + CJK counting |
| Arabic | ar | Native patterns |
| Spanglish | en+es | Auto-detected |

## Adding a Language

Create `languages/<code>.json` with stopwords and patterns. No code changes needed — the plugin auto-discovers language files.

## Contributing

Contributions are welcome. To get started:

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Add tests for new functionality in `tests/`
4. Ensure all tests pass: `python -m pytest tests/ -v`
5. Submit a pull request with a clear description

Guidelines:
- Follow conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- Add language patterns to `languages/<code>.json` — no code changes needed
- Keep classification latency under 5ms
- Maintain test coverage for all routing paths

## Roadmap v2

- [ ] Adaptive confidence thresholds based on routing history
- [ ] Token-count estimation for cost predictions
- [ ] Streaming classification for long prompts
- [ ] Custom pattern injection via project config
- [ ] Analytics export (CSV/JSON) for team reporting
- [ ] Weighted ensemble classification (rules + embeddings)
- [ ] Auto-escalation on repeated low-confidence routes

## License

MIT
]]>