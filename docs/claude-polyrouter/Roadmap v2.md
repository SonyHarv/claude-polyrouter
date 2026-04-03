# Roadmap v2

## Multi-Agent Provider Support

The level abstraction decouples routing logic from specific models. v2 extends this to support multiple AI agent providers:

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

The classifier remains unchanged — it produces levels. The provider resolution layer maps levels to provider-specific models. Adding a new provider = config entries only, no Python changes.

## Ultra Tier

A fourth routing level for next-generation models (Kairos, etc.):

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

## Cross-Agent Routing

Route different parts of a complex task to different providers based on their strengths:

- Code generation → Codex
- Analysis/reasoning → Claude Opus
- Fast lookups → Gemini Flash

Builds on the orchestrator pattern from v1, extending delegation across providers instead of just across tiers.

## v2 Compatibility

v1 config files remain valid in v2. The `providers` key is optional — if absent, the flat `model`/`agent` fields are used (v1 format). Zero migration required.

## Why the v1 Architecture Already Supports This

1. **Level abstraction**: Classifier never outputs model names, only levels
2. **Config-driven mapping**: Model/agent resolution is a config lookup, not hardcoded
3. **Modular pipeline**: Each stage is independent — adding provider resolution is a new module, not a refactor
4. **Language files are provider-agnostic**: Patterns detect complexity, not model capabilities
