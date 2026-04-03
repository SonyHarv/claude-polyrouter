# Classification Pipeline

## Overview

Six-stage pipeline that runs on every `UserPromptSubmit` hook. Total latency: ~1ms for rule-based classification. Zero external API calls.

## Stages

### 1. Exception Check (~0ms)

Detects queries that should bypass routing entirely:

| Exception | Detection | Action |
|-----------|-----------|--------|
| Slash commands | `query.startswith("/")` | Skip, pass-through |
| Router meta-queries | keywords: `polyrouter`, `routing`, `router` | Skip, pass-through |
| Empty/whitespace | `len(query.strip()) == 0` | Skip, pass-through |
| Continuation tokens | `"sí"`, `"ok"`, `"yes"`, `"continúa"`, etc. | Reuse `last_route` from session |

### 2. Cache Lookup (~0ms)

Two-level cache with MD5 fingerprinting:

- **L1**: In-memory LRU (50 entries, process-scoped)
- **L2**: File-based JSON (100 entries, 30-day TTL, persistent)
- **Key**: MD5 of normalized query (lowercase, no punctuation, sorted words)
- Cache hit returns stored route immediately

### 3. Language Detection (~0.1ms)

Hybrid stopword-based detection:

1. Score each language by `stopword_matches / total_words`
2. If `top_score > 0.15` and gap to second > 0.05 → single language
3. If ambiguous → `multi_eval=True` (evaluate all pattern sets)
4. Spanglish: both `en` and `es` score high → evaluate both
5. Short queries (<4 words) → use `last_language` from session or evaluate all

### 4. Rule-Based Classification (~0.5ms)

Pattern matching against language-specific regex patterns:

**Categories** (fixed, map to decision matrix signals):
- `fast`: Simple questions, formatting, git ops, syntax
- `deep`: Architecture, security, multi-file, trade-offs
- `tool_intensive`: Codebase search, multi-file mods, tests
- `orchestration`: Multi-step workflows, sequential tasks

**Decision matrix priority**:
```
deep + (tool OR orch) → deep @ 0.95
deep >= 2             → deep @ 0.90
deep == 1             → deep @ 0.70
tool >= 2             → standard @ 0.85
tool == 1             → standard @ 0.70
orch >= 1             → standard @ 0.75
fast >= 2             → fast @ 0.90
fast == 1             → fast @ 0.70
no signals            → default_level @ 0.50
```

Early exit if confidence >= 0.85.

### 5. Context Boost (~0ms)

Multi-turn awareness via session state:

- Detects follow-up queries using language-specific `follow_up_patterns`
- If follow-up and `last_route` was complex → boost confidence by 0.1
- Session expires after 30 min inactivity
- `conversation_depth` tracks query count in session

### 6. Learned Adjustments (~0ms)

Optional knowledge-based micro-adjustments:

- Only active if `config.learning.informed_routing == true`
- Reads keywords from project knowledge base
- Requires 2+ keyword matches to trigger
- Max boost: 0.1 (conservative)
- Never downgrades `deep` to `fast`

## Output

The pipeline produces a level (`fast`/`standard`/`deep`), which is resolved to a model and agent via config lookup. The result is injected as a `MANDATORY ROUTING DIRECTIVE` in the hook's `additionalContext`.

## Data Flow

```
Query → Exception? → Cache? → Detect Lang → Classify → Context → Learn → Output
         ↓ skip      ↓ hit                                                  ↓
         pass        return                                          level → config
         through     cached                                          → model + agent
                     route                                           → inject directive
```
