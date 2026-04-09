# Claude Polyrouter

![Version](https://img.shields.io/badge/version-1.4.0-blue) ![Tests](https://img.shields.io/badge/tests-501%20passed-brightgreen) ![Languages](https://img.shields.io/badge/languages-10-orange) ![Token Reduction](https://img.shields.io/badge/token%20reduction-82%25-success)

Intelligent multilingual model routing for Claude Code. Automatically routes queries to the optimal model tier (Haiku/Sonnet/Opus) based on complexity, with native support for 10 languages.

## Highlights

- **82% token reduction** — additionalContext reduced from ~150 tokens (v1.3) to ~27 tokens
- **100% classification accuracy** — 30/30 on multilingual test suite across 10 languages
- **501 tests passing** — Full coverage across scorer, HUD, effort, keepalive, compact, and more
- **Zero configuration** — Works out of the box with auto-hook injection

## Features

- **Multi-signal scoring** — 9-signal weighted scoring engine (patterns, code blocks, error traces, file paths, prompt length, tool results, conversation depth, effort level, universal tech symbols) for accurate routing
- **10 languages** — English, Spanish, Portuguese, French, German, Russian, Chinese, Japanese, Korean, Arabic, plus Spanglish detection
- **Zero API keys** — Pure rule-based classification with pre-compiled regex patterns (~3ms latency)
- **Cost savings** — 50-80% reduction by routing simple queries to cheaper models
- **Two-level cache** — In-memory LRU + file-based persistent cache for repeated queries
- **Multi-turn awareness** — Detects follow-up queries and maintains conversation context
- **Dynamic effort** — Automatic effort level mapping (low/medium/high/max) based on routing tier
- **Cache keep-alive** — PostToolUse hook detects prompt cache expiration risk
- **Compact advisory** — Recommends context compaction when stale tool results accumulate
- **Poly mascot HUD** — Animated ASCII mascot in statusLine with 6 states, cache freshness bar, zero token cost
- **Project learning** — Optional knowledge base that fine-tunes routing per project
- **Analytics** — Terminal stats and HTML dashboard with Charts.js visualizations

## Installation

```bash
claude plugin add sonyharv/claude-polyrouter
```

The plugin auto-configures the `UserPromptSubmit` hook in your `settings.json`. No manual setup needed.

## Quick Start

After installation, routing works automatically. Every query you type is classified and routed to the optimal model tier.

No configuration needed — it works out of the box.

## HUD — Poly Mascot

Poly lives in your statusLine and shows routing state at zero token cost:

```
[polyrouter] [^.^]~ · sonnet · std · cache:█████ · $12.34↓ · es
```

### Mascot States

| State | Display | Meaning |
|-------|---------|---------|
| Idle | `[^.^]~` | Ready, all good |
| Routing | `[^o^]>>` | Classifying query |
| Thinking | `[^.^]...` | Claude processing |
| Keepalive | `[~_~]zzz` | Cache drowsy (>40 min) |
| Danger | `[°O°]!!!` | Cache about to expire (>50 min) |
| Compact | `[^.^]~~~` | Recommending compaction |

### Cache Freshness Bar

| Time | Display | Color |
|------|---------|-------|
| 0-10 min | `cache:█████` | Green (fresh) |
| 10-30 min | `cache:████░` | Yellow (warm) |
| 30-50 min | `cache:███░░ !` | Orange (warning) |
| 50+ min | `cache:░░░░░ exp` | Red (expired) |

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

1. **Exception check** — Slash commands, meta-queries, and continuations bypass routing
2. **Intent override** — Natural language model forcing ("use opus") takes max priority
3. **Cache lookup** — Two-level cache (memory + file) for repeated queries
4. **Language detection** — Stopword-based scoring identifies the query language
5. **Pattern extraction** — Raw signal counting from language-specific regex patterns
6. **Multi-signal scoring** — Weighted 9-signal composite score maps to tier (fast <0.35, standard <0.65, deep >=0.65)
7. **Context boost** — Multi-turn awareness adjusts confidence for follow-up queries
8. **Learned adjustments** — Optional project knowledge base fine-tunes routing

## Supported Languages

| Language | Code | Status |
|----------|------|--------|
| English | en | Native patterns |
| Spanish | es | Native patterns (accent-tolerant) |
| Portuguese | pt | Native patterns (accent-tolerant) |
| French | fr | Native patterns |
| German | de | Native patterns |
| Russian | ru | Native patterns (declension-aware) |
| Chinese | zh | Native patterns |
| Japanese | ja | Native patterns (SOV word order) |
| Korean | ko | Native patterns |
| Arabic | ar | Native patterns |
| Spanglish | en+es | Auto-detected |

## Adding a Language

Create `languages/<code>.json` with stopwords and patterns. No code changes needed — the plugin auto-discovers language files.

## License

MIT
