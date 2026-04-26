---
name: stats
description: Per-session routing breakdown (tier·effort, method, language, savings) — optional `reset`
user_invokable: true
---

<!-- POLY:STATS:v1 -->
# /polyrouter:stats Command

Displays a per-session breakdown of polyrouter's routing decisions
(tier + effort, method frequency, language frequency, cumulative
savings vs all-Opus). Optional `reset` argument zeros the counters
without waiting for the 30-minute SessionState idle timeout.

## Usage

```
/polyrouter:stats          # show breakdown
/polyrouter:stats reset    # zero counters and confirm
```

## Output (mini-bar ASCII format)

```
[POLY:STATS]
Session: 47 routes since 14:32 (1h 47m ago)

Tier · effort:
  fast        ████████████████░░░░ 80.9% (38)
  standard    ███░░░░░░░░░░░░░░░░░ 14.9% (7)
  deep·medium ░░░░░░░░░░░░░░░░░░░░  0.0% (0)
  deep·high   ░░░░░░░░░░░░░░░░░░░░  0.0% (0)
  deep·xhigh  █░░░░░░░░░░░░░░░░░░░  4.3% (2)

Top methods:  scoring (89%) · cache (8%) · intent_override (3%)
Languages:    en (72%) · es (28%)
Savings:      $0.83 vs all-Opus
Retries:      3 invocations of /polyrouter:retry
```

## Reset behaviour

- Resets `routing_started_at`, `routing_counts`, method/lang dicts,
  `routing_savings_total`, and `retry_invocations`.
- **Does not** reset other session state (last_route, retry arrow,
  effort overrides, advisor flag).
- Useful for benchmarking — start a clean window before testing a
  routing change.

## Auto-reset

Counters reset automatically when SessionState times out (default
30 minutes idle). The slash command is for manual control between
auto-resets.
