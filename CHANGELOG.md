# Changelog

## [1.4.0] - 2026-04-09

### Added
- **Multi-signal scoring engine** — Replaces discrete decision matrix with weighted composite scoring across 9 signals (pattern depth, code blocks, error traces, file paths, prompt length, tool results, conversation depth, effort level)
- **Dynamic effort mapping** — Automatic effort level computation (low/medium/high) based on routing tier, with user and environment override support
- **Cache keep-alive hook** — PostToolUse hook that detects prompt cache expiration risk and recommends keep-alive pings (50-min threshold, 120-min idle cutoff)
- **Compact advisory system** — Two-layer context management: MicroCompact for stale tool results, SessionMemoryCompact for token thresholds, with circuit breaker (max 3 consecutive failures)
- **Poly animated mascot HUD** — ASCII mascot with 6 states and multi-frame animation: idle `[^.^] ~`, routing `[^o^] »»`, keepalive `[~_~] zzz`, danger `[°O°] !`, thinking `[^.^] ...`, compact `[^.^] ~~~`
- **StatusLine native hook** — Zero-token HUD display via Claude Code's StatusLine event, replacing token-consuming additionalContext for display info
- **HUD Python helper module** (`lib/hud.py`) — Testable state detection, frame selection, and status line formatting
- New config keys: `scoring`, `effort`, `keepalive`, `compact`, `hud`

### Changed
- **Pipeline upgraded from 6 to 8 stages** — New stages: Pattern extraction (raw signals) and Multi-signal scoring (composite score → tier)
- **Minimal additionalContext** — Routing directive reduced from ~150 tokens to ~50 tokens per query; display info moved to statusLine
- **Classifier refactored** — `classify_query()` replaced with `extract_signals()` returning raw pattern matches; scoring engine handles tier decision
- **Session context extended** — Tracks `last_tool_result_len`, `effort_level` for scorer consumption
- **OMC HUD coexistence** — Poly appends to OMC output with noise filtering; no statusLine conflicts

### Fixed
- HUD overwrite conflict with oh-my-claudecode resolved via append strategy

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
