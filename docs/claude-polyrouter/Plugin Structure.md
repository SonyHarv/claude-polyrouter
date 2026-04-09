# Plugin Structure

## Directory Layout

```
claude-polyrouter/
├── plugin.json                      # Plugin manifest (v1.4.0)
├── README.md
├── CHANGELOG.md
├── LICENSE
│
├── hooks/
│   ├── hooks.json                   # Hook registration (4 events)
│   ├── classify-prompt.py           # 8-stage pipeline orchestrator (~520 lines)
│   ├── cache-keepalive.py           # PostToolUse cache ping (~60 lines)
│   ├── check-update.py              # Version check on session start (~40 lines)
│   └── lib/
│       ├── __init__.py
│       ├── scorer.py                # Multi-signal scoring engine (~120 lines)
│       ├── classifier.py            # Pattern extraction + signal counting (~200 lines)
│       ├── effort.py                # Dynamic effort mapping (~50 lines)
│       ├── compact.py               # Microcompact + session memory advisory (~210 lines)
│       ├── hud.py                   # StatusLine helper: state, frames, colors (~120 lines)
│       ├── detector.py              # Language detection by stopwords (~120 lines)
│       ├── cache.py                 # Two-level cache (memory + file) (~150 lines)
│       ├── config.py                # Three-layer config merge (~100 lines)
│       ├── context.py               # Multi-turn session state (~100 lines)
│       ├── stats.py                 # Atomic stats logging (~100 lines)
│       ├── intent_override.py       # Natural language model forcing (~150 lines)
│       └── learner.py               # Knowledge-based adjustments (~120 lines)
│
├── hud/
│   └── polyrouter-hud.mjs          # Animated Poly mascot StatusLine (~140 lines)
│
├── languages/
│   ├── schema.json                  # JSON Schema for validation
│   ├── en.json … ar.json           # 10 language files
│
├── agents/
│   ├── fast-executor.md             # Quick answers (haiku tier)
│   ├── standard-executor.md         # Standard coding (sonnet tier)
│   ├── deep-executor.md             # Complex analysis (opus tier)
│   └── opus-orchestrator.md         # Multi-step task delegation
│
├── commands/                        # 10 slash commands
│   ├── route.md, stats.md, dashboard.md, config.md
│   ├── learn.md, learn-on.md, learn-off.md
│   ├── knowledge.md, learn-reset.md, retry.md
│
├── skills/                          # Backing skills for each command
│   └── <command>/SKILL.md
│
└── tests/                           # 476+ tests
    ├── test_scorer.py               # Multi-signal scoring
    ├── test_classifier.py           # Pattern extraction
    ├── test_effort.py               # Effort mapping
    ├── test_compact.py              # Compact advisory
    ├── test_keepalive.py            # Cache keep-alive
    ├── test_hud.py                  # HUD mascot, state, format
    ├── test_pipeline.py             # E2E integration
    ├── test_cache.py, test_config.py, test_context.py
    ├── test_detector.py, test_edge_cases.py
    ├── test_deep_patterns.py, test_intent_override.py
    ├── test_learner.py, test_stats.py
    └── __init__.py
```

## Runtime Files

Created at runtime, outside the plugin directory:

| File | Purpose |
|------|---------|
| `~/.claude/polyrouter/config.json` | Global configuration |
| `~/.claude/polyrouter-stats.json` | Routing statistics (global) |
| `~/.claude/polyrouter-session.json` | Multi-turn session state |
| `~/.claude/polyrouter-cache.json` | Query fingerprint cache |
| `~/.claude/polyrouter-compact.json` | Compact advisory state |
| `<project>/.claude-polyrouter/config.json` | Project config override |
| `<project>/.claude-polyrouter/learnings/` | Project knowledge base |

## Hooks

| Event | Script | Timeout | Purpose |
|-------|--------|---------|---------|
| `UserPromptSubmit` | `classify-prompt.py` | 15s | Route every query (8-stage pipeline) |
| `PostToolUse` | `cache-keepalive.py` | 5s | Detect prompt cache expiration risk |
| `StatusLine` | `polyrouter-hud.mjs` | 3s | Animated Poly mascot display |
| `SessionStart` | `check-update.py` | 5s | Version check notification |

## Agents

| Agent | Default Model | Tools | Purpose |
|-------|---------------|-------|---------|
| `fast-executor` | haiku | Read, Grep, Glob | Concise answers |
| `standard-executor` | sonnet | All | Typical coding |
| `deep-executor` | opus | All | Complex analysis |
| `opus-orchestrator` | opus | All | Task decomposition + delegation |

## Language File Format

```json
{
  "code": "es",
  "name": "Español",
  "stopwords": ["el", "la", "de", "en", "..."],
  "patterns": {
    "fast": ["regex..."],
    "deep": ["regex..."],
    "tool_intensive": ["regex..."],
    "orchestration": ["regex..."]
  },
  "follow_up_patterns": ["regex..."]
}
```

Adding a new language: create a JSON file in `languages/`. No Python changes needed.
