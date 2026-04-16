![claude-polyrouter](assets/banner.svg)

# claude-polyrouter

![Version](https://img.shields.io/badge/version-1.5.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-558%20passed-brightgreen)
![Languages](https://img.shields.io/badge/languages-10-orange)
![Token Reduction](https://img.shields.io/badge/token%20reduction-82%25-success)
![Accuracy](https://img.shields.io/badge/accuracy-100%25-brightgreen)

> Tired of hitting Claude Code token limits? claude-polyrouter silently routes every query to the right model — stop paying Opus prices for simple questions. 82% less token waste, 10 languages, zero setup.

---

## How It Routes

| Query | Tier | Model | Effort | Reason |
|-------|------|-------|--------|--------|
| "hola" / "ok" / "what is X?" | Fast | Haiku 4.5 | low | Short or simple question |
| "create a function" / "fix this bug" | Standard | Sonnet 4.6 | medium | Coding task |
| "debug this stack trace across 3 files" | Deep | Opus 4.7 | high | Multi-file, tool-heavy |
| "redesign the auth architecture" | Deep | Opus 4.7 | **xhigh + adv** | Architectural scope → Advisor engaged |

Routing happens automatically on every query via a `UserPromptSubmit` hook. No manual intervention needed.

---

## v1.5 Highlights

- **Pinned model IDs** — `claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-opus-4-7` — display stays compact, versions stay explicit
- **Dynamic deep-tier effort** — `medium` → `high` → `xhigh` chosen per-query from multi-signal score (architecture, file count, code blocks, tool intensity)
- **xhigh tier** — polyrouter-only display label for architectural/critical work; normalizes to `high` for the `CLAUDE_CODE_EFFORT_LEVEL` env var
- **Advisor Strategy** — `requires_advisor=true` flag set automatically on `xhigh`; surfaces as `adv` in the HUD so the executor can engage the Advisor (Opus on-demand) for architectural calls
- **Subagent lifecycle tracking** — HUD shows `(subagente)` while the spawned executor is running; `SubagentStop` hook clears it
- **Architectural promotion** — non-deep queries with architecture keywords + standard signals auto-promote to `deep + xhigh` (e.g. _"plan a major refactor across services"_)

### Dynamic Escalation Examples

| Query | Tier | Effort | Advisor | Why |
|-------|------|--------|---------|-----|
| "fix typo in README" | fast | low | — | Short, no signals |
| "add pagination to /api/users" | standard | medium | — | Single-file standard task |
| "debug this 200-line stack trace" | deep | high | — | Deep + tool-intensive |
| "redesign the billing subsystem" | deep | **xhigh** | **adv** | Architectural keyword match |
| "refactor auth.py login.py session.py as a strategic migration" | deep | **xhigh** | **adv** | Arch keyword + 3 files + orchestration |

---

## v1.4.0 Highlights

- **82% token reduction** — additionalContext reduced from ~150 tokens (v1.3) to ~27 tokens
- **100% classification accuracy** — 30/30 on multilingual test suite across all 10 languages
- **Multi-signal scoring** — 9-signal weighted engine replaces simple pattern counting
- **Poly mascot HUD** — Animated ASCII mascot with cache freshness bar, zero token cost
- **Auto-hook injection** — Zero-config installation, hooks configured automatically

---

## Features

- **Multi-signal scoring** — 9-signal weighted scoring engine (patterns, code blocks, error traces, file paths, prompt length, tool results, conversation depth, effort level, universal tech symbols)
- **10 languages** — English, Spanish, Portuguese, French, German, Russian, Chinese, Japanese, Korean, Arabic, plus Spanglish detection
- **Zero API keys** — Pure rule-based classification with pre-compiled regex patterns (~3ms latency)
- **Cost savings** — 50-80% reduction by routing simple queries to cheaper models
- **Two-level cache** — In-memory LRU + file-based persistent cache for repeated queries
- **Multi-turn awareness** — Detects follow-up queries and maintains conversation context
- **Dynamic effort** — Automatic effort level mapping (low/medium/high) based on routing tier
- **Cache keep-alive** — PostToolUse hook detects prompt cache expiration risk
- **Compact advisory** — Recommends context compaction when stale tool results accumulate
- **Poly mascot HUD** — Animated ASCII mascot in statusLine with 6 states, cache freshness bar, zero token cost
- **Project learning** — Optional knowledge base that fine-tunes routing per project
- **Analytics** — Terminal stats and HTML dashboard with Charts.js visualizations

---

## Requirements

- Claude Code v2.1.70+
- Python 3.8+
- Node.js 18+

## Installation

```bash
# Step 1: Add marketplace (one-time)
claude plugin marketplace add SonyHarv/claude-polyrouter

# Step 2: Install plugin
claude plugin install claude-polyrouter@claude-polyrouter

# Step 3: Restart Claude Code
```

That's it. On first run, the plugin auto-configures:
- `UserPromptSubmit` hook in `settings.json` for automatic routing
- HUD symlink for the Poly mascot statusLine
- `current` symlink for version-agnostic paths

---

## HUD — Poly Mascot

Poly lives in your statusLine and shows routing state at zero token cost:

```
[polyrouter] [^.^]~ · sonnet · std · cache:█████ · $12.34↓ · es
[polyrouter] [^.^]~ · opus · deep · xhigh · adv · (subagente) · cache:█████ · $12.34↓ · es
```

### Status Line Tokens (left → right)

| Token | When | Meaning |
|-------|------|---------|
| `haiku` / `sonnet` / `opus` | Always (after a route) | Model family selected |
| `fast` / `std` / `deep` | Always (after a route) | Routing tier |
| `high` / `xhigh` | Deep tier only | Dynamic sub-effort — `medium` is elided |
| `adv` | `requires_advisor=true` | Advisor (Opus on-demand) is engaged |
| `(subagente)` | While subagent runs | Executor subagent currently processing |
| `cache:…` | Session active | Freshness bar (see below) |
| `$x.xx↓` | Savings > 0 | Estimated cost saved vs. always-Opus |
| language code | Language detected | `en` / `es` / `pt` / ... |

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

| Time | Display | Color | Meaning |
|------|---------|-------|---------|
| 0-10 min | `cache:█████` | Green | Fresh — cache is warm |
| 10-30 min | `cache:████░` | Yellow | Warm — still healthy |
| 30-50 min | `cache:███░░ !` | Orange | Warning — consider a query |
| 50+ min | `cache:░░░░░ exp` | Red | Expired — triggers danger state |

---

## Commands

| Command | Description |
|---------|-------------|
| `/polyrouter:route <tier> [query]` | Manual routing override |
| `/polyrouter:stats` | View routing statistics |
| `/polyrouter:dashboard` | Open HTML analytics dashboard |
| `/polyrouter:config` | Show active configuration |
| `/polyrouter:learn` | Extract routing insights from conversation |
| `/polyrouter:learn-on` | Enable continuous learning mode |
| `/polyrouter:learn-off` | Disable continuous learning mode |
| `/polyrouter:knowledge` | View knowledge base status |
| `/polyrouter:learn-reset` | Clear knowledge base |
| `/polyrouter:retry` | Retry with escalated tier |

---

## Configuration

Global config at `~/.claude/polyrouter/config.json`:

```json
{
  "default_level": "fast",
  "confidence_threshold": 0.7,
  "levels": {
    "fast":     { "model": "haiku",  "model_id": "claude-haiku-4-5",  "agent": "fast-executor" },
    "standard": { "model": "sonnet", "model_id": "claude-sonnet-4-6", "agent": "standard-executor" },
    "deep":     { "model": "opus",   "model_id": "claude-opus-4-7",   "agent": "deep-executor" }
  },
  "scoring": {
    "thresholds": { "fast_max": 0.35, "standard_max": 0.65 }
  },
  "effort": { "auto": true },
  "keepalive": { "enabled": true, "threshold_minutes": 50 },
  "compact": { "enabled": true, "keep_last_n": 5 },
  "hud": { "mascot_enabled": true, "statusline_native": true }
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

1. **Exception check** — Slash commands, meta-queries, and continuations bypass routing
2. **Intent override** — Natural language model forcing ("use opus") takes max priority
3. **Cache lookup** — Two-level cache (memory + file) for repeated queries
4. **Language detection** — Stopword-based scoring identifies the query language
5. **Pattern extraction** — Raw signal counting from language-specific regex patterns
6. **Multi-signal scoring** — Weighted 9-signal composite score maps to tier (fast <0.35, standard <0.65, deep >=0.65)
7. **Context boost** — Multi-turn awareness adjusts confidence for follow-up queries
8. **Architectural promotion** — non-deep tiers with arch keywords + signals auto-promote to deep + xhigh
9. **Dynamic effort** — deep tier receives a sub-effort (medium/high/xhigh) from score + signal mix
10. **Advisor flag** — `xhigh` sets `requires_advisor=true`, surfaced as `adv` in the HUD
11. **Learned adjustments** — Optional project knowledge base fine-tunes routing

---

## Supported Languages

| Language | Code | Notes |
|----------|------|-------|
| English | en | Native patterns |
| Spanish | es | Native patterns (accent-tolerant) |
| Portuguese | pt | Native patterns (accent-tolerant) |
| French | fr | Native patterns |
| German | de | Native patterns |
| Russian | ru | Native patterns (declension-aware) |
| Chinese | zh | Native patterns + CJK word counting |
| Japanese | ja | Native patterns (SOV word order) |
| Korean | ko | Native patterns + CJK word counting |
| Arabic | ar | Native patterns |
| Spanglish | en+es | Auto-detected |

To add a language: create `languages/<code>.json` with stopwords and patterns. Auto-discovered — no code changes needed.

---

## Roadmap

### v1.5 (completed)

- [x] Pinned model IDs (haiku-4-5 / sonnet-4-6 / opus-4-7) with compact display names
- [x] Dynamic deep-tier effort classification (medium / high / xhigh)
- [x] Architectural promotion: non-deep → deep + xhigh on arch keywords + signals
- [x] Advisor Strategy: `requires_advisor` flag + `adv` HUD tag
- [x] Subagent lifecycle tracking: `(subagente)` HUD tag + `SubagentStop` hook

### v1.4.0 (completed)

- [x] Multi-signal 9-weighted scoring engine
- [x] 10-language support with accent-tolerant patterns
- [x] Poly mascot HUD with animated states
- [x] Cache freshness bar with prefix and warning indicators
- [x] Auto-hook injection for zero-config setup
- [x] 82% token reduction in additionalContext

### v1.6 (planned)

- [ ] Retry-escalation arrow in HUD (e.g. `fast → deep`)
- [ ] Advisor hand-off protocol: standardized way for executors to consult Opus
- [ ] Effort override via `/polyrouter:effort <level>` slash command

### v2 (planned)

- [ ] Multi-agent support: Codex CLI, Gemini CLI
- [ ] Ultra tier for next-gen models
- [ ] Adaptive confidence thresholds from routing history
- [ ] Analytics export (CSV/JSON) for team reporting
- [ ] Weighted ensemble classification (rules + embeddings)
- [ ] Auto-escalation on repeated low-confidence routes

---

## Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feat/my-feature`
3. Add tests in `tests/`
4. Run the test suite: `python -m pytest tests/ -v`
5. Ensure all 558+ tests pass before submitting
6. Commit using conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
7. Open a pull request with a clear description of the change

Keep classification latency under 5ms. Maintain test coverage for all routing paths.

---

## License

MIT — by [SonyHarv](https://github.com/SonyHarv)
