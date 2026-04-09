# Claude Polyrouter

Intelligent multilingual model routing for Claude Code. Automatically routes queries to the optimal model tier (Haiku/Sonnet/Opus) based on complexity, with native support for 10 languages.

## Features

- **Multi-signal scoring** — 9-signal weighted scoring engine replaces simple pattern counting for more accurate routing
- **10 languages** — English, Spanish, Portuguese, French, German, Russian, Chinese, Japanese, Korean, Arabic, plus Spanglish detection
- **Zero API keys** — Pure rule-based classification with pre-compiled regex patterns (~3ms latency)
- **Cost savings** — 50-80% reduction by routing simple queries to cheaper models
- **Two-level cache** — In-memory LRU + file-based persistent cache for repeated queries
- **Multi-turn awareness** — Detects follow-up queries and maintains conversation context
- **Dynamic effort** — Automatic effort level mapping (low/medium/high) based on routing tier
- **Cache keep-alive** — PostToolUse hook detects prompt cache expiration risk
- **Compact advisory** — Recommends context compaction when stale tool results accumulate
- **Poly mascot HUD** — Animated ASCII mascot `[^.^]` in statusLine with 6 states, zero token cost
- **Project learning** — Optional knowledge base that fine-tunes routing per project
- **Analytics** — Terminal stats and HTML dashboard with Charts.js visualizations

## Installation

```bash
claude plugin add sonyharv/claude-polyrouter
```

## Quick Start

After installation, routing works automatically. Every query you type is classified and routed to the optimal model tier.

No configuration needed — it works out of the box.

## HUD — Poly Mascot

Poly lives in your statusLine and shows routing state at zero token cost:

| State | Display | Meaning |
|-------|---------|---------|
| Idle | `[^.^]  ~` | Ready, all good |
| Routing | `[^o^] »»` | Classifying query |
| Thinking | `[^.^] ...` | Claude processing |
| Keepalive | `[~_~] zzz` | Cache drowsy (>40 min) |
| Danger | `[°O°] !!!` | Cache about to expire (>50 min) |
| Compact | `[^.^] ~~~` | Recommending compaction |

Format: `[polyrouter] [^.^] ~ · sonnet · std · $12.34↓ · es`

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
  },
  "scoring": {
    "thresholds": { "fast_max": 0.30, "standard_max": 0.65 }
  },
  "effort": { "auto": true },
  "keepalive": { "enabled": true, "threshold_minutes": 50 },
  "compact": { "enabled": true, "keep_last_n": 5 },
  "hud": { "mascot_enabled": true, "statusline_native": true }
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
2. **Intent override** — Natural language model forcing ("use opus") takes max priority
3. **Cache lookup** — Two-level cache (memory + file) for repeated queries
4. **Language detection** — Stopword-based scoring identifies the query language
5. **Pattern extraction** — Raw signal counting from language-specific regex patterns
6. **Multi-signal scoring** — Weighted 9-signal composite score maps to tier
7. **Context boost** — Multi-turn awareness adjusts confidence for follow-up queries
8. **Learned adjustments** — Optional project knowledge base fine-tunes routing

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
