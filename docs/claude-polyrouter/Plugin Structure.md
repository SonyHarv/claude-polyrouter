# Plugin Structure

## Directory Layout

```
claude-polyrouter/
├── plugin.json                      # Plugin manifest
├── README.md
├── CHANGELOG.md
├── LICENSE
│
├── hooks/
│   ├── hooks.json                   # Hook registration (UserPromptSubmit + SessionStart)
│   ├── classify-prompt.py           # Orchestrator (~300 lines)
│   ├── check-update.py              # Version check on session start (~40 lines)
│   └── lib/
│       ├── __init__.py
│       ├── detector.py              # Language detection by stopwords (~120 lines)
│       ├── classifier.py            # Pattern matching + decision matrix (~200 lines)
│       ├── cache.py                 # Two-level cache (memory + file) (~150 lines)
│       ├── stats.py                 # Atomic stats logging (~100 lines)
│       ├── context.py               # Multi-turn session awareness (~100 lines)
│       └── learner.py               # Knowledge-based adjustments (~120 lines)
│
├── languages/
│   ├── schema.json                  # JSON Schema for validation
│   ├── en.json                      # English
│   ├── es.json                      # Spanish
│   ├── pt.json                      # Portuguese
│   ├── fr.json                      # French
│   ├── de.json                      # German
│   ├── ru.json                      # Russian
│   ├── zh.json                      # Chinese
│   ├── ja.json                      # Japanese
│   ├── ko.json                      # Korean
│   └── ar.json                      # Arabic
│
├── agents/
│   ├── fast-executor.md             # Quick answers (haiku tier)
│   ├── standard-executor.md         # Standard coding (sonnet tier)
│   ├── deep-executor.md             # Complex analysis (opus tier)
│   └── opus-orchestrator.md         # Multi-step task delegation
│
├── commands/                        # 10 slash commands
│   ├── route.md
│   ├── stats.md
│   ├── dashboard.md
│   ├── config.md
│   ├── learn.md
│   ├── learn-on.md
│   ├── learn-off.md
│   ├── knowledge.md
│   ├── learn-reset.md
│   └── retry.md
│
└── skills/                          # Backing skills for each command
    ├── route/SKILL.md
    ├── stats/SKILL.md
    ├── dashboard/SKILL.md
    ├── config/SKILL.md
    ├── learn/SKILL.md
    ├── learn-on/SKILL.md
    ├── learn-off/SKILL.md
    ├── knowledge/SKILL.md
    ├── learn-reset/SKILL.md
    └── retry/SKILL.md
```

## Runtime Files

Created at runtime, outside the plugin directory:

| File | Purpose |
|------|---------|
| `~/.claude/polyrouter/config.json` | Global configuration |
| `~/.claude/polyrouter-stats.json` | Routing statistics (global) |
| `~/.claude/polyrouter-session.json` | Multi-turn session state |
| `<project>/.claude-polyrouter/config.json` | Project config override |
| `<project>/.claude-polyrouter/learnings/` | Project knowledge base |

## Hooks

| Event | Script | Timeout | Purpose |
|-------|--------|---------|---------|
| `UserPromptSubmit` | `classify-prompt.py` | 15s | Route every query |
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
