# Claude Polyrouter — Design Specification

**Date:** 2026-04-02
**Author:** sonyharv
**Status:** Approved
**Version:** 1.0.0

---

## 1. Overview

Claude Polyrouter is a Claude Code plugin that automatically routes user queries to the optimal model tier (Haiku/Sonnet/Opus) based on complexity, with native support for 10 languages. It reduces token consumption by sending simple queries to cheaper models while preserving full capability for complex tasks.

### Goals

1. Automatic routing via UserPromptSubmit hook — zero friction for the user
2. Native support for 10 languages: English, Spanish, Portuguese, French, German, Russian, Chinese, Japanese, Korean, Arabic, plus Spanglish
3. No external API keys required — pure rule-based classification with length boost
4. Project-level learning via knowledge base
5. Analytics: `/polyrouter:stats` and `/polyrouter:dashboard` (HTML)
6. Configurable per-project via config merge
7. Routing levels abstracted from models — future-proof

### Non-Goals

- LLM-based classification (no API key dependency)
- Per-directory config (monorepo support deferred)
- Backward compatibility with other routing solutions

---

## 2. Architecture

### 2.1 Plugin Structure

```
claude-polyrouter/
├── plugin.json
├── README.md
├── CHANGELOG.md
├── LICENSE
│
├── hooks/
│   ├── hooks.json
│   ├── classify-prompt.py           # Orchestrator (~300 lines)
│   ├── check-update.py              # SessionStart version check (~40 lines)
│   └── lib/
│       ├── __init__.py
│       ├── detector.py              # Language detection (~120 lines)
│       ├── classifier.py            # Classification engine (~200 lines)
│       ├── cache.py                 # Two-level cache (~150 lines)
│       ├── stats.py                 # Statistics logging (~100 lines)
│       ├── context.py               # Multi-turn awareness (~100 lines)
│       └── learner.py               # Knowledge-based adjustments (~120 lines)
│
├── languages/
│   ├── schema.json
│   ├── en.json
│   ├── es.json
│   ├── pt.json
│   ├── fr.json
│   ├── de.json
│   ├── ru.json
│   ├── zh.json
│   ├── ja.json
│   ├── ko.json
│   └── ar.json
│
├── agents/
│   ├── fast-executor.md
│   ├── standard-executor.md
│   ├── deep-executor.md
│   └── opus-orchestrator.md
│
├── commands/
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
└── skills/
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

### 2.2 Runtime Files (outside plugin directory)

```
~/.claude/polyrouter/config.json              # Global config
~/.claude/polyrouter-stats.json               # Global stats
~/.claude/polyrouter-session.json             # Multi-turn session state
<project>/.claude-polyrouter/config.json      # Project config override (optional)
<project>/.claude-polyrouter/learnings/       # Project knowledge base
    ├── patterns.md
    ├── quirks.md
    └── decisions.md
```

### 2.3 Design Principles

- **Level abstraction**: The classifier produces a level (`fast`, `standard`, `deep`), never a model name. The level-to-model mapping lives exclusively in config.
- **Zero-config**: Works out-of-the-box with hardcoded defaults. Config files are only needed to customize.
- **Fail-safe**: Hook errors never break the user experience. All failures fall back to safe defaults silently.
- **Token-first**: Every design decision prioritizes reducing token consumption — aggressive caching, short queries to cheap models, no unnecessary overhead.

---

## 3. Classification Pipeline

### 3.1 Six-Stage Pipeline

```
User Query
    │
    ▼
┌─────────────────────────────────────────────┐
│ 1. EXCEPTION CHECK (~0ms)                   │
│    Slash commands, router meta-queries,      │
│    empty input, continuation tokens          │
│    → skip routing, pass-through              │
└──────────────────┬──────────────────────────┘
                   │ no exception
                   ▼
┌─────────────────────────────────────────────┐
│ 2. CACHE LOOKUP (~0ms)                      │
│    MD5 fingerprint of normalized query       │
│    L1: in-memory LRU (50 entries)           │
│    L2: file-based (100 entries, 30d TTL)    │
│    → hit? return cached route               │
└──────────────────┬──────────────────────────┘
                   │ miss
                   ▼
┌─────────────────────────────────────────────┐
│ 3. LANGUAGE DETECTION (~0.1ms)              │
│    Stopword scoring per language             │
│    High confidence → single language         │
│    Low confidence → multi_eval=True          │
│    Spanglish: detects en/es mix              │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 4. RULE-BASED CLASSIFICATION (~0.5ms)       │
│    Load patterns for detected language       │
│    If multi_eval: all languages in parallel  │
│    Decision matrix → level + confidence      │
│    Early exit if confidence >= 0.85          │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 5. CONTEXT BOOST (~0ms)                     │
│    Follow-up detection via session state     │
│    Boost confidence if same conversation     │
│    Session timeout: 30 min inactivity        │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 6. LEARNED ADJUSTMENTS (~0ms)               │
│    Only if learning enabled in config        │
│    Keyword matching from knowledge base      │
│    Max boost: 0.1 (conservative)             │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │ OUTPUT           │
         │ level → model    │
         │ (config lookup)  │
         │ → inject context │
         └─────────────────┘
```

### 3.2 Exception Handling

| Exception | Detection | Behavior |
|-----------|-----------|----------|
| Slash commands | `query.startswith("/")` | Skip routing |
| Router meta-queries | keywords: `polyrouter`, `routing`, `router` | Skip routing |
| Empty/whitespace | `len(query.strip()) == 0` | Skip routing |
| Continuation tokens | `query in ["y", "sí", "ok", "continúa", "yes", "go", ...]` | Use `last_route` from session |

### 3.3 Language Detection (`detector.py`)

Hybrid approach:

1. **Stopword scoring**: Each language file contains a `stopwords` array. Score = count of stopword matches / total words. Top-scoring language wins.
2. **Confidence gate**: If `top_score > 0.15` and `top_score - second_score > 0.05`, use single language. Otherwise, flag `multi_eval=True`.
3. **Spanglish**: If both `en` and `es` score above threshold and neither dominates, classify as Spanglish — evaluate both pattern sets.
4. **Short query fallback**: Queries under 4 words use `last_language` from session state if available, otherwise evaluate all languages.

### 3.4 Rule-Based Classification (`classifier.py`)

**Pattern categories per language file**:
- `fast`: Simple questions, formatting, git ops, syntax lookups
- `deep`: Architecture, security, multi-file, trade-offs, optimization
- `tool_intensive`: Codebase search, multi-file modifications, test execution
- `orchestration`: Multi-step workflows, sequential tasks

**Decision matrix**:

```python
def decide(signals: dict[str, int], config: dict) -> tuple[str, float]:
    deep = signals.get("deep", 0)
    tool = signals.get("tool_intensive", 0)
    orch = signals.get("orchestration", 0)
    fast = signals.get("fast", 0)

    if deep and (tool or orch):
        return ("deep", 0.95)
    if deep >= 2:
        return ("deep", 0.90)
    if deep == 1:
        return ("deep", 0.70)
    if tool >= 2:
        return ("standard", 0.85)
    if tool == 1:
        return ("standard", 0.70)
    if orch:
        return ("standard", 0.75)
    if fast >= 2:
        return ("fast", 0.90)
    if fast == 1:
        return ("fast", 0.70)

    return (config.get("default_level", "fast"), 0.50)
```

### 3.5 Context Boost (`context.py`)

- Reads `~/.claude/polyrouter-session.json`
- Detects follow-up queries via language-specific `follow_up_patterns`
- If follow-up detected and `last_route` was complex, boosts confidence by 0.1
- Session state fields: `last_route`, `last_level`, `conversation_depth`, `last_query_time`, `last_language`
- Sessions expire after `config.session_timeout_minutes` (default 30)

### 3.6 Learned Adjustments (`learner.py`)

- Only active if `config.learning.informed_routing == true`
- Reads keywords from `<project>/.claude-polyrouter/learnings/patterns.md` and `quirks.md`
- Requires 2+ keyword matches in query to trigger
- Max boost: `config.learning.max_boost` (default 0.1)
- Never downgrades `deep` to `fast` — conservative only

---

## 4. Language Files

### 4.1 Schema

Each language file (`languages/<code>.json`) follows this structure:

```json
{
  "code": "es",
  "name": "Español",
  "stopwords": ["el", "la", "los", "de", "en", "que", "por", "para", "..."],
  "patterns": {
    "fast": ["regex1", "regex2"],
    "deep": ["regex1", "regex2"],
    "tool_intensive": ["regex1", "regex2"],
    "orchestration": ["regex1", "regex2"]
  },
  "follow_up_patterns": ["regex1", "regex2"]
}
```

### 4.2 Pattern Guidelines

- Patterns are regex strings, compiled once at module load
- Pattern categories (`fast`, `deep`, `tool_intensive`, `orchestration`) are fixed — they map to the decision matrix, not to routing levels
- Each language should have 7-12 patterns per category
- Patterns should capture natural phrasing in the target language, not translations of English patterns
- Unicode-aware: patterns support accented characters, CJK, Arabic script

### 4.3 Adding a New Language

1. Create `languages/<code>.json` with stopwords and patterns
2. No Python code changes required
3. The detector auto-discovers all `.json` files in `languages/`

### 4.4 Adding a New Routing Level

1. Add the level to `config.json` under `levels`
2. Add patterns for the new level in each language file under `patterns`
3. Update the decision matrix in `classifier.py` to handle the new signal
4. Create the corresponding agent file in `agents/`

Note: Adding a level requires a classifier.py change for the decision matrix. This is intentional — the decision matrix encodes routing logic that should be explicit, not auto-derived.

---

## 5. Configuration

### 5.1 Config Merge Strategy

Three layers, shallow merge (one level deep):

```
1. Hardcoded defaults (always works, no files needed)
2. Global: ~/.claude/polyrouter/config.json (overrides defaults)
3. Project: <project>/.claude-polyrouter/config.json (overrides global)
```

Merge rule: For dict values, shallow merge (`{**base, **override}`). For scalar values, override replaces base.

### 5.2 Default Configuration

```json
{
  "version": "1.0",
  "levels": {
    "fast": {
      "model": "haiku",
      "agent": "fast-executor",
      "cost_per_1k_input": 0.001,
      "cost_per_1k_output": 0.005
    },
    "standard": {
      "model": "sonnet",
      "agent": "standard-executor",
      "cost_per_1k_input": 0.003,
      "cost_per_1k_output": 0.015
    },
    "deep": {
      "model": "opus",
      "agent": "deep-executor",
      "cost_per_1k_input": 0.005,
      "cost_per_1k_output": 0.025
    }
  },
  "default_level": "fast",
  "confidence_threshold": 0.7,
  "session_timeout_minutes": 30,
  "cache": {
    "memory_size": 50,
    "file_size": 100,
    "ttl_days": 30
  },
  "learning": {
    "enabled": false,
    "informed_routing": false,
    "max_boost": 0.1
  },
  "updates": {
    "check_on_start": true,
    "repo": "sonyharv/claude-polyrouter"
  }
}
```

### 5.3 Project Override Example

A project where everything should be at least `standard`:

```json
{
  "default_level": "standard",
  "confidence_threshold": 0.8,
  "levels": {
    "fast": {
      "model": "sonnet",
      "agent": "standard-executor"
    }
  }
}
```

Result: `fast` level now uses Sonnet. `standard` and `deep` inherit from global.

### 5.4 Project Config Discovery

`find_project_config()` searches from CWD upward until it finds `.claude-polyrouter/config.json` or hits a `.git` directory (repo root) or home.

---

## 6. Agents

### 6.1 Agent Definitions

Four agents, tools restricted by tier:

| Agent | Model (default) | Tools | Role |
|-------|-----------------|-------|------|
| `fast-executor` | haiku | Read, Grep, Glob | Quick, concise answers |
| `standard-executor` | sonnet | All tools | Typical coding tasks |
| `deep-executor` | opus | All tools | Architecture, complex analysis |
| `opus-orchestrator` | opus | All tools | Multi-step task delegation |

### 6.2 Agent Behavior

- **fast-executor**: Maximum 3 sentences unless code is needed. No preamble. Suggests `/polyrouter:retry` if task is too complex.
- **standard-executor**: Standard coding assistant. Suggests retry for architectural decisions.
- **deep-executor**: Thinks deeply, considers trade-offs, verifies work.
- **opus-orchestrator**: Decomposes multi-step tasks. Delegates reads/searches to fast-tier, single-file edits to standard-tier, handles complex analysis and synthesis itself.

### 6.3 Model Independence

Agent files reference `model: haiku|sonnet|opus` in frontmatter, but the actual model used is determined by the config level mapping. If a user reconfigures `fast` to use `sonnet`, the `fast-executor` agent runs on Sonnet.

---

## 7. Hook Output

### 7.1 Routing Directive (normal case)

```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "[Claude Polyrouter] MANDATORY ROUTING DIRECTIVE\nRoute: <level> | Model: <model> | Confidence: <pct> | Method: rules\nSignals: <signal_description>\nLanguage: <detected_lang>\n\nCRITICAL: You MUST use the Task tool NOW to spawn the \"polyrouter:<agent>\" subagent.\nDo NOT respond to the user directly. Do NOT skip this step. Delegate immediately."
  }
}
```

### 7.2 Skip Directive (exceptions)

```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "[Claude Polyrouter] ROUTING SKIPPED\nReason: <reason>\n\nRespond to the user directly. Do not spawn a subagent."
  }
}
```

### 7.3 Update Notification (SessionStart)

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "[Polyrouter] Update available: v1.0.0 → v1.1.0. Run: claude plugin update claude-polyrouter"
  }
}
```

Non-blocking. Timeout: 5 seconds. Silent on failure.

---

## 8. Statistics

### 8.1 Stats Schema (`~/.claude/polyrouter-stats.json`)

```json
{
  "version": "1.0",
  "total_queries": 0,
  "routes": {
    "fast": 0,
    "standard": 0,
    "deep": 0
  },
  "cache_hits": 0,
  "languages_detected": {},
  "estimated_savings": 0.0,
  "sessions": [],
  "last_updated": null
}
```

Session entry:
```json
{
  "date": "2026-04-02",
  "queries": 15,
  "routes": { "fast": 8, "standard": 5, "deep": 2 },
  "cache_hits": 3,
  "savings": 2.40
}
```

### 8.2 Savings Calculation

```
savings = sum(queries × max_level_cost) - sum(queries × actual_level_cost)
```

Where costs come from `config.levels.<level>.cost_per_1k_input` and `cost_per_1k_output`, assuming average query of 1K input + 2K output tokens.

### 8.3 Retention

Last 30 days of session entries. Older entries pruned on write.

### 8.4 Atomic Writes

`stats.py` uses file locking (`fcntl` on Unix, `msvcrt` on Windows) + write-to-temp-then-rename to prevent corruption on concurrent access.

---

## 9. Learning System

### 9.1 Knowledge Base

Located at `<project>/.claude-polyrouter/learnings/`:

- `patterns.md` — What works well (routing insights)
- `quirks.md` — Project-specific oddities
- `decisions.md` — Architectural decisions

### 9.2 Entry Format

```markdown
## Pattern: <Title>
- **Discovered:** <ISO date>
- **Context:** <What led to this discovery>
- **Insight:** <What works and why>
- **Keywords:** <comma-separated keywords for matching>
- **Confidence:** high|medium|low
```

### 9.3 How Learning Affects Routing

1. Only active if `config.learning.informed_routing == true`
2. Reads keywords from `patterns.md` and `quirks.md`
3. Requires 2+ keyword matches in query to trigger
4. Max boost: `config.learning.max_boost` (default 0.1)
5. Conservative: never downgrades `deep` to `fast`

### 9.4 Learning Commands

| Command | Behavior |
|---------|----------|
| `/polyrouter:learn` | Extract insights from current conversation |
| `/polyrouter:learn-on` | Enable continuous learning (suggests extraction every 10 queries) |
| `/polyrouter:learn-off` | Disable continuous learning |
| `/polyrouter:knowledge` | Show entry counts per file + last 5 insights |
| `/polyrouter:learn-reset` | Clear all learnings (with confirmation) |

---

## 10. Commands

### 10.1 Command Reference

| Command | Purpose |
|---------|---------|
| `/polyrouter:route <level\|model> [query]` | Manual override — force a specific tier |
| `/polyrouter:stats` | Display routing statistics table in terminal |
| `/polyrouter:dashboard` | Generate HTML analytics dashboard with Charts.js |
| `/polyrouter:config` | Show active merged configuration |
| `/polyrouter:learn` | Extract routing insights from conversation |
| `/polyrouter:learn-on` | Enable continuous learning mode |
| `/polyrouter:learn-off` | Disable continuous learning mode |
| `/polyrouter:knowledge` | Display knowledge base status |
| `/polyrouter:learn-reset` | Clear knowledge base |
| `/polyrouter:retry` | Re-send last query with escalated tier |

### 10.2 Route Command

Accepts both levels and model names:
- `/polyrouter:route fast "query"` — uses the model configured for `fast`
- `/polyrouter:route haiku "query"` — finds which level has `haiku` and uses it
- `/polyrouter:route opus` — sets rest of conversation to opus

### 10.3 Retry Escalation Path

```
fast → standard → deep → (already at maximum)
```

Reads `last_route` from session state, escalates one level, re-executes.

### 10.4 Stats Output Format

```
╔══════════════════════════════════════════╗
║        Claude Polyrouter Stats           ║
╠══════════════════════════════════════════╣
║ Total queries:     847                   ║
║ Cache hit rate:    23% (195/847)         ║
║ Estimated savings: $12.40               ║
╠══════════════════════════════════════════╣
║ Routes:                                  ║
║   fast     ████████████░░ 52% (440)      ║
║   standard ████████░░░░░░ 35% (296)      ║
║   deep     ███░░░░░░░░░░░ 13% (111)      ║
╠══════════════════════════════════════════╣
║ Languages:                               ║
║   en 61% | es 28% | pt 8% | fr 3%       ║
╚══════════════════════════════════════════╝
```

---

## 11. Update Notifications

### 11.1 SessionStart Hook

`check-update.py` (~40 lines) runs on every session start:

1. Reads current version from `plugin.json`
2. Fetches latest release from GitHub API (`sonyharv/claude-polyrouter`)
3. Timeout: 5 seconds (non-blocking)
4. If newer version exists, injects notification as `additionalContext`
5. Silent on any failure (network, parsing, timeout)

### 11.2 Hook Registration

Registered in `hooks.json` under `SessionStart` event with 5-second timeout.

---

## 12. Session State

### 12.1 Schema (`~/.claude/polyrouter-session.json`)

```json
{
  "last_route": "deep",
  "last_level": "deep",
  "conversation_depth": 5,
  "last_query_time": "2026-04-02T20:15:00",
  "last_language": "es"
}
```

### 12.2 Behavior

- Timeout: `config.session_timeout_minutes` (default 30) of inactivity resets state
- `conversation_depth` increments each query, influences context boost
- `last_language` avoids re-detection on short follow-up queries
- Continuation tokens (`"sí"`, `"ok"`, `"continúa"`) reuse `last_route` instead of re-classifying

---

## 13. Cache

### 13.1 Two-Level Cache

| Level | Storage | Size | Scope | TTL |
|-------|---------|------|-------|-----|
| L1 | In-memory LRU dict | `config.cache.memory_size` (50) | Process lifetime | None |
| L2 | File-based JSON | `config.cache.file_size` (100) | Persistent across sessions | `config.cache.ttl_days` (30) |

### 13.2 Cache Key

MD5 fingerprint of normalized query:
1. Lowercase
2. Strip punctuation
3. Sort words (order-independent matching)
4. MD5 hash

### 13.3 Cache Eviction

- L1: LRU eviction when size exceeds limit
- L2: TTL-based expiration on read. LRU eviction on write when size exceeds limit.

---

## 14. Error Handling

### 14.1 Fail-Safe Principle

The hook must never break the user experience. Every operation is wrapped:

```python
try:
    result = classify(query)
except Exception:
    result = {"level": config["default_level"], "confidence": 0.5, "method": "fallback"}
```

### 14.2 Specific Failure Modes

| Failure | Behavior |
|---------|----------|
| Config file corrupted/missing | Use hardcoded defaults |
| Language file missing/invalid | Skip that language, continue with others |
| Cache read error | Treat as cache miss |
| Cache write error | Skip caching, classify normally |
| Stats write error | Skip stats update |
| Session state error | Treat as new session |
| Update check fails | Silent, no notification |

---

## 15. plugin.json

```json
{
  "name": "claude-polyrouter",
  "version": "1.0.0",
  "description": "Intelligent multilingual model routing for Claude Code — routes queries to optimal model tier based on complexity, with native support for 10 languages",
  "author": { "name": "sonyharv" },
  "homepage": "https://github.com/sonyharv/claude-polyrouter",
  "repository": "https://github.com/sonyharv/claude-polyrouter",
  "license": "MIT",
  "keywords": [
    "routing", "model-selection", "cost-optimization",
    "multilingual", "haiku", "sonnet", "opus",
    "polyglot", "i18n"
  ],
  "agents": [
    "./agents/fast-executor.md",
    "./agents/standard-executor.md",
    "./agents/deep-executor.md",
    "./agents/opus-orchestrator.md"
  ],
  "commands": [
    { "name": "route",       "description": "Manually route a query to a specific model tier",            "file": "./commands/route.md" },
    { "name": "stats",       "description": "Display routing statistics and cost savings",                 "file": "./commands/stats.md" },
    { "name": "dashboard",   "description": "Generate HTML analytics dashboard with Charts.js",             "file": "./commands/dashboard.md" },
    { "name": "config",      "description": "Show active configuration (global + project merged)",         "file": "./commands/config.md" },
    { "name": "learn",       "description": "Extract routing insights from current conversation",          "file": "./commands/learn.md" },
    { "name": "learn-on",    "description": "Enable continuous learning mode",                             "file": "./commands/learn-on.md" },
    { "name": "learn-off",   "description": "Disable continuous learning mode",                            "file": "./commands/learn-off.md" },
    { "name": "knowledge",   "description": "Display knowledge base status and recent learnings",          "file": "./commands/knowledge.md" },
    { "name": "learn-reset", "description": "Clear the knowledge base",                                   "file": "./commands/learn-reset.md" },
    { "name": "retry",       "description": "Retry last query with escalated model tier",                  "file": "./commands/retry.md" }
  ],
  "skills": [
    { "name": "route",       "file": "./skills/route/SKILL.md" },
    { "name": "stats",       "file": "./skills/stats/SKILL.md" },
    { "name": "dashboard",   "file": "./skills/dashboard/SKILL.md" },
    { "name": "config",      "file": "./skills/config/SKILL.md" },
    { "name": "learn",       "file": "./skills/learn/SKILL.md" },
    { "name": "learn-on",    "file": "./skills/learn-on/SKILL.md" },
    { "name": "learn-off",   "file": "./skills/learn-off/SKILL.md" },
    { "name": "knowledge",   "file": "./skills/knowledge/SKILL.md" },
    { "name": "learn-reset", "file": "./skills/learn-reset/SKILL.md" },
    { "name": "retry",       "file": "./skills/retry/SKILL.md" }
  ]
}
```

---

## 16. Roadmap v2

### 16.1 Multi-Agent Provider Support

The level abstraction already decouples routing logic from specific models. v2 extends this to support multiple AI agent providers beyond Claude Code:

```json
{
  "levels": {
    "fast": {
      "providers": {
        "claude": { "model": "haiku", "agent": "fast-executor" },
        "codex":  { "model": "codex-mini", "agent": "codex-fast" },
        "gemini": { "model": "gemini-flash", "agent": "gemini-fast" }
      }
    },
    "standard": {
      "providers": {
        "claude": { "model": "sonnet", "agent": "standard-executor" },
        "codex":  { "model": "codex", "agent": "codex-standard" },
        "gemini": { "model": "gemini-pro", "agent": "gemini-standard" }
      }
    },
    "deep": {
      "providers": {
        "claude": { "model": "opus", "agent": "deep-executor" },
        "codex":  { "model": "codex-reasoning", "agent": "codex-deep" },
        "gemini": { "model": "gemini-ultra", "agent": "gemini-deep" }
      }
    }
  },
  "active_provider": "claude"
}
```

The classifier remains unchanged — it still produces levels. The provider resolution layer maps levels to provider-specific models. Adding a new provider = adding entries to config, no Python changes.

### 16.2 Ultra Tier

A fourth routing level for next-generation models (Kairos, etc.) that exceed current Opus capabilities:

```json
"ultra": {
  "model": "kairos",
  "agent": "ultra-executor",
  "cost_per_1k_input": 0.010,
  "cost_per_1k_output": 0.050
}
```

Requires:
- Adding `ultra` patterns to each language JSON
- One new branch in the decision matrix
- One new agent file

The architecture already supports this — levels are strings, not an enum.

### 16.3 Cross-Agent Routing

Route different parts of a complex task to different providers based on their strengths:

- Code generation → Codex
- Analysis/reasoning → Claude Opus
- Fast lookups → Gemini Flash

This builds on the orchestrator pattern already in v1, extending delegation across providers instead of just across tiers.

### 16.4 v2 Compatibility

v1 config files remain valid in v2. The `providers` key is optional — if absent, the flat `model`/`agent` fields are used (v1 format). Zero migration required.
```
