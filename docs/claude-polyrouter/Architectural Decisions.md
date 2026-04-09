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

---

## AD-009: Multi-Signal Scoring over Decision Matrix (v1.4.0)

**Decision:** Replace the discrete pattern-count decision matrix with a continuous 0.0–1.0 scoring engine that combines 9 weighted signals (pattern depth, structural features, session context).

**Rationale:** Pattern counting produced binary "deep or not" decisions with no confidence gradient. The weighted scorer allows nuanced routing — a prompt with 2 deep patterns but short length routes differently than one with 2 deep patterns and 3 code blocks. Weights are configurable via `config.json`.

**Alternatives considered:**
- LLM-based classification — rejected per AD-005 (no API calls)
- Bayesian classifier — rejected as overengineered for the signal count

---

## AD-010: Compact Advisory over Direct Message Manipulation (v1.4.0)

**Decision:** The compact system operates as an advisory — it detects stale tool results and token thresholds, then emits a recommendation in `additionalContext`. It does not directly modify conversation messages.

**Rationale:** Claude Code hooks receive the user prompt but not the full message history. Direct manipulation is architecturally impossible. The advisory approach leverages Claude Code's native compact system while polyrouter tracks and reports.

---

## AD-011: Zero-Token StatusLine HUD (v1.4.0)

**Decision:** Move all display information (confidence, method, signals, language, cache bar) to the `StatusLine` hook. Keep `additionalContext` to the minimal routing directive only (~50 tokens).

**Rationale:** The v1.3 HUD consumed ~150 tokens per query in `additionalContext` for display purposes. StatusLine is rendered by Claude Code's UI at zero token cost. This reduces per-query overhead by ~67%.

---

## AD-012: Timestamp-Based Animation Ticks (v1.4.0)

**Decision:** Use `Date.now()` (mjs) / `time.time()` (Python) modulo frame count for mascot animation, not conversation depth.

**Rationale:** Conversation depth changes slowly (once per user message), producing a static mascot. Timestamp-based ticks produce a different frame on each StatusLine refresh (~1-3s intervals), creating visible animation.

---

## AD-013: Cache Freshness Bar (v1.4.0)

**Decision:** Display a 5-block visual bar (█████ → ░░░░░) in the StatusLine showing prompt cache age, with color coding: green (0-10min), yellow (10-30min), orange (30-50min), red (50+min expired).

**Rationale:** Cache state is invisible to the user but affects cost. The bar provides at-a-glance awareness. The 50-min expired threshold aligns with the keep-alive hook's threshold and triggers the danger mascot state.
