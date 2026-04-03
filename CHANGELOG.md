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
