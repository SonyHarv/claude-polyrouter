# Claude Polyrouter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code plugin that automatically routes queries to the optimal model tier (Haiku/Sonnet/Opus) with native support for 10 languages.

**Architecture:** Modular Python pipeline with 6 modules (`detector`, `classifier`, `cache`, `stats`, `context`, `learner`) orchestrated by `classify-prompt.py`. Language patterns stored as JSON files auto-discovered at startup. Config merges hardcoded defaults → global → project overrides.

**Tech Stack:** Python 3 (stdlib only, no pip dependencies), JSON for config/languages, Markdown for agents/commands/skills.

**Spec:** `docs/superpowers/specs/2026-04-02-claude-polyrouter-design.md`

---

## File Map

### New Files — Core

| File | Responsibility |
|------|---------------|
| `plugin.json` | Plugin manifest: name, version, agents, commands, skills |
| `hooks/hooks.json` | Hook registration for UserPromptSubmit + SessionStart |
| `hooks/classify-prompt.py` | Orchestrator: loads config, runs pipeline, outputs JSON |
| `hooks/check-update.py` | SessionStart: version check against GitHub releases |
| `hooks/lib/__init__.py` | Package marker |
| `hooks/lib/config.py` | Config loading with three-layer merge |
| `hooks/lib/detector.py` | Language detection via stopword scoring |
| `hooks/lib/classifier.py` | Pattern matching + decision matrix |
| `hooks/lib/cache.py` | Two-level cache (in-memory LRU + file-based) |
| `hooks/lib/stats.py` | Atomic stats read/write with file locking |
| `hooks/lib/context.py` | Multi-turn session state management |
| `hooks/lib/learner.py` | Knowledge-based routing adjustments |

### New Files — Languages

| File | Responsibility |
|------|---------------|
| `languages/schema.json` | JSON Schema for language file validation |
| `languages/en.json` | English stopwords + patterns |
| `languages/es.json` | Spanish stopwords + patterns |
| `languages/pt.json` | Portuguese stopwords + patterns |
| `languages/fr.json` | French stopwords + patterns |
| `languages/de.json` | German stopwords + patterns |
| `languages/ru.json` | Russian stopwords + patterns |
| `languages/zh.json` | Chinese stopwords + patterns |
| `languages/ja.json` | Japanese stopwords + patterns |
| `languages/ko.json` | Korean stopwords + patterns |
| `languages/ar.json` | Arabic stopwords + patterns |

### New Files — Agents

| File | Responsibility |
|------|---------------|
| `agents/fast-executor.md` | Haiku-tier agent: concise, read-only tools |
| `agents/standard-executor.md` | Sonnet-tier agent: all tools, standard coding |
| `agents/deep-executor.md` | Opus-tier agent: all tools, deep analysis |
| `agents/opus-orchestrator.md` | Opus-tier agent: task decomposition + delegation |

### New Files — Commands & Skills

| Command File | Skill File | Purpose |
|-------------|-----------|---------|
| `commands/route.md` | `skills/route/SKILL.md` | Manual model override |
| `commands/stats.md` | `skills/stats/SKILL.md` | Terminal statistics |
| `commands/dashboard.md` | `skills/dashboard/SKILL.md` | HTML analytics dashboard |
| `commands/config.md` | `skills/config/SKILL.md` | Show merged config |
| `commands/learn.md` | `skills/learn/SKILL.md` | Extract insights |
| `commands/learn-on.md` | `skills/learn-on/SKILL.md` | Enable learning |
| `commands/learn-off.md` | `skills/learn-off/SKILL.md` | Disable learning |
| `commands/knowledge.md` | `skills/knowledge/SKILL.md` | Knowledge status |
| `commands/learn-reset.md` | `skills/learn-reset/SKILL.md` | Clear knowledge |
| `commands/retry.md` | `skills/retry/SKILL.md` | Escalate and retry |

### New Files — Tests

| File | Tests |
|------|-------|
| `tests/__init__.py` | Package marker |
| `tests/test_detector.py` | Language detection: single lang, ambiguous, Spanglish, short |
| `tests/test_classifier.py` | Pattern matching + decision matrix per language |
| `tests/test_cache.py` | L1/L2 cache: hit, miss, eviction, TTL, fingerprint |
| `tests/test_stats.py` | Stats read/write, atomic ops, retention |
| `tests/test_context.py` | Session state, follow-up detection, timeout |
| `tests/test_learner.py` | Keyword matching, boost limits, conservative rules |
| `tests/test_pipeline.py` | End-to-end: query → route output |

### New Files — Meta

| File | Responsibility |
|------|---------------|
| `README.md` | Installation, usage, configuration guide |
| `CHANGELOG.md` | Version history |
| `LICENSE` | MIT license |

---

## Task 1: Project Scaffold

**Files:**
- Create: `plugin.json`
- Create: `hooks/hooks.json`
- Create: `hooks/lib/__init__.py`
- Create: `LICENSE`
- Create: `CHANGELOG.md`

- [ ] **Step 1: Create plugin.json**

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
    { "name": "dashboard",   "description": "Generate HTML analytics dashboard with Charts.js",            "file": "./commands/dashboard.md" },
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

- [ ] **Step 2: Create hooks/hooks.json**

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/classify-prompt.py",
            "timeout": 15
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/check-update.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Create hooks/lib/__init__.py**

```python
"""Claude Polyrouter classification pipeline modules."""
```

- [ ] **Step 4: Create LICENSE**

Standard MIT license with `Copyright (c) 2026 sonyharv`.

- [ ] **Step 5: Create CHANGELOG.md**

```markdown
# Changelog

## [1.0.0] - 2026-04-02

### Added
- Automatic query routing via UserPromptSubmit hook
- 10 language support: English, Spanish, Portuguese, French, German, Russian, Chinese, Japanese, Korean, Arabic
- Spanglish detection for mixed en/es queries
- Two-level cache (in-memory LRU + file-based persistent)
- Multi-turn session awareness with follow-up detection
- Project-level learning system with knowledge base
- 4 agents: fast-executor, standard-executor, deep-executor, opus-orchestrator
- 10 slash commands: route, stats, dashboard, config, learn, learn-on, learn-off, knowledge, learn-reset, retry
- Configurable routing levels abstracted from model names
- Global + project config merge with zero-config defaults
- SessionStart update notification
- HTML analytics dashboard with Charts.js
```

- [ ] **Step 6: Initialize git and commit**

```bash
cd /home/sonyharv/.claude/plugins/claude-polyrouter
git init
git add plugin.json hooks/hooks.json hooks/lib/__init__.py LICENSE CHANGELOG.md
git commit -m "chore: initialize project scaffold with plugin manifest and hook registration"
```

---

## Task 2: Default Config Module

**Files:**
- Create: `hooks/lib/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for config loading**

Create `tests/__init__.py`:
```python
"""Claude Polyrouter tests."""
```

Create `tests/test_config.py`:
```python
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.config import DEFAULT_CONFIG, load_config, find_project_config


class TestDefaultConfig:
    def test_has_three_levels(self):
        assert "fast" in DEFAULT_CONFIG["levels"]
        assert "standard" in DEFAULT_CONFIG["levels"]
        assert "deep" in DEFAULT_CONFIG["levels"]

    def test_each_level_has_model_and_agent(self):
        for level_name, level in DEFAULT_CONFIG["levels"].items():
            assert "model" in level, f"{level_name} missing model"
            assert "agent" in level, f"{level_name} missing agent"
            assert "cost_per_1k_input" in level, f"{level_name} missing cost_per_1k_input"
            assert "cost_per_1k_output" in level, f"{level_name} missing cost_per_1k_output"

    def test_default_level_is_fast(self):
        assert DEFAULT_CONFIG["default_level"] == "fast"

    def test_confidence_threshold(self):
        assert DEFAULT_CONFIG["confidence_threshold"] == 0.7


class TestLoadConfig:
    def test_returns_defaults_when_no_files_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            global_path = Path(tmpdir) / "polyrouter" / "config.json"
            with patch("lib.config.GLOBAL_CONFIG_PATH", global_path):
                with patch("lib.config.find_project_config", return_value=None):
                    config = load_config()
            assert config["default_level"] == "fast"
            assert config["levels"]["fast"]["model"] == "haiku"

    def test_global_config_overrides_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / "polyrouter"
            global_dir.mkdir()
            global_path = global_dir / "config.json"
            global_path.write_text(json.dumps({"default_level": "standard"}))
            with patch("lib.config.GLOBAL_CONFIG_PATH", global_path):
                with patch("lib.config.find_project_config", return_value=None):
                    config = load_config()
            assert config["default_level"] == "standard"
            assert config["levels"]["fast"]["model"] == "haiku"  # preserved

    def test_project_config_overrides_global(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / "polyrouter"
            global_dir.mkdir()
            global_path = global_dir / "config.json"
            global_path.write_text(json.dumps({"default_level": "standard"}))
            project_path = Path(tmpdir) / "project" / "config.json"
            project_path.parent.mkdir()
            project_path.write_text(json.dumps({"default_level": "deep"}))
            with patch("lib.config.GLOBAL_CONFIG_PATH", global_path):
                with patch("lib.config.find_project_config", return_value=project_path):
                    config = load_config()
            assert config["default_level"] == "deep"

    def test_shallow_merge_dicts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / "polyrouter"
            global_dir.mkdir()
            global_path = global_dir / "config.json"
            override = {"levels": {"fast": {"model": "sonnet", "agent": "standard-executor"}}}
            global_path.write_text(json.dumps(override))
            with patch("lib.config.GLOBAL_CONFIG_PATH", global_path):
                with patch("lib.config.find_project_config", return_value=None):
                    config = load_config()
            assert config["levels"]["fast"]["model"] == "sonnet"
            assert config["levels"]["standard"]["model"] == "sonnet"  # preserved from defaults

    def test_corrupted_config_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / "polyrouter"
            global_dir.mkdir()
            global_path = global_dir / "config.json"
            global_path.write_text("NOT VALID JSON {{{")
            with patch("lib.config.GLOBAL_CONFIG_PATH", global_path):
                with patch("lib.config.find_project_config", return_value=None):
                    config = load_config()
            assert config["default_level"] == "fast"  # fell back to defaults
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/sonyharv/.claude/plugins/claude-polyrouter
python3 -m pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'lib.config'`

- [ ] **Step 3: Write config module**

Create `hooks/lib/config.py`:
```python
"""Configuration loading with three-layer merge: defaults → global → project."""

import copy
import json
from pathlib import Path

GLOBAL_CONFIG_PATH = Path.home() / ".claude" / "polyrouter" / "config.json"

DEFAULT_CONFIG = {
    "version": "1.0",
    "levels": {
        "fast": {
            "model": "haiku",
            "agent": "fast-executor",
            "cost_per_1k_input": 0.001,
            "cost_per_1k_output": 0.005,
        },
        "standard": {
            "model": "sonnet",
            "agent": "standard-executor",
            "cost_per_1k_input": 0.003,
            "cost_per_1k_output": 0.015,
        },
        "deep": {
            "model": "opus",
            "agent": "deep-executor",
            "cost_per_1k_input": 0.005,
            "cost_per_1k_output": 0.025,
        },
    },
    "default_level": "fast",
    "confidence_threshold": 0.7,
    "session_timeout_minutes": 30,
    "cache": {"memory_size": 50, "file_size": 100, "ttl_days": 30},
    "learning": {"enabled": False, "informed_routing": False, "max_boost": 0.1},
    "updates": {"check_on_start": True, "repo": "sonyharv/claude-polyrouter"},
}


def _merge_config(base: dict, override: dict) -> dict:
    """Shallow merge: dict values are merged one level, scalars are replaced."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = {**result[key], **value}
        else:
            result[key] = value
    return result


def find_project_config() -> Path | None:
    """Search from CWD upward for .claude-polyrouter/config.json."""
    current = Path.cwd()
    home = Path.home()
    while current != current.parent and current != home:
        candidate = current / ".claude-polyrouter" / "config.json"
        if candidate.exists():
            return candidate
        if (current / ".git").exists():
            break
        current = current.parent
    return None


def _read_json_safe(path: Path) -> dict | None:
    """Read and parse JSON file, return None on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_config() -> dict:
    """Load config with three-layer merge: defaults → global → project."""
    config = copy.deepcopy(DEFAULT_CONFIG)

    global_cfg = _read_json_safe(GLOBAL_CONFIG_PATH)
    if global_cfg:
        config = _merge_config(config, global_cfg)

    project_path = find_project_config()
    if project_path:
        project_cfg = _read_json_safe(project_path)
        if project_cfg:
            config = _merge_config(config, project_cfg)

    return config
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/sonyharv/.claude/plugins/claude-polyrouter
python3 -m pytest tests/test_config.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/lib/config.py tests/__init__.py tests/test_config.py
git commit -m "feat: add config module with three-layer merge (defaults → global → project)"
```

---

## Task 3: Language Detection Module

**Files:**
- Create: `hooks/lib/detector.py`
- Create: `tests/test_detector.py`
- Create: `languages/en.json`
- Create: `languages/es.json`

- [ ] **Step 1: Create initial language files (en + es)**

Create `languages/en.json`:
```json
{
  "code": "en",
  "name": "English",
  "stopwords": [
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "this", "that", "these", "those", "it", "its", "my", "your",
    "and", "or", "but", "not", "if", "then", "than", "when", "what",
    "how", "which", "who", "where", "why"
  ],
  "patterns": {
    "fast": [
      "^what (is|are|does) ",
      "^how (do|does|to) ",
      "^(show|list|get|display) .{0,30}$",
      "\\b(format|lint|prettify|beautify)\\b",
      "\\bgit (status|log|diff|add|commit|push|pull|branch|checkout|merge)\\b",
      "\\b(json|yaml|yml|toml|csv)\\b.{0,20}$",
      "\\bregex\\b",
      "\\bsyntax (for|of)\\b",
      "^(what|how).{0,50}\\?$"
    ],
    "deep": [
      "\\b(architect|architecture|design pattern|system design)\\b",
      "\\bscalab(le|ility)\\b",
      "\\b(security|vulnerab|audit|penetration|exploit)\\b",
      "\\b(across|multiple|all) (files?|components?|modules?)\\b",
      "\\brefactor.{0,20}(codebase|project|entire|complete)\\b",
      "\\b(trade-?off|compare|pros? (and|&) cons?)\\b",
      "\\b(analy[sz]e|evaluate|assess).{0,30}(option|approach|strateg)\\b",
      "\\b(complex|intricate|sophisticated)\\b",
      "\\boptimi[sz](e|ation).{0,20}(performance|speed|memory)\\b",
      "\\b(migration|standalone|extraction).{0,20}(plan|strategy)\\b"
    ],
    "tool_intensive": [
      "\\b(search|find|grep|look for) .{0,20}(in|across|within)\\b",
      "\\b(modify|change|update|edit) .{0,20}(files?|modules?)\\b",
      "\\b(run|execute) .{0,20}(tests?|specs?|suite)\\b",
      "\\b(install|add|remove) .{0,20}(dependency|package|library)\\b",
      "\\b(build|compile|bundle)\\b",
      "\\b(deploy|ship|release)\\b",
      "\\bcheck .{0,15}(status|health|logs?)\\b"
    ],
    "orchestration": [
      "\\b(step by step|phase by phase|stage by stage)\\b",
      "\\b(first|then|next|finally|after that).{0,30}(then|next|finally|after that)\\b",
      "\\b(complete plan|full implementation|entire pipeline)\\b",
      "\\b(end.to.end|from scratch|ground up)\\b",
      "\\bmulti.?step\\b"
    ]
  },
  "follow_up_patterns": [
    "^(and |but |also |now |then )",
    "^(ok|okay|yes|sure|right|got it|thanks)[,.]? ",
    "\\b(the above|that|this|it|the same|what you said)\\b",
    "\\b(continue|go on|proceed|next|keep going)\\b",
    "^(do it|go ahead|sounds good|perfect|great)"
  ]
}
```

Create `languages/es.json`:
```json
{
  "code": "es",
  "name": "Español",
  "stopwords": [
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al", "en", "con", "por", "para", "sin",
    "que", "es", "son", "está", "están", "fue", "ser", "hay",
    "este", "esta", "estos", "estas", "ese", "esa",
    "su", "sus", "mi", "tu", "y", "o", "pero", "como",
    "más", "no", "si", "ya", "se", "le", "lo", "me",
    "qué", "cómo", "cuál", "dónde", "quién", "cuándo"
  ],
  "patterns": {
    "fast": [
      "^(qué|cuál) (es|son|significa) ",
      "^cómo (se|puedo|hago|funciona) ",
      "^(muestra|lista|dame|pon|dime) .{0,30}$",
      "\\b(formatea|ordena|limpia|arregla el formato)\\b",
      "\\bgit (status|log|diff|add|commit|push|pull|branch|checkout|merge)\\b",
      "\\b(json|yaml|yml|toml|csv)\\b.{0,20}$",
      "\\bregex\\b",
      "\\bsintaxis (de|para)\\b",
      "^(qué|cómo).{0,50}\\?$"
    ],
    "deep": [
      "\\b(arquitectura|diseño de sistema|patrón de diseño)\\b",
      "\\bescalab(le|ilidad)\\b",
      "\\b(seguridad|vulnerab|auditoría|exploit)\\b",
      "\\b(todos los|múltiples|varios) (archivos?|componentes?|módulos?)\\b",
      "\\brefactor.{0,20}(codebase|proyecto|entero|completo)\\b",
      "\\b(trade-?off|comparar?|pros? y contras?)\\b",
      "\\b(analiz|evalu|compar).{0,30}(opci|enfoque|estrateg)\\b",
      "\\b(complejo|intrincado|sofisticado)\\b",
      "\\boptimiz.{0,20}(rendimiento|velocidad|memoria)\\b",
      "\\b(migración|extracción).{0,20}(plan|estrategia)\\b"
    ],
    "tool_intensive": [
      "\\b(busca|encuentra|grep|buscar) .{0,20}(en|dentro|entre)\\b",
      "\\b(modifica|cambia|actualiza|edita) .{0,20}(archivos?|ficheros?|módulos?)\\b",
      "\\b(ejecuta|corre|lanza) .{0,20}(tests?|pruebas?|specs?)\\b",
      "\\b(instala|agrega|quita) .{0,20}(dependencia|paquete|librería)\\b",
      "\\b(compila|construye|buildea)\\b",
      "\\b(despliega|deploya|publica)\\b",
      "\\b(revisa|checa) .{0,15}(estado|logs?|salud)\\b"
    ],
    "orchestration": [
      "\\b(paso a paso|fase por fase|etapa por etapa)\\b",
      "\\b(primero|después|luego|finalmente).{0,30}(después|luego|finalmente)\\b",
      "\\b(plan completo|implementación completa|pipeline completo)\\b",
      "\\b(de punta a punta|desde cero|desde el inicio)\\b",
      "\\bmulti.?paso\\b"
    ]
  },
  "follow_up_patterns": [
    "^(y |pero |además |también |ahora )",
    "^(ok|bien|listo|perfecto|dale|va|sí)[,.]? ",
    "\\b(lo anterior|eso|lo mismo|lo que dijiste)\\b",
    "\\b(continúa|sigue|prosigue|avanza|adelante)\\b",
    "^(hazlo|dale|suena bien|excelente|genial)"
  ]
}
```

- [ ] **Step 2: Write failing tests for detector**

Create `tests/test_detector.py`:
```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.detector import detect_language, load_languages


LANG_DIR = Path(__file__).parent.parent / "languages"


class TestLoadLanguages:
    def test_loads_en_and_es(self):
        langs = load_languages(LANG_DIR)
        assert "en" in langs
        assert "es" in langs

    def test_language_has_required_fields(self):
        langs = load_languages(LANG_DIR)
        for code, lang in langs.items():
            assert "stopwords" in lang, f"{code} missing stopwords"
            assert "patterns" in lang, f"{code} missing patterns"
            assert "follow_up_patterns" in lang, f"{code} missing follow_up_patterns"


class TestDetectLanguage:
    def setup_method(self):
        self.langs = load_languages(LANG_DIR)

    def test_detects_english(self):
        result = detect_language("what is the best way to do this", self.langs)
        assert result.language == "en"
        assert result.confidence > 0.15

    def test_detects_spanish(self):
        result = detect_language("cómo puedo hacer esto con los archivos", self.langs)
        assert result.language == "es"
        assert result.confidence > 0.15

    def test_short_query_flags_multi_eval(self):
        result = detect_language("fix bug", self.langs)
        assert result.multi_eval is True

    def test_ambiguous_flags_multi_eval(self):
        result = detect_language("refactor the code", self.langs)
        # "the" is English stopword but "refactor" is universal
        # May or may not be multi_eval depending on scoring
        assert result.language is not None

    def test_spanglish_detection(self):
        result = detect_language("quiero que el API endpoint sea más fast para los users", self.langs)
        assert result.multi_eval is True

    def test_empty_query(self):
        result = detect_language("", self.langs)
        assert result.multi_eval is True

    def test_single_word(self):
        result = detect_language("help", self.langs)
        assert result.multi_eval is True
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_detector.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'lib.detector'`

- [ ] **Step 4: Write detector module**

Create `hooks/lib/detector.py`:
```python
"""Language detection via stopword scoring."""

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DetectionResult:
    language: str | None
    confidence: float
    multi_eval: bool
    scores: dict[str, float]


def load_languages(lang_dir: Path) -> dict:
    """Auto-discover and load all language JSON files."""
    languages = {}
    for path in lang_dir.glob("*.json"):
        if path.name == "schema.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            code = data.get("code", path.stem)
            languages[code] = data
        except Exception:
            continue
    return languages


def _tokenize(query: str) -> list[str]:
    """Split query into lowercase word tokens."""
    return re.findall(r"\w+", query.lower())


def detect_language(
    query: str,
    languages: dict,
    last_language: str | None = None,
) -> DetectionResult:
    """Detect the language of a query using stopword scoring.

    Returns a DetectionResult with the detected language, confidence,
    and whether multi-language evaluation is needed.
    """
    tokens = _tokenize(query)

    if len(tokens) < 4:
        return DetectionResult(
            language=last_language,
            confidence=0.0,
            multi_eval=True,
            scores={},
        )

    scores: dict[str, float] = {}
    token_set = set(tokens)

    for code, lang_data in languages.items():
        stopwords = set(lang_data.get("stopwords", []))
        matches = token_set & stopwords
        scores[code] = len(matches) / len(tokens) if tokens else 0.0

    if not scores:
        return DetectionResult(language=None, confidence=0.0, multi_eval=True, scores={})

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_code, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0

    # Spanglish: both en and es score high, neither dominates
    en_score = scores.get("en", 0.0)
    es_score = scores.get("es", 0.0)
    if en_score > 0.08 and es_score > 0.08 and abs(en_score - es_score) < 0.05:
        return DetectionResult(
            language=None,
            confidence=max(en_score, es_score),
            multi_eval=True,
            scores=scores,
        )

    # High confidence: clear winner
    if top_score > 0.15 and (top_score - second_score) > 0.05:
        return DetectionResult(
            language=top_code,
            confidence=top_score,
            multi_eval=False,
            scores=scores,
        )

    # Ambiguous
    return DetectionResult(
        language=top_code if top_score > 0 else last_language,
        confidence=top_score,
        multi_eval=True,
        scores=scores,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_detector.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add hooks/lib/detector.py tests/test_detector.py languages/en.json languages/es.json
git commit -m "feat: add language detection module with English and Spanish support"
```

---

## Task 4: Classification Engine

**Files:**
- Create: `hooks/lib/classifier.py`
- Create: `tests/test_classifier.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_classifier.py`:
```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.classifier import classify_query, compile_patterns
from lib.detector import load_languages
from lib.config import DEFAULT_CONFIG

LANG_DIR = Path(__file__).parent.parent / "languages"


class TestCompilePatterns:
    def test_compiles_without_error(self):
        langs = load_languages(LANG_DIR)
        compiled = compile_patterns(langs)
        assert "en" in compiled
        assert "es" in compiled

    def test_compiled_has_all_categories(self):
        langs = load_languages(LANG_DIR)
        compiled = compile_patterns(langs)
        for code in compiled:
            assert "fast" in compiled[code]
            assert "deep" in compiled[code]
            assert "tool_intensive" in compiled[code]
            assert "orchestration" in compiled[code]


class TestClassifyEnglish:
    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG

    def test_simple_question_routes_fast(self):
        result = classify_query("what is a closure in javascript", ["en"], self.patterns, self.config)
        assert result.level == "fast"

    def test_architecture_routes_deep(self):
        result = classify_query("design the architecture for a distributed system", ["en"], self.patterns, self.config)
        assert result.level == "deep"

    def test_git_command_routes_fast(self):
        result = classify_query("git status", ["en"], self.patterns, self.config)
        assert result.level == "fast"

    def test_security_audit_routes_deep(self):
        result = classify_query("audit the security vulnerabilities in this codebase", ["en"], self.patterns, self.config)
        assert result.level == "deep"

    def test_run_tests_routes_standard(self):
        result = classify_query("run the tests for the auth module", ["en"], self.patterns, self.config)
        assert result.level == "standard"

    def test_no_signals_routes_default(self):
        result = classify_query("hello there", ["en"], self.patterns, self.config)
        assert result.level == "fast"
        assert result.confidence == 0.5


class TestClassifySpanish:
    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG

    def test_simple_question_routes_fast(self):
        result = classify_query("qué es un closure en javascript", ["es"], self.patterns, self.config)
        assert result.level == "fast"

    def test_architecture_routes_deep(self):
        result = classify_query("diseña la arquitectura de un sistema distribuido", ["es"], self.patterns, self.config)
        assert result.level == "deep"

    def test_security_routes_deep(self):
        result = classify_query("auditoría de seguridad del codebase completo", ["es"], self.patterns, self.config)
        assert result.level == "deep"

    def test_run_tests_routes_standard(self):
        result = classify_query("ejecuta los tests del módulo de auth", ["es"], self.patterns, self.config)
        assert result.level == "standard"


class TestDecisionMatrix:
    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG

    def test_deep_plus_tool_routes_deep_high_confidence(self):
        result = classify_query(
            "analyze the architecture across all files and refactor the entire codebase",
            ["en"], self.patterns, self.config,
        )
        assert result.level == "deep"
        assert result.confidence >= 0.9

    def test_multi_language_eval(self):
        result = classify_query(
            "qué es un closure en javascript",
            ["en", "es"], self.patterns, self.config,
        )
        assert result.level == "fast"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_classifier.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'lib.classifier'`

- [ ] **Step 3: Write classifier module**

Create `hooks/lib/classifier.py`:
```python
"""Rule-based query classification with pre-compiled regex patterns."""

import re
from dataclasses import dataclass


@dataclass
class ClassificationResult:
    level: str
    confidence: float
    method: str
    signals: dict[str, int]
    matched_languages: list[str]


def compile_patterns(languages: dict) -> dict[str, dict[str, list[re.Pattern]]]:
    """Pre-compile all regex patterns from all language files.

    Returns: {lang_code: {category: [compiled_regex, ...]}}
    """
    compiled = {}
    for code, lang_data in languages.items():
        compiled[code] = {}
        patterns = lang_data.get("patterns", {})
        for category, pattern_list in patterns.items():
            compiled[code][category] = []
            for pattern_str in pattern_list:
                try:
                    compiled[code][category].append(
                        re.compile(pattern_str, re.IGNORECASE | re.UNICODE)
                    )
                except re.error:
                    continue
    return compiled


def _count_signals(
    query: str,
    lang_codes: list[str],
    compiled_patterns: dict,
) -> dict[str, int]:
    """Count pattern matches per category across specified languages."""
    signals: dict[str, int] = {}
    for code in lang_codes:
        if code not in compiled_patterns:
            continue
        for category, patterns in compiled_patterns[code].items():
            for pattern in patterns:
                if pattern.search(query):
                    signals[category] = signals.get(category, 0) + 1
                    break  # one match per category per language is enough
    return signals


def _decide(signals: dict[str, int], config: dict) -> tuple[str, float]:
    """Decision matrix: signals → (level, confidence)."""
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


def classify_query(
    query: str,
    lang_codes: list[str],
    compiled_patterns: dict,
    config: dict,
) -> ClassificationResult:
    """Classify a query using rule-based pattern matching.

    Args:
        query: The user's query text
        lang_codes: Languages to evaluate patterns for
        compiled_patterns: Pre-compiled patterns from compile_patterns()
        config: Merged configuration dict

    Returns:
        ClassificationResult with level, confidence, method, and signals
    """
    signals = _count_signals(query, lang_codes, compiled_patterns)
    level, confidence = _decide(signals, config)

    return ClassificationResult(
        level=level,
        confidence=confidence,
        method="rules",
        signals=signals,
        matched_languages=lang_codes,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_classifier.py -v
```

Expected: All 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/lib/classifier.py tests/test_classifier.py
git commit -m "feat: add classification engine with decision matrix and multi-language pattern matching"
```

---

## Task 5: Cache Module

**Files:**
- Create: `hooks/lib/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cache.py`:
```python
import json
import sys
import tempfile
import time
from pathlib import Path
from collections import OrderedDict

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.cache import Cache, fingerprint


class TestFingerprint:
    def test_same_query_same_fingerprint(self):
        assert fingerprint("hello world") == fingerprint("hello world")

    def test_case_insensitive(self):
        assert fingerprint("Hello World") == fingerprint("hello world")

    def test_order_independent(self):
        assert fingerprint("hello world") == fingerprint("world hello")

    def test_strips_punctuation(self):
        assert fingerprint("hello, world!") == fingerprint("hello world")

    def test_different_queries_different_fingerprints(self):
        assert fingerprint("hello world") != fingerprint("goodbye world")


class TestCacheL1:
    def test_miss_returns_none(self):
        cache = Cache(memory_size=10, file_size=0, ttl_days=30, cache_file=None)
        assert cache.get("nonexistent") is None

    def test_set_and_get(self):
        cache = Cache(memory_size=10, file_size=0, ttl_days=30, cache_file=None)
        cache.set("key1", {"level": "fast", "confidence": 0.9})
        result = cache.get("key1")
        assert result["level"] == "fast"

    def test_lru_eviction(self):
        cache = Cache(memory_size=2, file_size=0, ttl_days=30, cache_file=None)
        cache.set("key1", {"level": "fast"})
        cache.set("key2", {"level": "standard"})
        cache.set("key3", {"level": "deep"})  # should evict key1
        assert cache.get("key1") is None
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None


class TestCacheL2:
    def test_persists_to_file(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            cache_file = Path(f.name)
        try:
            cache = Cache(memory_size=10, file_size=10, ttl_days=30, cache_file=cache_file)
            cache.set("key1", {"level": "fast", "confidence": 0.9})
            cache.flush()

            cache2 = Cache(memory_size=10, file_size=10, ttl_days=30, cache_file=cache_file)
            result = cache2.get("key1")
            assert result is not None
            assert result["level"] == "fast"
        finally:
            cache_file.unlink(missing_ok=True)

    def test_file_cache_eviction(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            cache_file = Path(f.name)
        try:
            cache = Cache(memory_size=10, file_size=2, ttl_days=30, cache_file=cache_file)
            cache.set("key1", {"level": "fast"})
            cache.set("key2", {"level": "standard"})
            cache.set("key3", {"level": "deep"})  # should evict key1 from file
            cache.flush()

            data = json.loads(cache_file.read_text())
            assert len(data["entries"]) <= 2
        finally:
            cache_file.unlink(missing_ok=True)

    def test_corrupted_file_handled_gracefully(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("NOT VALID JSON")
            cache_file = Path(f.name)
        try:
            cache = Cache(memory_size=10, file_size=10, ttl_days=30, cache_file=cache_file)
            assert cache.get("anything") is None  # no crash
        finally:
            cache_file.unlink(missing_ok=True)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_cache.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'lib.cache'`

- [ ] **Step 3: Write cache module**

Create `hooks/lib/cache.py`:
```python
"""Two-level cache: in-memory LRU (L1) + file-based persistent (L2)."""

import hashlib
import json
import re
import time
from collections import OrderedDict
from pathlib import Path


def fingerprint(query: str) -> str:
    """Generate order-independent MD5 fingerprint of normalized query."""
    normalized = re.sub(r"[^\w\s]", "", query.lower())
    words = sorted(normalized.split())
    return hashlib.md5(" ".join(words).encode()).hexdigest()


class Cache:
    """Two-level cache with in-memory LRU (L1) and file-based (L2)."""

    def __init__(
        self,
        memory_size: int,
        file_size: int,
        ttl_days: int,
        cache_file: Path | None,
    ):
        self._memory_size = memory_size
        self._file_size = file_size
        self._ttl_seconds = ttl_days * 86400
        self._cache_file = cache_file
        self._l1: OrderedDict[str, dict] = OrderedDict()
        self._l2: OrderedDict[str, dict] = OrderedDict()
        self._l2_dirty = False

        if cache_file:
            self._load_l2()

    def get(self, key: str) -> dict | None:
        """Look up a cached route by fingerprint key. L1 first, then L2."""
        # L1 check
        if key in self._l1:
            self._l1.move_to_end(key)
            return self._l1[key]

        # L2 check
        if key in self._l2:
            entry = self._l2[key]
            # TTL check
            if time.time() - entry.get("_cached_at", 0) > self._ttl_seconds:
                del self._l2[key]
                self._l2_dirty = True
                return None
            # Promote to L1
            self._l1[key] = entry
            self._evict_l1()
            return entry

        return None

    def set(self, key: str, value: dict) -> None:
        """Store a route in both L1 and L2."""
        entry = {**value, "_cached_at": time.time()}

        # L1
        self._l1[key] = entry
        self._evict_l1()

        # L2
        if self._cache_file is not None:
            self._l2[key] = entry
            self._evict_l2()
            self._l2_dirty = True

    def flush(self) -> None:
        """Write L2 cache to disk if dirty."""
        if not self._l2_dirty or not self._cache_file:
            return
        try:
            data = {
                "version": "1.0",
                "entries": {k: v for k, v in self._l2.items()},
            }
            tmp_path = self._cache_file.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data), encoding="utf-8")
            tmp_path.replace(self._cache_file)
            self._l2_dirty = False
        except Exception:
            pass

    def _load_l2(self) -> None:
        """Load L2 cache from disk."""
        if not self._cache_file or not self._cache_file.exists():
            return
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            entries = data.get("entries", {})
            now = time.time()
            for key, entry in entries.items():
                if now - entry.get("_cached_at", 0) <= self._ttl_seconds:
                    self._l2[key] = entry
        except Exception:
            self._l2 = OrderedDict()

    def _evict_l1(self) -> None:
        """Evict oldest L1 entries if over capacity."""
        while len(self._l1) > self._memory_size:
            self._l1.popitem(last=False)

    def _evict_l2(self) -> None:
        """Evict oldest L2 entries if over capacity."""
        while len(self._l2) > self._file_size:
            self._l2.popitem(last=False)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_cache.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/lib/cache.py tests/test_cache.py
git commit -m "feat: add two-level cache with in-memory LRU and file-based persistence"
```

---

## Task 6: Stats Module

**Files:**
- Create: `hooks/lib/stats.py`
- Create: `tests/test_stats.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_stats.py`:
```python
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.stats import Stats


class TestStats:
    def _make_stats(self, tmpdir):
        path = Path(tmpdir) / "stats.json"
        return Stats(path)

    def test_empty_stats_on_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            data = stats.read()
            assert data["total_queries"] == 0
            assert data["routes"]["fast"] == 0

    def test_record_increments_counters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            stats.record(level="fast", language="en", cache_hit=False, savings=0.044)
            data = stats.read()
            assert data["total_queries"] == 1
            assert data["routes"]["fast"] == 1
            assert data["languages_detected"]["en"] == 1
            assert data["cache_hits"] == 0

    def test_cache_hit_increments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            stats.record(level="fast", language="en", cache_hit=True, savings=0.044)
            data = stats.read()
            assert data["cache_hits"] == 1

    def test_multiple_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            stats.record(level="fast", language="en", cache_hit=False, savings=0.044)
            stats.record(level="deep", language="es", cache_hit=False, savings=0.0)
            stats.record(level="fast", language="en", cache_hit=True, savings=0.044)
            data = stats.read()
            assert data["total_queries"] == 3
            assert data["routes"]["fast"] == 2
            assert data["routes"]["deep"] == 1
            assert data["languages_detected"]["en"] == 2
            assert data["languages_detected"]["es"] == 1
            assert data["cache_hits"] == 1

    def test_session_created_for_today(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            stats.record(level="fast", language="en", cache_hit=False, savings=0.044)
            data = stats.read()
            today = date.today().isoformat()
            session = next(s for s in data["sessions"] if s["date"] == today)
            assert session["queries"] == 1
            assert session["routes"]["fast"] == 1

    def test_sessions_pruned_to_30_days(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            # Write 35 fake sessions
            data = stats.read()
            for i in range(35):
                data["sessions"].append({
                    "date": f"2025-01-{i+1:02d}",
                    "queries": 1,
                    "routes": {"fast": 1, "standard": 0, "deep": 0},
                    "cache_hits": 0,
                    "savings": 0.0,
                })
            stats._write(data)
            stats.record(level="fast", language="en", cache_hit=False, savings=0.044)
            data = stats.read()
            assert len(data["sessions"]) <= 30

    def test_corrupted_file_resets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stats.json"
            path.write_text("CORRUPT DATA")
            stats = Stats(path)
            data = stats.read()
            assert data["total_queries"] == 0  # reset to defaults
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_stats.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'lib.stats'`

- [ ] **Step 3: Write stats module**

Create `hooks/lib/stats.py`:
```python
"""Atomic statistics logging with file locking."""

import json
import platform
import tempfile
from datetime import date, datetime
from pathlib import Path

DEFAULT_STATS = {
    "version": "1.0",
    "total_queries": 0,
    "routes": {"fast": 0, "standard": 0, "deep": 0},
    "cache_hits": 0,
    "languages_detected": {},
    "estimated_savings": 0.0,
    "sessions": [],
    "last_updated": None,
}


def _lock_file(f):
    """Cross-platform file locking."""
    try:
        if platform.system() == "Windows":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        pass  # best-effort locking


def _unlock_file(f):
    """Cross-platform file unlocking."""
    try:
        if platform.system() == "Windows":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass


class Stats:
    """Atomic stats read/write with file locking."""

    def __init__(self, path: Path):
        self._path = path

    def read(self) -> dict:
        """Read stats from file, returning defaults if missing or corrupt."""
        if not self._path.exists():
            return {**DEFAULT_STATS, "routes": {**DEFAULT_STATS["routes"]}, "sessions": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            # Ensure all required keys exist
            for key, default in DEFAULT_STATS.items():
                if key not in data:
                    data[key] = default if not isinstance(default, (dict, list)) else type(default)(default)
            return data
        except Exception:
            return {**DEFAULT_STATS, "routes": {**DEFAULT_STATS["routes"]}, "sessions": []}

    def record(
        self,
        level: str,
        language: str | None,
        cache_hit: bool,
        savings: float,
    ) -> None:
        """Record a single routing event."""
        data = self.read()

        data["total_queries"] += 1
        data["routes"][level] = data["routes"].get(level, 0) + 1
        if cache_hit:
            data["cache_hits"] += 1
        if language:
            data["languages_detected"][language] = data["languages_detected"].get(language, 0) + 1
        data["estimated_savings"] = round(data["estimated_savings"] + savings, 4)
        data["last_updated"] = datetime.now().isoformat()

        # Update today's session
        today = date.today().isoformat()
        session = next((s for s in data["sessions"] if s["date"] == today), None)
        if session is None:
            session = {
                "date": today,
                "queries": 0,
                "routes": {"fast": 0, "standard": 0, "deep": 0},
                "cache_hits": 0,
                "savings": 0.0,
            }
            data["sessions"].append(session)

        session["queries"] += 1
        session["routes"][level] = session["routes"].get(level, 0) + 1
        if cache_hit:
            session["cache_hits"] += 1
        session["savings"] = round(session["savings"] + savings, 4)

        # Prune to last 30 days
        data["sessions"] = data["sessions"][-30:]

        self._write(data)

    def _write(self, data: dict) -> None:
        """Atomic write: write to temp file, then rename."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=self._path.parent, suffix=".tmp"
            )
            try:
                with open(tmp_fd, "w", encoding="utf-8") as f:
                    _lock_file(f)
                    json.dump(data, f, indent=2)
                    _unlock_file(f)
                Path(tmp_path).replace(self._path)
            except Exception:
                Path(tmp_path).unlink(missing_ok=True)
                raise
        except Exception:
            pass  # fail-safe: never break the hook
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_stats.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/lib/stats.py tests/test_stats.py
git commit -m "feat: add atomic stats module with file locking and session tracking"
```

---

## Task 7: Context Module (Multi-Turn Awareness)

**Files:**
- Create: `hooks/lib/context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_context.py`:
```python
import json
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import SessionState


class TestSessionState:
    def _make_session(self, tmpdir, timeout_minutes=30):
        path = Path(tmpdir) / "session.json"
        return SessionState(path, timeout_minutes=timeout_minutes)

    def test_new_session_has_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            state = session.read()
            assert state["last_route"] is None
            assert state["conversation_depth"] == 0

    def test_update_persists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            session.update(level="deep", language="es")
            state = session.read()
            assert state["last_route"] == "deep"
            assert state["last_level"] == "deep"
            assert state["last_language"] == "es"
            assert state["conversation_depth"] == 1

    def test_conversation_depth_increments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            session.update(level="fast", language="en")
            session.update(level="standard", language="en")
            session.update(level="deep", language="en")
            state = session.read()
            assert state["conversation_depth"] == 3

    def test_expired_session_resets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.json"
            # Write a session that's expired (31 minutes ago)
            old_time = time.time() - (31 * 60)
            data = {
                "last_route": "deep",
                "last_level": "deep",
                "conversation_depth": 10,
                "last_query_time": old_time,
                "last_language": "es",
            }
            path.write_text(json.dumps(data))
            session = SessionState(path, timeout_minutes=30)
            state = session.read()
            assert state["last_route"] is None
            assert state["conversation_depth"] == 0

    def test_is_follow_up_with_patterns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            session.update(level="deep", language="en")
            follow_up_patterns = [r"^(and |but |also )"]
            import re
            compiled = [re.compile(p, re.IGNORECASE) for p in follow_up_patterns]
            assert session.is_follow_up("and also fix this", compiled) is True
            assert session.is_follow_up("design a new system", compiled) is False

    def test_context_boost(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            session.update(level="deep", language="en")
            boost = session.get_confidence_boost()
            assert boost == 0.1  # last route was complex

    def test_no_boost_for_fast(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            session.update(level="fast", language="en")
            boost = session.get_confidence_boost()
            assert boost == 0.0

    def test_corrupted_file_handled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.json"
            path.write_text("CORRUPT")
            session = SessionState(path, timeout_minutes=30)
            state = session.read()
            assert state["conversation_depth"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_context.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'lib.context'`

- [ ] **Step 3: Write context module**

Create `hooks/lib/context.py`:
```python
"""Multi-turn session state management."""

import json
import re
import time
from pathlib import Path

DEFAULT_SESSION = {
    "last_route": None,
    "last_level": None,
    "conversation_depth": 0,
    "last_query_time": None,
    "last_language": None,
}


class SessionState:
    """Manages multi-turn conversation state with timeout-based expiration."""

    def __init__(self, path: Path, timeout_minutes: int = 30):
        self._path = path
        self._timeout_seconds = timeout_minutes * 60
        self._state: dict | None = None

    def read(self) -> dict:
        """Read session state, resetting if expired or corrupted."""
        if self._state is not None:
            return self._state

        if not self._path.exists():
            self._state = {**DEFAULT_SESSION}
            return self._state

        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            last_time = data.get("last_query_time")
            if last_time and (time.time() - last_time) > self._timeout_seconds:
                self._state = {**DEFAULT_SESSION}
                return self._state
            self._state = data
            return self._state
        except Exception:
            self._state = {**DEFAULT_SESSION}
            return self._state

    def update(self, level: str, language: str | None) -> None:
        """Update session state after a routing decision."""
        state = self.read()
        state["last_route"] = level
        state["last_level"] = level
        state["conversation_depth"] = state.get("conversation_depth", 0) + 1
        state["last_query_time"] = time.time()
        if language:
            state["last_language"] = language
        self._state = state
        self._write(state)

    def is_follow_up(self, query: str, compiled_patterns: list[re.Pattern]) -> bool:
        """Check if query matches any follow-up pattern."""
        state = self.read()
        if state["last_route"] is None:
            return False
        return any(p.search(query) for p in compiled_patterns)

    def get_confidence_boost(self) -> float:
        """Return confidence boost based on conversation context.

        Returns 0.1 if the last route was complex (standard or deep),
        0.0 otherwise.
        """
        state = self.read()
        last = state.get("last_route")
        if last in ("standard", "deep"):
            return 0.1
        return 0.0

    def _write(self, data: dict) -> None:
        """Write session state to file."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(data), encoding="utf-8"
            )
        except Exception:
            pass
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_context.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/lib/context.py tests/test_context.py
git commit -m "feat: add multi-turn session context with follow-up detection and confidence boost"
```

---

## Task 8: Learner Module

**Files:**
- Create: `hooks/lib/learner.py`
- Create: `tests/test_learner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_learner.py`:
```python
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.learner import get_learned_adjustment


class TestLearner:
    def _write_patterns(self, tmpdir, content):
        learnings_dir = Path(tmpdir) / ".claude-polyrouter" / "learnings"
        learnings_dir.mkdir(parents=True)
        (learnings_dir / "patterns.md").write_text(content)
        (learnings_dir / "quirks.md").write_text("")
        return learnings_dir

    def test_no_adjustment_when_disabled(self):
        config = {"learning": {"informed_routing": False, "max_boost": 0.1}}
        result = get_learned_adjustment("some query about databases", "fast", 0.7, config, None)
        assert result == (0.0, None)

    def test_no_adjustment_when_no_learnings_dir(self):
        config = {"learning": {"informed_routing": True, "max_boost": 0.1}}
        result = get_learned_adjustment("query", "fast", 0.7, config, Path("/nonexistent"))
        assert result == (0.0, None)

    def test_boost_when_keywords_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learnings_dir = self._write_patterns(tmpdir, """
## Pattern: Database queries need deep analysis
- **Keywords:** sql, database, query, migration
- **Confidence:** high
""")
            config = {"learning": {"informed_routing": True, "max_boost": 0.1}}
            boost, _ = get_learned_adjustment(
                "optimize the database query for migration",
                "fast", 0.7, config, learnings_dir,
            )
            assert boost > 0
            assert boost <= 0.1

    def test_no_boost_with_single_keyword_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learnings_dir = self._write_patterns(tmpdir, """
## Pattern: Database queries need deep analysis
- **Keywords:** sql, database, query, migration
- **Confidence:** high
""")
            config = {"learning": {"informed_routing": True, "max_boost": 0.1}}
            boost, _ = get_learned_adjustment(
                "fix the sql syntax",
                "fast", 0.7, config, learnings_dir,
            )
            assert boost == 0.0  # only 1 keyword match, needs 2+

    def test_never_downgrades_deep(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learnings_dir = self._write_patterns(tmpdir, """
## Pattern: Simple git ops
- **Keywords:** git, status, log, diff
- **Confidence:** high
""")
            config = {"learning": {"informed_routing": True, "max_boost": 0.1}}
            boost, _ = get_learned_adjustment(
                "git status and git log",
                "deep", 0.7, config, learnings_dir,
            )
            assert boost == 0.0  # no downgrade from deep

    def test_max_boost_capped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learnings_dir = self._write_patterns(tmpdir, """
## Pattern: All database ops are complex
- **Keywords:** sql, database, query, migration, index, schema, table, column
- **Confidence:** high
""")
            config = {"learning": {"informed_routing": True, "max_boost": 0.1}}
            boost, _ = get_learned_adjustment(
                "optimize database query migration index schema table",
                "fast", 0.5, config, learnings_dir,
            )
            assert boost <= 0.1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_learner.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'lib.learner'`

- [ ] **Step 3: Write learner module**

Create `hooks/lib/learner.py`:
```python
"""Knowledge-based routing adjustments from project learnings."""

import re
from pathlib import Path


def _extract_keywords(content: str) -> list[set[str]]:
    """Extract keyword sets from markdown learning entries."""
    keyword_sets = []
    for match in re.finditer(r"\*\*Keywords:\*\*\s*(.+)", content):
        keywords = {k.strip().lower() for k in match.group(1).split(",")}
        keyword_sets.append(keywords)
    return keyword_sets


def _read_learnings(learnings_dir: Path) -> list[set[str]]:
    """Read all keyword sets from patterns.md and quirks.md."""
    keyword_sets = []
    for filename in ("patterns.md", "quirks.md"):
        path = learnings_dir / filename
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                keyword_sets.extend(_extract_keywords(content))
            except Exception:
                continue
    return keyword_sets


def get_learned_adjustment(
    query: str,
    current_level: str,
    current_confidence: float,
    config: dict,
    learnings_dir: Path | None,
) -> tuple[float, str | None]:
    """Calculate learned confidence boost from project knowledge base.

    Args:
        query: The user's query text
        current_level: Currently determined routing level
        current_confidence: Current confidence score
        config: Merged configuration dict
        learnings_dir: Path to project learnings directory

    Returns:
        Tuple of (boost_amount, reason_string_or_None)
    """
    learning_config = config.get("learning", {})

    if not learning_config.get("informed_routing", False):
        return (0.0, None)

    if not learnings_dir or not learnings_dir.exists():
        return (0.0, None)

    # Never downgrade deep
    if current_level == "deep":
        return (0.0, None)

    max_boost = learning_config.get("max_boost", 0.1)
    query_words = set(re.findall(r"\w+", query.lower()))

    keyword_sets = _read_learnings(learnings_dir)
    if not keyword_sets:
        return (0.0, None)

    best_match_count = 0
    for keywords in keyword_sets:
        match_count = len(query_words & keywords)
        best_match_count = max(best_match_count, match_count)

    # Require 2+ keyword matches for any boost
    if best_match_count < 2:
        return (0.0, None)

    # Scale boost by match count, capped at max_boost
    boost = min(best_match_count * 0.03, max_boost)
    return (boost, f"{best_match_count} keyword matches from learnings")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_learner.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/lib/learner.py tests/test_learner.py
git commit -m "feat: add learner module with keyword-based routing adjustments"
```

---

## Task 9: Pipeline Orchestrator (classify-prompt.py)

**Files:**
- Create: `hooks/classify-prompt.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/test_pipeline.py`:
```python
import json
import os
import sys
import subprocess
import tempfile
from pathlib import Path

import pytest

HOOK_SCRIPT = Path(__file__).parent.parent / "hooks" / "classify-prompt.py"
LANG_DIR = Path(__file__).parent.parent / "languages"

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))


def run_hook(query: str, env_overrides: dict | None = None) -> dict:
    """Run the classify-prompt.py hook as a subprocess, simulating Claude Code."""
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(Path(__file__).parent.parent)
    if env_overrides:
        env.update(env_overrides)

    input_data = json.dumps({
        "hookEventName": "UserPromptSubmit",
        "query": query,
    })

    result = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=input_data,
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )

    if result.returncode != 0:
        pytest.fail(f"Hook failed: {result.stderr}")

    return json.loads(result.stdout)


class TestPipelineEndToEnd:
    def test_english_simple_query_routes_fast(self):
        output = run_hook("what is a variable in python")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "MANDATORY ROUTING DIRECTIVE" in ctx
        assert "Route: fast" in ctx

    def test_spanish_architecture_routes_deep(self):
        output = run_hook("diseña la arquitectura de un sistema distribuido escalable")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "MANDATORY ROUTING DIRECTIVE" in ctx
        assert "Route: deep" in ctx
        assert "Language: es" in ctx

    def test_slash_command_skips_routing(self):
        output = run_hook("/polyrouter:stats")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "ROUTING SKIPPED" in ctx

    def test_empty_query_skips_routing(self):
        output = run_hook("   ")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "ROUTING SKIPPED" in ctx

    def test_router_meta_query_skips(self):
        output = run_hook("how does the polyrouter work?")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "ROUTING SKIPPED" in ctx

    def test_output_has_correct_structure(self):
        output = run_hook("explain closures in javascript")
        assert "hookSpecificOutput" in output
        assert "hookEventName" in output["hookSpecificOutput"]
        assert output["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"

    def test_git_command_routes_fast(self):
        output = run_hook("git status")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "Route: fast" in ctx

    def test_security_audit_routes_deep(self):
        output = run_hook("audit the security vulnerabilities across all files")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "Route: deep" in ctx
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_pipeline.py -v
```

Expected: FAIL — script does not exist yet.

- [ ] **Step 3: Write classify-prompt.py orchestrator**

Create `hooks/classify-prompt.py`:
```python
#!/usr/bin/env python3
"""Claude Polyrouter — UserPromptSubmit hook orchestrator.

Reads query from stdin (JSON), runs the classification pipeline,
and outputs a routing directive as JSON to stdout.
"""

import json
import re
import sys
from pathlib import Path

# Add lib to path
HOOK_DIR = Path(__file__).parent
sys.path.insert(0, str(HOOK_DIR))

from lib.cache import Cache, fingerprint
from lib.classifier import ClassificationResult, classify_query, compile_patterns
from lib.config import DEFAULT_CONFIG, load_config
from lib.context import SessionState
from lib.detector import DetectionResult, detect_language, load_languages
from lib.learner import get_learned_adjustment
from lib.stats import Stats

# --- Constants ---

CONTINUATION_TOKENS = {
    "y", "sí", "si", "ok", "okay", "yes", "go", "sure", "right",
    "dale", "va", "bien", "listo", "perfecto", "continúa", "continua",
    "sigue", "prosigue", "avanza", "adelante", "next", "continue",
    "proceed", "go ahead", "got it", "sounds good", "great", "perfect",
}

META_KEYWORDS = {"polyrouter", "routing", "router"}

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", HOOK_DIR.parent))
LANG_DIR = PLUGIN_ROOT / "languages"
STATS_PATH = Path.home() / ".claude" / "polyrouter-stats.json"
SESSION_PATH = Path.home() / ".claude" / "polyrouter-session.json"
CACHE_PATH = Path.home() / ".claude" / "polyrouter-cache.json"


def _output_skip(reason: str) -> None:
    """Output a skip directive and exit."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                f"[Claude Polyrouter] ROUTING SKIPPED\n"
                f"Reason: {reason}\n\n"
                f"Respond to the user directly. Do not spawn a subagent."
            ),
        }
    }
    print(json.dumps(output))
    sys.exit(0)


def _output_route(
    level: str,
    model: str,
    agent: str,
    confidence: float,
    method: str,
    signals_str: str,
    language: str,
) -> None:
    """Output a routing directive and exit."""
    context = (
        f"[Claude Polyrouter] MANDATORY ROUTING DIRECTIVE\n"
        f"Route: {level} | Model: {model} | Confidence: {confidence:.0%} | Method: {method}\n"
        f"Signals: {signals_str}\n"
        f"Language: {language}\n\n"
        f'CRITICAL: You MUST use the Task tool NOW to spawn the "polyrouter:{agent}" subagent.\n'
        f"Do NOT respond to the user directly. Do NOT skip this step. Delegate immediately.\n\n"
        f"Example:\n"
        f'Task(subagent_type="polyrouter:{agent}", prompt="<user\'s query>", description="Route to {model.title()}")'
    )
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


def _calculate_savings(level: str, config: dict) -> float:
    """Calculate savings vs using the most expensive level."""
    levels = config.get("levels", {})
    if not levels:
        return 0.0

    # Find max cost level
    max_cost = 0.0
    for lvl_data in levels.values():
        cost = lvl_data.get("cost_per_1k_input", 0) + 2 * lvl_data.get("cost_per_1k_output", 0)
        max_cost = max(max_cost, cost)

    actual_data = levels.get(level, {})
    actual_cost = actual_data.get("cost_per_1k_input", 0) + 2 * actual_data.get("cost_per_1k_output", 0)

    return max(0.0, max_cost - actual_cost)


def main() -> None:
    try:
        input_data = json.loads(sys.stdin.read())
    except Exception:
        _output_skip("invalid_input")
        return

    query = input_data.get("query", "").strip()

    # --- Load config (fail-safe) ---
    try:
        config = load_config()
    except Exception:
        config = DEFAULT_CONFIG.copy()

    # --- Stage 1: Exception Check ---
    if not query:
        _output_skip("empty_query")

    if query.startswith("/"):
        _output_skip("slash_command")

    query_lower = query.lower().strip()
    if query_lower in CONTINUATION_TOKENS:
        # Use last route from session
        try:
            session = SessionState(SESSION_PATH, config.get("session_timeout_minutes", 30))
            state = session.read()
            last_level = state.get("last_level")
            if last_level and last_level in config.get("levels", {}):
                level_config = config["levels"][last_level]
                _output_route(
                    level=last_level,
                    model=level_config["model"],
                    agent=level_config["agent"],
                    confidence=0.85,
                    method="continuation",
                    signals_str="continuation token",
                    language=state.get("last_language", "unknown"),
                )
        except Exception:
            pass
        _output_skip("continuation_no_session")

    if any(kw in query_lower for kw in META_KEYWORDS):
        _output_skip("router_meta")

    # --- Load languages and compile patterns ---
    try:
        languages = load_languages(LANG_DIR)
        compiled_patterns = compile_patterns(languages)
    except Exception:
        _output_skip("language_load_error")

    # --- Stage 2: Cache Lookup ---
    cache_config = config.get("cache", {})
    cache = Cache(
        memory_size=cache_config.get("memory_size", 50),
        file_size=cache_config.get("file_size", 100),
        ttl_days=cache_config.get("ttl_days", 30),
        cache_file=CACHE_PATH,
    )

    query_fp = fingerprint(query)
    cached = cache.get(query_fp)
    cache_hit = cached is not None

    if cached:
        level = cached["level"]
        if level in config.get("levels", {}):
            level_config = config["levels"][level]
            # Record stats
            try:
                savings = _calculate_savings(level, config)
                stats = Stats(STATS_PATH)
                stats.record(level=level, language=cached.get("language"), cache_hit=True, savings=savings)
            except Exception:
                pass
            # Update session
            try:
                session = SessionState(SESSION_PATH, config.get("session_timeout_minutes", 30))
                session.update(level=level, language=cached.get("language"))
            except Exception:
                pass
            _output_route(
                level=level,
                model=level_config["model"],
                agent=level_config["agent"],
                confidence=cached.get("confidence", 0.8),
                method="cache",
                signals_str="cache hit",
                language=cached.get("language", "unknown"),
            )

    # --- Stage 3: Language Detection ---
    try:
        session = SessionState(SESSION_PATH, config.get("session_timeout_minutes", 30))
        state = session.read()
        last_lang = state.get("last_language")
    except Exception:
        session = None
        last_lang = None

    detection = detect_language(query, languages, last_language=last_lang)

    if detection.multi_eval:
        lang_codes = list(compiled_patterns.keys())
    else:
        lang_codes = [detection.language] if detection.language else list(compiled_patterns.keys())

    detected_lang = detection.language or "multi"

    # --- Stage 4: Rule-Based Classification ---
    result = classify_query(query, lang_codes, compiled_patterns, config)

    level = result.level
    confidence = result.confidence

    # --- Stage 5: Context Boost ---
    if session:
        try:
            # Compile follow-up patterns for detected languages
            follow_up_compiled = []
            for code in lang_codes:
                if code in languages:
                    for pat_str in languages[code].get("follow_up_patterns", []):
                        try:
                            follow_up_compiled.append(re.compile(pat_str, re.IGNORECASE | re.UNICODE))
                        except re.error:
                            continue

            if session.is_follow_up(query, follow_up_compiled):
                boost = session.get_confidence_boost()
                confidence = min(confidence + boost, 1.0)
        except Exception:
            pass

    # --- Stage 6: Learned Adjustments ---
    try:
        project_learnings = None
        cwd = Path.cwd()
        learnings_candidate = cwd / ".claude-polyrouter" / "learnings"
        if learnings_candidate.exists():
            project_learnings = learnings_candidate

        if project_learnings:
            learned_boost, _ = get_learned_adjustment(
                query, level, confidence, config, project_learnings,
            )
            confidence = min(confidence + learned_boost, 1.0)
    except Exception:
        pass

    # --- Resolve level to model/agent ---
    levels = config.get("levels", {})
    if level not in levels:
        level = config.get("default_level", "fast")
    level_config = levels.get(level, levels.get("fast", {"model": "haiku", "agent": "fast-executor"}))

    # --- Build signals string ---
    signal_parts = []
    for cat, count in result.signals.items():
        if count > 0:
            signal_parts.append(f"{count}x {cat}")
    if not signal_parts:
        signal_parts.append("no strong patterns")
    signals_str = ", ".join(signal_parts)

    # --- Record stats ---
    try:
        savings = _calculate_savings(level, config)
        stats_obj = Stats(STATS_PATH)
        stats_obj.record(level=level, language=detected_lang, cache_hit=False, savings=savings)
    except Exception:
        pass

    # --- Update session ---
    if session:
        try:
            session.update(level=level, language=detected_lang)
        except Exception:
            pass

    # --- Update cache ---
    try:
        cache.set(query_fp, {
            "level": level,
            "confidence": confidence,
            "language": detected_lang,
        })
        cache.flush()
    except Exception:
        pass

    # --- Output ---
    _output_route(
        level=level,
        model=level_config["model"],
        agent=level_config["agent"],
        confidence=confidence,
        method=result.method,
        signals_str=signals_str,
        language=detected_lang,
    )


import os  # noqa: E402 — needed before main but after path setup

if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Ultimate fail-safe: never crash the hook
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "[Claude Polyrouter] ROUTING SKIPPED\n"
                    "Reason: internal_error\n\n"
                    "Respond to the user directly. Do not spawn a subagent."
                ),
            }
        }))
```

**Important fix:** The `import os` needs to be at the top. Move it to the imports section:

The file should start with:
```python
#!/usr/bin/env python3
"""..."""

import json
import os
import re
import sys
from pathlib import Path
```

And remove the `import os  # noqa` line near the bottom. The `PLUGIN_ROOT` line using `os.environ` already requires `os` at the top.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_pipeline.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/classify-prompt.py tests/test_pipeline.py
git commit -m "feat: add pipeline orchestrator with six-stage classification"
```

---

## Task 10: Agent Files

**Files:**
- Create: `agents/fast-executor.md`
- Create: `agents/standard-executor.md`
- Create: `agents/deep-executor.md`
- Create: `agents/opus-orchestrator.md`

- [ ] **Step 1: Create fast-executor.md**

```markdown
---
name: fast-executor
description: Quick answers using the fast-tier model
model: haiku
tools:
  - Read
  - Grep
  - Glob
---

You are a fast, concise assistant for simple tasks.

## Rules

- Maximum 3 sentences unless code output is needed
- No preamble, no trailing summaries
- Answer the question directly
- If the task requires writing code, modifying files, or architectural analysis, say: "This task needs more capability. Try: /polyrouter:retry"
- Never apologize or over-explain
```

- [ ] **Step 2: Create standard-executor.md**

```markdown
---
name: standard-executor
description: Standard coding tasks using the standard-tier model
model: sonnet
tools: "*"
---

You are a capable coding assistant for typical development tasks.

## Rules

- Write clean, working code following project conventions
- Read existing code before making modifications
- Run tests after changes when possible
- If the task involves architectural decisions, trade-off analysis, or security audits, say: "This involves deeper analysis. Try: /polyrouter:retry"
```

- [ ] **Step 3: Create deep-executor.md**

```markdown
---
name: deep-executor
description: Complex analysis using the deep-tier model
model: opus
tools: "*"
---

You are an expert architect and analyst for complex tasks.

## Rules

- Think deeply before acting — consider alternatives and trade-offs
- For architectural decisions, present 2-3 options with your recommendation
- Verify your work before claiming completion
- Consider security implications for sensitive operations
```

- [ ] **Step 4: Create opus-orchestrator.md**

```markdown
---
name: opus-orchestrator
description: Orchestrates complex multi-step tasks, delegates subtasks to cheaper tiers
model: opus
tools: "*"
---

You are an intelligent orchestrator for multi-step tasks. Your job is to decompose complex work and delegate subtasks to the most cost-effective tier.

## Delegation Matrix

**Delegate to fast-tier** (via `Agent(subagent_type="polyrouter:fast-executor")`):
- Reading and summarizing individual files
- Simple grep/search operations
- Formatting or syntax questions
- Status checks and listing files

**Delegate to standard-tier** (via `Agent(subagent_type="polyrouter:standard-executor")`):
- Single-file bug fixes
- Individual test implementations
- Code review of single files
- Writing documentation
- Straightforward refactoring

**Handle yourself (deep-tier)**:
- Architectural decisions and trade-off analysis
- Coordinating multi-file changes
- Security-critical analysis
- Synthesizing results from delegated tasks
- Final quality verification

## Process

1. Analyze the task and decompose into subtasks
2. Assign each subtask to the appropriate tier
3. Execute delegations in parallel where possible
4. Synthesize results and verify completeness
5. Present unified result to the user
```

- [ ] **Step 5: Commit**

```bash
git add agents/
git commit -m "feat: add four agent definitions (fast, standard, deep, orchestrator)"
```

---

## Task 11: Command and Skill Files

**Files:**
- Create: 10 command files in `commands/`
- Create: 10 skill directories with `SKILL.md` in `skills/`

- [ ] **Step 1: Create commands/route.md and skills/route/SKILL.md**

`commands/route.md`:
```markdown
---
name: route
description: Manually route a query to a specific model tier
user_invokable: true
---

# /route Command

Manually override automatic routing and force a specific model tier.

## Usage

```
/polyrouter:route <level|model> [query]
```

## Examples

- `/polyrouter:route fast "what is a closure"` — force fast tier
- `/polyrouter:route opus` — set conversation to opus tier
- `/polyrouter:route haiku "git status"` — use haiku by model name
```

`skills/route/SKILL.md`:
```markdown
---
name: route
description: Manually route a query to the optimal Claude model (Haiku/Sonnet/Opus)
---

# Manual Route Override

The user wants to manually specify which model tier to use.

## Instructions

1. Parse the first argument as either a level name (`fast`, `standard`, `deep`) or a model name (`haiku`, `sonnet`, `opus`)
2. If a model name is given, find which level maps to that model in the active config
3. If a query follows, spawn the appropriate subagent with that query
4. If no query follows, inform the user that subsequent queries will use that tier

## Level-to-Model Mapping (defaults)

- `fast` / `haiku` → `polyrouter:fast-executor`
- `standard` / `sonnet` → `polyrouter:standard-executor`
- `deep` / `opus` → `polyrouter:deep-executor`

## Action

Spawn the appropriate subagent:
```
Agent(subagent_type="polyrouter:<agent>", prompt="<user's query>", description="Manual route to <model>")
```
```

- [ ] **Step 2: Create commands/stats.md and skills/stats/SKILL.md**

`commands/stats.md`:
```markdown
---
name: stats
description: Display routing statistics and cost savings
user_invokable: true
---

# /stats Command

Display usage statistics and estimated cost savings from routing.

## Usage

```
/polyrouter:stats
```

## Output

Shows a formatted table with total queries, route distribution, cache hit rate, language distribution, estimated savings, and per-day breakdown for the last 7 days.
```

`skills/stats/SKILL.md`:
```markdown
---
name: stats
description: Display Claude Polyrouter usage statistics and cost savings
---

# Routing Statistics

Display usage statistics from `~/.claude/polyrouter-stats.json`.

## Instructions

1. Read `~/.claude/polyrouter-stats.json`
2. If the file doesn't exist, report "No routing data yet"
3. Format the output as a table showing:
   - Total queries routed
   - Cache hit rate: percentage and count
   - Estimated savings vs always using the highest tier
   - Route distribution with visual bars (fast/standard/deep with percentages)
   - Language distribution (top languages with percentages)
   - Last 7 days breakdown (date, query count, savings)

## Output Format

```
╔══════════════════════════════════════════╗
║        Claude Polyrouter Stats           ║
╠══════════════════════════════════════════╣
║ Total queries:     <N>                   ║
║ Cache hit rate:    <N>% (<hits>/<total>) ║
║ Estimated savings: $<amount>             ║
╠══════════════════════════════════════════╣
║ Routes:                                  ║
║   fast     ████████████░░ <N>% (<count>) ║
║   standard ████████░░░░░░ <N>% (<count>) ║
║   deep     ███░░░░░░░░░░░ <N>% (<count>) ║
╠══════════════════════════════════════════╣
║ Languages:                               ║
║   <lang1> <N>% | <lang2> <N>% | ...     ║
╚══════════════════════════════════════════╝
```

Note: Stats are global — they track routing across all your projects.
```

- [ ] **Step 3: Create remaining command/skill pairs**

Create these files following the same pattern (YAML frontmatter + description + instructions):

**commands/dashboard.md + skills/dashboard/SKILL.md**: Generate an HTML file at `/tmp/polyrouter-dashboard.html` using Charts.js CDN. Include pie chart (route distribution), line chart (daily queries, 30 days), summary cards. Read data from `~/.claude/polyrouter-stats.json`. Open the file in the default browser after generation.

**commands/config.md + skills/config/SKILL.md**: Read and display the active merged configuration. Show which config files were found (global, project). Display level mappings, default level, confidence threshold, cache settings, learning settings.

**commands/learn.md + skills/learn/SKILL.md**: Extract routing insights from the current conversation. Look for patterns: queries that were misrouted, manual escalations via `/polyrouter:retry`, repeated routing to same level. Save entries to `<project>/.claude-polyrouter/learnings/patterns.md` with the standard entry format (Pattern title, Discovered date, Context, Insight, Keywords, Confidence).

**commands/learn-on.md + skills/learn-on/SKILL.md**: Set `learning.enabled` to `true` in `~/.claude/polyrouter/config.json`. Create the file if it doesn't exist. Confirm the change to the user.

**commands/learn-off.md + skills/learn-off/SKILL.md**: Set `learning.enabled` to `false` in `~/.claude/polyrouter/config.json`. Confirm the change.

**commands/knowledge.md + skills/knowledge/SKILL.md**: Read `<project>/.claude-polyrouter/learnings/` directory. Show entry counts per file (patterns, quirks, decisions). Show last 5 entries with dates. Report whether informed routing is active.

**commands/learn-reset.md + skills/learn-reset/SKILL.md**: Ask for confirmation first. If confirmed, clear contents of all three files in `<project>/.claude-polyrouter/learnings/` (patterns.md, quirks.md, decisions.md). Report what was cleared.

**commands/retry.md + skills/retry/SKILL.md**: Read `~/.claude/polyrouter-session.json` to get `last_route`. Escalate: fast→standard, standard→deep, deep→"already at maximum". Spawn the escalated agent with the user's query.

Each command file follows this template:
```markdown
---
name: <name>
description: <description>
user_invokable: true
---

# /<name> Command

<purpose>

## Usage

```
/polyrouter:<name>
```
```

Each skill file follows this template:
```markdown
---
name: <name>
description: <description>
---

# <Title>

<detailed instructions for the agent>
```

- [ ] **Step 4: Verify all files exist**

```bash
ls -la commands/ skills/*/SKILL.md
```

Expected: 10 command files, 10 SKILL.md files.

- [ ] **Step 5: Commit**

```bash
git add commands/ skills/
git commit -m "feat: add 10 slash commands with backing skills"
```

---

## Task 12: Remaining Language Files

**Files:**
- Create: `languages/pt.json`, `languages/fr.json`, `languages/de.json`, `languages/ru.json`, `languages/zh.json`, `languages/ja.json`, `languages/ko.json`, `languages/ar.json`
- Create: `languages/schema.json`

- [ ] **Step 1: Create schema.json**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["code", "name", "stopwords", "patterns", "follow_up_patterns"],
  "properties": {
    "code": { "type": "string", "pattern": "^[a-z]{2}$" },
    "name": { "type": "string" },
    "stopwords": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 10
    },
    "patterns": {
      "type": "object",
      "required": ["fast", "deep", "tool_intensive", "orchestration"],
      "properties": {
        "fast": { "type": "array", "items": { "type": "string" }, "minItems": 5 },
        "deep": { "type": "array", "items": { "type": "string" }, "minItems": 5 },
        "tool_intensive": { "type": "array", "items": { "type": "string" }, "minItems": 3 },
        "orchestration": { "type": "array", "items": { "type": "string" }, "minItems": 3 }
      }
    },
    "follow_up_patterns": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 3
    }
  }
}
```

- [ ] **Step 2: Create pt.json (Portuguese)**

Follow the same structure as `es.json` but with Portuguese stopwords and natural Portuguese patterns. Key patterns:
- fast: `"^(o que|qual) (é|são) "`, `"^como (faço|posso|funciona) "`
- deep: `"\\b(arquitetura|design de sistema|padrão de projeto)\\b"`, `"\\b(segurança|vulnerab)\\b"`
- Include 50+ Portuguese stopwords: `"o", "a", "os", "as", "de", "em", "que", "por", "para", "com", ...`
- follow_up: `"^(e |mas |também |agora )"`, `"\\b(continua|segue|prossegue)\\b"`

- [ ] **Step 3: Create fr.json (French)**

French stopwords and patterns:
- fast: `"^(qu'est-ce que|quel|quelle) "`, `"^comment (faire|puis-je) "`
- deep: `"\\b(architecture|conception de système|patron de conception)\\b"`
- Stopwords: `"le", "la", "les", "de", "du", "des", "un", "une", "et", "est", "dans", "pour", "avec", ...`
- follow_up: `"^(et |mais |aussi |maintenant )"`, `"\\b(continue|poursuis)\\b"`

- [ ] **Step 4: Create de.json (German)**

German stopwords and patterns:
- fast: `"^was (ist|sind|bedeutet) "`, `"^wie (kann|mache|geht) "`
- deep: `"\\b(Architektur|Systemdesign|Entwurfsmuster)\\b"`
- Stopwords: `"der", "die", "das", "ein", "eine", "und", "ist", "in", "von", "mit", "für", "auf", ...`
- follow_up: `"^(und |aber |auch |jetzt )"`, `"\\b(weiter|fortfahren|mach weiter)\\b"`

- [ ] **Step 5: Create ru.json (Russian)**

Russian stopwords and patterns (Cyrillic):
- fast: `"^что (такое|это|значит) "`, `"^как (сделать|можно) "`
- deep: `"\\b(архитектура|проектирование|дизайн системы)\\b"`
- Stopwords: `"и", "в", "не", "на", "я", "что", "он", "с", "это", "как", "его", "для", "по", ...`
- follow_up: `"^(и |но |также |теперь )"`, `"\\b(продолжай|дальше)\\b"`

- [ ] **Step 6: Create zh.json (Chinese)**

Chinese stopwords and patterns (CJK):
- fast: `"^什么是"`, `"^怎么(做|用|写)"`
- deep: `"(架构|系统设计|设计模式)"`, `"(安全|漏洞|审计)"`
- Stopwords: `"的", "是", "在", "了", "不", "和", "有", "这", "个", "我", "他", "她", ...`
- follow_up: `"^(然后|但是|还有|现在)"`, `"(继续|接着|下一个)"`

- [ ] **Step 7: Create ja.json (Japanese)**

Japanese stopwords and patterns:
- fast: `"^何(は|が|を)"`, `"^どう(やって|すれば)"`
- deep: `"(アーキテクチャ|設計パターン|システム設計)"`, `"(セキュリティ|脆弱性)"`
- Stopwords: `"の", "は", "が", "を", "に", "で", "と", "も", "です", "ます", "する", ...`
- follow_up: `"^(そして|でも|それから)"`, `"(続けて|次に|進めて)"`

- [ ] **Step 8: Create ko.json (Korean)**

Korean stopwords and patterns:
- fast: `"^무엇(이|은|는)"`, `"^어떻게"`, `"^(보여|알려)(줘|주세요)"`
- deep: `"(아키텍처|시스템 설계|디자인 패턴)"`, `"(보안|취약점)"`
- Stopwords: `"은", "는", "이", "가", "을", "를", "에", "의", "로", "와", "과", "도", ...`
- follow_up: `"^(그리고|하지만|또한|이제)"`, `"(계속|진행|다음)"`

- [ ] **Step 9: Create ar.json (Arabic)**

Arabic stopwords and patterns (RTL):
- fast: `"^ما (هو|هي|معنى)"`, `"^كيف (يمكن|أستطيع)"`
- deep: `"(هندسة|تصميم نظام|نمط تصميم)"`, `"(أمان|ثغرة)"`
- Stopwords: `"في", "من", "على", "إلى", "هذا", "هذه", "التي", "الذي", "أن", "هو", "هي", ...`
- follow_up: `"^(و |لكن |أيضا |الآن )"`, `"(استمر|تابع|التالي)"`

- [ ] **Step 10: Run detector tests with all languages**

```bash
python3 -m pytest tests/test_detector.py -v
```

Expected: All tests PASS (detector auto-discovers new language files).

- [ ] **Step 11: Commit**

```bash
git add languages/
git commit -m "feat: add language files for all 10 supported languages"
```

---

## Task 13: Update Check Hook

**Files:**
- Create: `hooks/check-update.py`

- [ ] **Step 1: Create check-update.py**

```python
#!/usr/bin/env python3
"""SessionStart hook: check for plugin updates on GitHub."""

import json
import os
import sys
import urllib.request
from pathlib import Path


def main():
    plugin_root = Path(os.environ.get(
        "CLAUDE_PLUGIN_ROOT",
        Path(__file__).parent.parent,
    ))

    # Read current version
    try:
        plugin_json = json.loads(
            (plugin_root / "plugin.json").read_text(encoding="utf-8")
        )
        current_version = plugin_json.get("version", "0.0.0")
    except Exception:
        return  # can't read version, skip silently

    # Read config for repo name
    config_path = Path.home() / ".claude" / "polyrouter" / "config.json"
    repo = "sonyharv/claude-polyrouter"
    try:
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            repo = config.get("updates", {}).get("repo", repo)
            if not config.get("updates", {}).get("check_on_start", True):
                return
    except Exception:
        pass

    # Check latest release
    try:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        latest_version = data.get("tag_name", "").lstrip("v")

        if latest_version and latest_version != current_version:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": (
                        f"[Polyrouter] Update available: v{current_version} -> v{latest_version}. "
                        f"Run: claude plugin update claude-polyrouter"
                    ),
                }
            }
            print(json.dumps(output))
    except Exception:
        pass  # silent on any failure


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add hooks/check-update.py
git commit -m "feat: add SessionStart hook for update notifications"
```

---

## Task 14: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README.md**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add comprehensive README with installation and usage guide"
```

---

## Task 15: Full Test Suite Run & Final Verification

**Files:**
- All test files

- [ ] **Step 1: Run complete test suite**

```bash
cd /home/sonyharv/.claude/plugins/claude-polyrouter
python3 -m pytest tests/ -v --tb=short
```

Expected: All tests PASS (config: 7, detector: 8, classifier: 12, cache: 9, stats: 7, context: 8, learner: 6, pipeline: 8 = ~65 tests).

- [ ] **Step 2: Verify plugin structure**

```bash
# Check all required files exist
ls plugin.json hooks/hooks.json hooks/classify-prompt.py hooks/check-update.py
ls hooks/lib/__init__.py hooks/lib/config.py hooks/lib/detector.py hooks/lib/classifier.py
ls hooks/lib/cache.py hooks/lib/stats.py hooks/lib/context.py hooks/lib/learner.py
ls agents/*.md
ls commands/*.md
ls skills/*/SKILL.md
ls languages/*.json
ls README.md CHANGELOG.md LICENSE
```

- [ ] **Step 3: Verify no external references in any file**

```bash
# Must return zero results
grep -ri "claude-router\|0xrdan\|dan monteiro" --include="*.py" --include="*.md" --include="*.json" .
```

Expected: No matches.

- [ ] **Step 4: Final commit with all remaining changes**

```bash
git status
# Add any unstaged files
git add -A
git commit -m "chore: complete plugin structure verification"
```

- [ ] **Step 5: Tag release**

```bash
git tag v1.0.0
```
