# claude-polyrouter

![Version](https://img.shields.io/badge/version-1.2.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.8+-yellow)
![Languages](https://img.shields.io/badge/languages-10-orange)
![Tests](https://img.shields.io/badge/tests-105%20passing-brightgreen)

> Automatic model routing for Claude Code — sends each query to the optimal model tier based on complexity, without sacrificing quality.
>
> **10 languages · zero config · no API key · save 40-80% on tokens depending on your workload**

---

## How It Routes

| Query | Tier | Model | Reason |
|-------|------|-------|--------|
| "hola" / "ok" / "what is X?" | ⚡ Fast | Haiku | Short or simple question |
| "create a function" / "fix this bug" | ⚙️ Standard | Sonnet | Coding task |
| "design microservices architecture" | 🧠 Deep | Opus | Complex analysis |

Routing happens automatically on every query via a `UserPromptSubmit` hook. No manual intervention needed.

---

## Installation

```bash
# Step 1: Add marketplace
claude plugin marketplace add claude-polyrouter SonyHarv/claude-polyrouter

# Step 2: Install
claude plugin install claude-polyrouter@claude-polyrouter

# Step 3: Restart Claude Code
```

That's it. No configuration needed — works out of the box.

---

## HUD Integration

Real-time routing status in Claude Code's status line:

```
[OMC#4.9.3] | 5h | session:2m  [polyrouter] ⚡ haiku · es · 45q · $1.36↓
```

Fields: `model · language · total queries · estimated savings`

To enable, add to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "node $HOME/.claude/hud/polyrouter-hud.mjs"
  }
}
```

---

## Commands

| Command | Description |
|---------|-------------|
| `/claude-polyrouter:stats` | View routing statistics |
| `/claude-polyrouter:dashboard` | Open HTML analytics dashboard |
| `/claude-polyrouter:config` | Show active configuration |
| `/claude-polyrouter:route <tier> [query]` | Manual routing override |
| `/claude-polyrouter:retry` | Retry with escalated tier |
| `/claude-polyrouter:learn` | Extract routing insights from conversation |
| `/claude-polyrouter:learn-on` | Enable continuous learning mode |
| `/claude-polyrouter:learn-off` | Disable continuous learning mode |
| `/claude-polyrouter:knowledge` | View knowledge base status |
| `/claude-polyrouter:learn-reset` | Clear knowledge base |

---

## Configuration

Global config at `~/.claude/polyrouter/config.json`:

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

Project override at `<project>/.claude-polyrouter/config.json`:

```json
{
  "default_level": "standard",
  "confidence_threshold": 0.8
}
```

When new models release, update config only — no code changes needed:

```json
{
  "levels": {
    "fast": { "model": "haiku-next", "agent": "fast-executor" }
  }
}
```

---

## How It Works

1. **Exception check** — Slash commands and meta-queries bypass routing
2. **Cache lookup** — Two-level cache (memory + file) for repeated queries
3. **Length pre-classification** — Queries under 5 words route to fast tier at 90% confidence
4. **Language detection** — Stopword-based scoring identifies the query language
5. **Pattern classification** — Pre-compiled regex patterns per language determine complexity
6. **Context boost** — Multi-turn awareness adjusts confidence for follow-up queries
7. **Learned adjustments** — Optional per-project knowledge base fine-tunes routing

---

## Supported Languages

| Language | Code | Notes |
|----------|------|-------|
| English | en | Native patterns |
| Spanish | es | Native patterns |
| Portuguese | pt | Native patterns |
| French | fr | Native patterns |
| German | de | Native patterns |
| Russian | ru | Native patterns |
| Chinese | zh | Native patterns + CJK word counting |
| Japanese | ja | Native patterns + CJK word counting |
| Korean | ko | Native patterns + CJK word counting |
| Arabic | ar | Native patterns |
| Spanglish | en+es | Auto-detected |

To add a language: create `languages/<code>.json` with stopwords and patterns. Auto-discovered — no code changes needed.

---

## Roadmap v2

- [ ] Multi-agent support: Codex CLI, Gemini CLI
- [ ] Ultra tier for next-gen models (Kairos, etc.)
- [ ] Adaptive confidence thresholds from routing history
- [ ] Analytics export (CSV/JSON) for team reporting
- [ ] Weighted ensemble classification (rules + embeddings)
- [ ] Auto-escalation on repeated low-confidence routes

---

## Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feat/my-feature`
3. Add tests in `tests/`
4. Run tests: `python -m pytest tests/ -v`
5. Submit a pull request with a clear description

Commit style: `feat:` `fix:` `refactor:` `test:` `docs:`

Keep classification latency under 5ms. Maintain test coverage for all routing paths.

---

## License

MIT — by [SonyHarv](https://github.com/SonyHarv)
