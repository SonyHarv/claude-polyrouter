# Claude Polyrouter — Design Documentation

Design documentation for Claude Polyrouter, an intelligent multilingual model routing plugin for Claude Code.

## Documents

- [[Architectural Decisions]] — Key design decisions with rationale and alternatives considered
- [[Classification Pipeline]] — Six-stage pipeline: exception check, cache, language detection, classification, context boost, learned adjustments
- [[Plugin Structure]] — Complete file tree, hooks, agents, language file format, runtime files
- [[Commands]] — All 10 slash commands with usage details
- [[Roadmap v2]] — Multi-provider support (Codex, Gemini), ultra tier, cross-agent routing

## Quick Reference

| Aspect | Detail |
|--------|--------|
| **Languages** | English, Spanish, Portuguese, French, German, Russian, Chinese, Japanese, Korean, Arabic + Spanglish |
| **Routing levels** | `fast` (haiku), `standard` (sonnet), `deep` (opus) — configurable |
| **Classification** | Pure rule-based, ~1ms, zero API calls |
| **Config** | Zero-config default, global + project override merge |
| **Commands** | 10 slash commands |
| **Agents** | 4 (fast, standard, deep, orchestrator) |

## Source Spec

Full design specification: `docs/superpowers/specs/2026-04-02-claude-polyrouter-design.md`
