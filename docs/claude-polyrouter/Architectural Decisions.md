# Architectural Decisions

## AD-001: Modular by Layers Architecture

**Decision:** Separate the classification pipeline into independent Python modules (`detector.py`, `classifier.py`, `cache.py`, `stats.py`, `context.py`, `learner.py`) orchestrated by a thin `classify-prompt.py`.

**Rationale:** Each module stays under 200 lines, is independently testable, and has a single responsibility. Adding a language requires only a JSON file, not touching Python code.

**Alternatives considered:**
- Monolith (single file ~1500 lines) — rejected for maintainability
- Plugin-of-plugins (dynamic registration) — rejected as YAGNI

---

## AD-002: Level Abstraction over Model Names

**Decision:** The classifier produces routing levels (`fast`, `standard`, `deep`), never model names. The level-to-model mapping lives exclusively in config.

**Rationale:** Decouples routing logic from specific models. When new models release (Haiku 4, Sonnet 5, Kairos), only `config.json` changes. Enables future multi-provider support (Codex, Gemini) without classifier changes.

---

## AD-003: Hybrid Language Detection

**Decision:** Detect language via stopword scoring first (~0.1ms). If confidence is high, use only that language's patterns. If ambiguous (short query, Spanglish, mixed), evaluate all languages in parallel.

**Rationale:** Covers 90% of queries with a single language evaluation (fast path). The 10% fallback to multi-eval handles edge cases without penalizing the common case.

**Alternatives considered:**
- Explicit detection only — fails on short/mixed queries
- Universal patterns always — evaluates ~300 patterns unnecessarily for 90% of queries

---

## AD-004: Zero-Config with Config Merge

**Decision:** Plugin works out-of-the-box with hardcoded defaults. Optional config files at global (`~/.claude/polyrouter/config.json`) and project (`.claude-polyrouter/config.json`) levels, merged with shallow override.

**Rationale:** Zero friction for new users. Power users can customize per-project. Shallow merge is predictable and avoids deep-merge surprises.

---

## AD-005: No LLM Fallback Classification

**Decision:** Classification is purely rule-based. No LLM call for ambiguous queries.

**Rationale:** Eliminates API key dependency, reduces latency to ~0ms, and avoids per-query cost. The rule-based system with 10 languages of patterns provides sufficient accuracy. When uncertain, defaulting to `fast` is the correct token-saving behavior.

---

## AD-006: Fresh Start Stats (No Migration)

**Decision:** Use a new stats file (`polyrouter-stats.json`) with a clean schema. No backward compatibility with other solutions.

**Rationale:** Clean schema enables tracking multilingual metrics (`languages_detected`, `cache_hits`) that don't exist in other formats. As a complete replacement, there's no data to preserve.

---

## AD-007: Merge Dashboard and Analytics

**Decision:** Single `/polyrouter:dashboard` command generates a complete HTML analytics page with Charts.js. No separate `analytics` command.

**Rationale:** Two HTML-generating commands with overlapping functionality is confusing. One command with complete visualizations (pie charts, line charts, bar charts, summary cards) covers all needs. Total commands: 10.

---

## AD-008: Continuation Token Handling

**Decision:** Short affirmative tokens (`"sí"`, `"ok"`, `"yes"`, `"continúa"`) reuse `last_route` from session state instead of being re-classified.

**Rationale:** These tokens carry no complexity signal. Re-classifying them would always route to `fast` (50% confidence), breaking the flow when the user is mid-conversation with Opus on a complex task.
