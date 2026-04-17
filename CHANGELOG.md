# Changelog

## [1.6.0] - 2026-04-16

**HUD v1.6 redesign · Accurate savings calc · Idle fallback · 613 tests passing**

### Added
- **HUD v1.6 redesign** — New format: `[poly v1.6] [^.^]~ haiku·fast │ cache:████░ ctx:8% │ 5h:45%(1h2m) wk:9%(6d19h) snt:3%(6d19h) │ $0.03↓ es`. Prompt/exec split for subagent display, `🤖N` subagent counter, `ctx:%` from `transcript_path`, rate-limit bar (requires `ccusage`), `⚠compact` advisory at ctx≥70%, new mascot states `ctx_high` and `critical` (`[>.^]` / `[x.x]`).
- **Idle fallback** — When session is stale (>30 min) and OMC is absent, HUD now emits `[poly v1.6] [^.^]~ idle` instead of going blank.
- **DE/FR/PT multi-file patterns** — `feat(v1.6)`: deep+xhigh routing for multi-file refactor prompts in German, French, and Portuguese.
- **Spanish `rediseño` fix** — `fix(v1.6)`: noun form and all inflections now match deep-tier patterns.

### Changed
- **Accurate savings calc** — Per-token formula using 1 000 input + 500 output tokens per prompt (documented approximation). Old formula used `input + 2×output` with stale Opus pricing.
- **Opus 4.7 cost constants** — Updated from `$0.005/$0.025` (wrong) to `$0.015/$0.075` per 1k tokens (correct: $15/$75 per 1M as of April 2026).
- **`limits.py` documented** — Module-level comment clarifies ccusage is optional; gracefully returns `None` when absent.

## [1.5.0] - 2026-04-16

**Pinned model IDs · Dynamic deep-tier effort · Advisor Strategy · 558 tests passing**

### Added
- **Pinned model IDs** — `levels.*.model_id` now pins explicit versions: `claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-opus-4-7`. The compact `model` name (haiku/sonnet/opus) is preserved for HUD display.
- **Dynamic deep-tier effort** — Deep routes receive a sub-effort (`medium` / `high` / `xhigh`) derived from composite score + signal mix (architecture keywords, file paths, code blocks, tool intensity, orchestration).
- **xhigh display label** — Polyrouter-only effort label for architectural/critical work. Normalizes to `high` when emitted as `CLAUDE_CODE_EFFORT_LEVEL` (upstream env var supports low/medium/high only).
- **Architectural promotion** — Non-deep queries with architecture keywords + at least one standard/tool/orchestration signal auto-promote to `deep + xhigh` (e.g. _"plan a strategic migration across auth, billing, session"_).
- **Advisor Strategy** — `requires_advisor=true` flag raised automatically on `xhigh`. Persisted in session state, surfaced in the routing header (`Advisor: required`) and as `adv` in the HUD so executors can engage the Advisor (Opus on-demand) for architectural decisions.
- **Subagent lifecycle tracking** — Session state gains `subagent_active`; `session.update()` sets it True when a route is emitted. New `SubagentStop` hook clears it. HUD appends `(subagente)` while the spawned executor is running.
- **New session keys** — `effort_level`, `subagent_active`, `requires_advisor` added to `DEFAULT_SESSION`.

### Changed
- **HUD format extended** — `[polyrouter] · opus · deep · xhigh · adv · (subagente) · cache:… · $…↓ · es`. Order: tier → sub-effort (deep only, medium elided) → advisor flag → subagent tag → cache → savings → language.
- **Effort map tests** — `test_effort.py` and `test_hud.py` cover medium/high/xhigh transitions, architectural promotion, advisor wiring, and subagent tag rendering.

### Fixed
- Removed deprecated `max` effort level (graceful fallback to `high`).

## [1.4.0] - 2026-04-09

**82% token reduction · 100% multilingual accuracy · 501 tests passing**

### Added
- **Multi-signal scoring engine** — Replaces discrete decision matrix with weighted composite scoring across 9 signals (pattern depth, code blocks, error traces, file paths, prompt length, tool results, conversation depth, effort level, universal tech symbols)
- **Dynamic effort mapping** — Automatic effort level computation (low/medium/high) based on routing tier, with user and environment override support
- **Cache keep-alive hook** — PostToolUse hook that detects prompt cache expiration risk and recommends keep-alive pings (50-min threshold, 120-min idle cutoff)
- **Compact advisory system** — Two-layer context management: MicroCompact for stale tool results, SessionMemoryCompact for token thresholds, with circuit breaker (max 3 consecutive failures)
- **Poly animated mascot HUD** — ASCII mascot with 6 states and multi-frame animation: idle `[^.^]~`, routing `[^o^]»»`, keepalive `[~_~]zzz`, danger `[°O°]!!!`, thinking `[^.^]...`, compact `[^.^]~~~`
- **Cache freshness bar** — `cache:█████` (fresh) → `cache:████░` (warm) → `cache:███░░ !` (warning) → `cache:░░░░░ exp` (expired)
- **StatusLine native hook** — Zero-token HUD display via Claude Code's StatusLine event, replacing token-consuming additionalContext for display info
- **HUD Python helper module** (`lib/hud.py`) — Testable state detection, frame selection, and status line formatting
- **Auto-hook injection** — `post-install.sh` auto-configures `settings.json` with correct matcher/hooks format
- New config keys: `scoring`, `effort`, `keepalive`, `compact`, `hud`

### Changed
- **Pipeline upgraded from 6 to 8 stages** — New stages: Pattern extraction (raw signals) and Multi-signal scoring (composite score → tier)
- **additionalContext reduced 82%** — From ~150 tokens (v1.3) to ~27 tokens per query; display info moved to statusLine
- **Classifier refactored** — `classify_query()` replaced with `extract_signals()` returning raw pattern matches; scoring engine handles tier decision
- **Session context extended** — Tracks `last_tool_result_len`, `effort_level` for scorer consumption
- **OMC HUD coexistence** — Poly appends to OMC output with noise filtering; no statusLine conflicts

### Fixed
- HUD overwrite conflict with oh-my-claudecode resolved via append strategy
- HUD mascot frames: removed extra spaces between face and animation (`[^.^]~` not `[^.^]  ~`)
- es/pt: accent-tolerant standard patterns (`funcion`/`funcao` now match)
- ar: added architecture vocabulary (`البنية`, `خدمات مصغرة`) to deep patterns
- ja: added reverse object-verb order patterns for standard tier (SOV word order)
- ru: declension-aware deep patterns (`архитектур[ауые]` matches all cases)

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
