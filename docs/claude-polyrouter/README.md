# Claude Polyrouter — Design Documentation (v1.4.0)

Design documentation for Claude Polyrouter, an intelligent multilingual model routing plugin for Claude Code.

## Documents

- [[Architectural Decisions]] — Key design decisions with rationale and alternatives considered
- [[Classification Pipeline]] — Eight-stage pipeline: exception check, intent override, cache, language detection, pattern extraction, multi-signal scoring, context boost, learned adjustments
- [[Plugin Structure]] — Complete file tree, hooks, agents, language file format, runtime files
- [[Commands]] — All 10 slash commands with usage details
- [[Roadmap v2]] — Multi-provider support (Codex, Gemini), ultra tier, cross-agent routing

## Quick Reference

| Aspect | Detail |
|--------|--------|
| **Version** | 1.4.0 |
| **Languages** | English, Spanish, Portuguese, French, German, Russian, Chinese, Japanese, Korean, Arabic + Spanglish |
| **Routing levels** | `fast` (haiku), `standard` (sonnet), `deep` (opus) — configurable |
| **Classification** | Multi-signal scoring (9 signals), ~3ms, zero API calls |
| **Effort mapping** | Dynamic `low`/`medium`/`high` per tier, user override supported |
| **Cache keep-alive** | PostToolUse hook prevents prompt cache expiration (50-min threshold) |
| **Compact advisory** | MicroCompact + SessionMemoryCompact with circuit breaker |
| **HUD** | Animated Poly mascot via StatusLine (zero token cost) with cache freshness bar |
| **Config** | Zero-config default, global + project override merge |
| **Commands** | 10 slash commands |
| **Agents** | 4 (fast, standard, deep, orchestrator) |

## What's New in v1.4.0

- **Multi-signal scoring engine** — 9 weighted signals replace discrete pattern counting
- **Dynamic effort mapping** — automatic `low`/`medium`/`high` effort per tier
- **Cache keep-alive hook** — invisible PostToolUse ping keeps Anthropic prompt cache warm
- **Compact advisory system** — two-layer advisory (MicroCompact + SessionMemoryCompact) with circuit breaker
- **Poly animated mascot** — 6 states (idle, routing, keepalive, danger, thinking, compact) with frame animation
- **Cache freshness bar** — 5-block visual indicator (█████ fresh → ░░░░░ expired) in StatusLine
- **Token reduction** — additionalContext reduced from ~150 to ~50 tokens; display info moved to StatusLine

## Source Spec

Full design specification: `docs/superpowers/specs/2026-04-02-claude-polyrouter-design.md`
