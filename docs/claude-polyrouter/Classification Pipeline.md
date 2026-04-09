# Classification Pipeline

## Overview

Eight-stage pipeline (v1.4) that runs on every `UserPromptSubmit` hook. Total latency: ~3ms for multi-signal scoring. Zero external API calls.

## Stages

### 1. Exception Check (~0ms)

Detects queries that should bypass routing entirely:

| Exception | Detection | Action |
|-----------|-----------|--------|
| Slash commands | `query.startswith("/")` | Skip, pass-through |
| Router meta-queries | keywords: `polyrouter`, `routing`, `router` | Skip, pass-through |
| Empty/whitespace | `len(query.strip()) == 0` | Skip, pass-through |
| Continuation tokens | `"sí"`, `"ok"`, `"yes"`, `"continúa"`, etc. | Reuse `last_route` from session |

### 2. Intent Override (~0ms)

Natural language model forcing with maximum priority:

- Detects explicit model requests: "use opus", "con haiku", "think deeply"
- Always overrides all other routing decisions
- Confidence: 0.99 for direct model references

### 3. Cache Lookup (~0ms)

Two-level cache with MD5 fingerprinting:

- **L1**: In-memory LRU (50 entries, process-scoped)
- **L2**: File-based JSON (100 entries, 30-day TTL, persistent)
- **Key**: MD5 of normalized query (lowercase, no punctuation, sorted words)
- Cache hit returns stored route immediately

### 4. Language Detection (~0.1ms)

Hybrid stopword-based detection:

1. Score each language by `stopword_matches / total_words`
2. If `top_score > 0.15` and gap to second > 0.05 → single language
3. If ambiguous → `multi_eval=True` (evaluate all pattern sets)
4. Spanglish: both `en` and `es` score high → evaluate both
5. Short queries (<4 words) → use `last_language` from session or evaluate all

### 5. Pattern Extraction (~0.5ms)

Raw signal counting from language-specific regex patterns (no tier decision):

**Categories** (fixed, feed into scorer):
- `fast`: Simple questions, formatting, git ops, syntax
- `deep`: Architecture, security, multi-file, trade-offs
- `tool_intensive`: Codebase search, multi-file mods, tests
- `orchestration`: Multi-step workflows, sequential tasks

Returns `PatternSignals` with raw match counts and word count.

### 6. Multi-Signal Scoring (~1ms)

Weighted composite scoring engine combining 9 signals:

| Signal | Weight | Source |
|--------|--------|--------|
| Pattern depth | 0.30 | Deep pattern matches from stage 5 |
| Pattern standard | 0.20 | Standard pattern matches from stage 5 |
| Code blocks | 0.15 | Count of ``` blocks in prompt |
| Error traces | 0.10 | Stacktrace/traceback/error patterns |
| File paths | 0.08 | `/path/to/file` references |
| Prompt length | 0.07 | Normalized chars / 2000, capped at 1.0 |
| Tool result length | 0.05 | Previous tool_result length from session |
| Conversation depth | 0.03 | Turn count in current session |
| Effort level | 0.02 | User effort setting as signal |

**Score → Tier mapping**:
```
score < 0.30  → fast   (confidence based on distance from boundary)
0.30 ≤ score < 0.65 → standard
score ≥ 0.65  → deep
```

Short queries (<4 words, no signals) fast-track to `fast` at 0.85 confidence.

### 7. Context Boost (~0ms)

Multi-turn awareness via session state:

- Detects follow-up queries using language-specific `follow_up_patterns`
- If follow-up and `last_route` was complex → boost confidence by 0.1
- Session expires after 30 min inactivity
- `conversation_depth` tracks query count in session

### 8. Learned Adjustments (~0ms)

Optional knowledge-based micro-adjustments:

- Only active if `config.learning.informed_routing == true`
- Reads keywords from project knowledge base
- Requires 2+ keyword matches to trigger
- Max boost: 0.1 (conservative)
- Never downgrades `deep` to `fast`

## Output

The pipeline produces a level (`fast`/`standard`/`deep`), which is resolved to a model and agent via config lookup. The result is injected as a minimal routing directive (~50 tokens) in the hook's `additionalContext`. Display info (confidence, method, signals, language) is shown via the StatusLine hook at zero token cost.

## Data Flow

```
Query → Exception? → Intent? → Cache? → Lang → Patterns → Score → Context → Learn → Output
         ↓ skip      ↓ force   ↓ hit                                                  ↓
         pass        return    return                                          level → config
         through     override  cached                                          → model + agent
                     route     route                                           → minimal directive
```

## Additional Hooks

| Event | Script | Purpose |
|-------|--------|---------|
| `PostToolUse` | `cache-keepalive.py` | Detect prompt cache expiration risk |
| `StatusLine` | `polyrouter-hud.mjs` | Zero-token animated HUD display |

## StatusLine Format

```
[polyrouter] [^.^] ~ · sonnet · std · ████░ · $10.63↓ · es
             ╰mascot╯  ╰model╯ ╰tier╯ ╰cache╯ ╰savings╯ ╰lang╯
```

**Cache freshness bar** (5 blocks):
- `█████` green (#97c459) — 0–10 min, cache fresh
- `████░` yellow (#ef9f27) — 10–30 min, cache warm
- `███░░` orange (#e8853a) — 30–50 min, cache cooling
- `░░░░░` red (#e24b4a) — 50+ min, cache expired → danger state

**Mascot animation**: frame selected by `timestamp % frame_count`, producing visible animation on each StatusLine refresh.
