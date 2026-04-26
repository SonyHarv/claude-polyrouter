"""Multi-turn session state management."""

import copy
import json
import re
import time
from pathlib import Path

DEFAULT_SESSION = {
    "last_route": None,
    "last_level": None,
    "conversation_depth": 0,
    "last_query_time": None,
    "last_language": None,
    "last_tool_result_len": 0,
    "effort_level": "medium",
    "subagent_active": False,
    "requires_advisor": False,
    # v1.6 additions
    "subagent_count": 0,
    "exec_model": None,
    "exec_effort": None,
    "exec_advisor": False,
    "ctx_tokens": 0,
    "limits": None,
    # v1.7: silent model swap detection
    "swap_detected": False,
    "swap_expected": None,   # tier family, e.g. "haiku"
    "swap_actual": None,     # full model id from transcript, e.g. "claude-opus-4-7"
    # v1.7: retry-escalation arrow
    "retry_active": False,
    "retry_from_tier": None,    # "fast" | "standard" | "deep"
    "retry_from_effort": None,  # "low" | "medium" | "high" | "xhigh" | None
    "retry_to_tier": None,
    "retry_to_effort": None,
    "retry_at_ceiling": False,  # True only when prev was deep/xhigh — render ⚠max
    # v1.7 SCOPE FIRME #5: one-shot effort override from /polyrouter:effort
    "effort_override_active": False,
    "effort_override_level": None,         # "low" | "medium" | "high" | "xhigh"
    "effort_override_promote_deep": False, # True iff level=="xhigh" — auto-promote tier
    # v1.7 ADICIONAL #9: per-session routing breakdown (full audit)
    "routing_started_at": None,            # epoch seconds — set on first record
    "routing_counts": {
        "fast": 0,
        "standard": 0,
        "deep_medium": 0,
        "deep_high": 0,
        "deep_xhigh": 0,
    },
    "routing_method_counts": {},           # method-name → count
    "routing_lang_counts": {},             # language code → count
    "routing_savings_total": 0.0,          # cumulative $ savings vs all-opus
    "retry_invocations": 0,                # count of /polyrouter:retry uses
}


class SessionState:
    def __init__(self, path: Path, timeout_minutes: int = 30):
        self._path = path
        self._timeout_seconds = max(0, timeout_minutes) * 60
        self._state: dict | None = None

    def read(self) -> dict:
        if self._state is not None:
            return self._state
        if not self._path.exists():
            self._state = copy.deepcopy(DEFAULT_SESSION)
            return self._state
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                self._state = copy.deepcopy(DEFAULT_SESSION)
                return self._state
            last_time = data.get("last_query_time")
            if last_time and isinstance(last_time, (int, float)) and (time.time() - last_time) > self._timeout_seconds:
                self._state = copy.deepcopy(DEFAULT_SESSION)
                return self._state
            self._state = data
            return self._state
        except Exception:
            self._state = copy.deepcopy(DEFAULT_SESSION)
            return self._state

    def get_scorer_context(self) -> dict:
        """Return context dict for the multi-signal scorer."""
        state = self.read()
        return {
            "conversation_depth": state.get("conversation_depth", 0),
            "last_tool_result_len": state.get("last_tool_result_len", 0),
            "effort_level": state.get("effort_level", "medium"),
        }

    def update(
        self,
        level: str,
        language: str | None,
        requires_advisor: bool = False,
    ) -> None:
        state = self.read()
        state["last_route"] = level
        state["last_level"] = level
        state["conversation_depth"] = state.get("conversation_depth", 0) + 1
        state["last_query_time"] = time.time()
        state["subagent_active"] = True
        state["requires_advisor"] = bool(requires_advisor)
        if language and isinstance(language, str):
            state["last_language"] = language
        self._state = state
        self._write(state)

    def mark_subagent_active(
        self,
        subagent_name: str | None = None,
        exec_model: str | None = None,
        exec_effort: str | None = None,
        exec_advisor: bool = False,
    ) -> None:
        """Set subagent_active, increment counter, snapshot exec params."""
        state = self.read()
        state["subagent_active"] = True
        state["subagent_count"] = state.get("subagent_count", 0) + 1
        state["exec_model"] = exec_model
        state["exec_effort"] = exec_effort
        state["exec_advisor"] = bool(exec_advisor)
        self._state = state
        self._write(state)

    def mark_subagent_stopped(self) -> None:
        """Clear the subagent_active flag (called by SubagentStop hook).

        Keeps subagent_count and exec_* snapshots — rendering gates on
        subagent_active so exec segment disappears automatically.
        """
        state = self.read()
        state["subagent_active"] = False
        state["requires_advisor"] = False
        self._state = state
        self._write(state)

    def update_tool_result_len(self, length: int) -> None:
        """Track the length of the last tool result (set by PostToolUse hook)."""
        state = self.read()
        state["last_tool_result_len"] = max(0, int(length))
        self._state = state
        self._write(state)

    def update_effort(self, effort: str) -> None:
        """Track effort level from environment or user override.

        Accepts display labels including "xhigh" (polyrouter-only v1.5).
        The raw label is stored; callers that need a Claude-Code-valid
        env value should normalize via effort.normalize_effort_for_env().
        """
        if effort in ("low", "medium", "high", "xhigh"):
            state = self.read()
            state["effort_level"] = effort
            self._state = state
            self._write(state)

    def set_advisor(self, required: bool) -> None:
        """Persist whether the Advisor (Opus on-demand) should be engaged."""
        state = self.read()
        state["requires_advisor"] = bool(required)
        self._state = state
        self._write(state)

    def update_ctx_tokens(self, tokens: int) -> None:
        """Persist latest context token count (written by classify-prompt)."""
        state = self.read()
        state["ctx_tokens"] = max(0, int(tokens))
        self._state = state
        self._write(state)

    def update_limits(self, limits: dict | None) -> None:
        """Persist latest rate-limit snapshot from ccusage."""
        state = self.read()
        state["limits"] = limits
        self._state = state
        self._write(state)

    def mark_swap(self, expected: str, actual: str) -> None:
        """Persist a silent model swap detection (v1.7).

        expected: tier family poly routed for (e.g. "haiku").
        actual:   model id Claude Code actually used (e.g. "claude-opus-4-7").
        """
        state = self.read()
        state["swap_detected"] = True
        state["swap_expected"] = expected if isinstance(expected, str) else None
        state["swap_actual"] = actual if isinstance(actual, str) else None
        self._state = state
        self._write(state)

    def clear_swap(self) -> None:
        """Clear any prior swap flag (no divergence detected this turn)."""
        state = self.read()
        state["swap_detected"] = False
        state["swap_expected"] = None
        state["swap_actual"] = None
        self._state = state
        self._write(state)

    def mark_retry(
        self,
        from_tier: str,
        from_effort: str | None,
        to_tier: str,
        to_effort: str | None,
        at_ceiling: bool = False,
    ) -> None:
        """Persist a retry-escalation transition (v1.7).

        from_tier/from_effort: where the previous turn routed.
        to_tier/to_effort:     where this retry escalated to.
        at_ceiling: True only when prev was deep/xhigh (no actual escalation
                    happened — HUD renders ⚠max instead of an arrow).
        """
        state = self.read()
        state["retry_active"] = True
        state["retry_from_tier"] = from_tier if isinstance(from_tier, str) else None
        state["retry_from_effort"] = from_effort if isinstance(from_effort, str) else None
        state["retry_to_tier"] = to_tier if isinstance(to_tier, str) else None
        state["retry_to_effort"] = to_effort if isinstance(to_effort, str) else None
        state["retry_at_ceiling"] = bool(at_ceiling)
        self._state = state
        self._write(state)

    def clear_retry(self) -> None:
        """Clear any prior retry flag (next normal prompt)."""
        state = self.read()
        state["retry_active"] = False
        state["retry_from_tier"] = None
        state["retry_from_effort"] = None
        state["retry_to_tier"] = None
        state["retry_to_effort"] = None
        state["retry_at_ceiling"] = False
        self._state = state
        self._write(state)

    def set_effort_override(self, level: str, promote_deep: bool = False) -> None:
        """Persist a one-shot effort override from /polyrouter:effort (v1.7).

        Consumed by the next normal-prompt routing pass via
        consume_effort_override(); single-fire — never persists across
        more than one turn.
        """
        if level not in ("low", "medium", "high", "xhigh"):
            return
        state = self.read()
        state["effort_override_active"] = True
        state["effort_override_level"] = level
        state["effort_override_promote_deep"] = bool(promote_deep)
        self._state = state
        self._write(state)

    def consume_effort_override(self) -> dict | None:
        """Pop the one-shot effort override (returns + clears).

        Returns {"level": str, "promote_deep": bool} when active,
        otherwise None. Clears the flag in either path so the override
        cannot leak into subsequent turns.
        """
        state = self.read()
        if not state.get("effort_override_active"):
            return None
        result = {
            "level": state.get("effort_override_level"),
            "promote_deep": bool(state.get("effort_override_promote_deep")),
        }
        state["effort_override_active"] = False
        state["effort_override_level"] = None
        state["effort_override_promote_deep"] = False
        self._state = state
        self._write(state)
        if result["level"] not in ("low", "medium", "high", "xhigh"):
            return None
        return result

    def clear_effort_override(self) -> None:
        """Drop any pending effort override (without consuming)."""
        state = self.read()
        state["effort_override_active"] = False
        state["effort_override_level"] = None
        state["effort_override_promote_deep"] = False
        self._state = state
        self._write(state)

    def record_route(
        self,
        level: str,
        effort: str | None,
        method: str | None,
        language: str | None,
        savings: float = 0.0,
    ) -> None:
        """Increment per-session routing counters (v1.7 ADICIONAL #9).

        Tracks tier+effort granularity for deep (deep_medium / deep_high /
        deep_xhigh); fast and standard are counted by tier only. Method
        and language are accumulated as flat dicts. Total savings runs
        as a float sum.
        """
        state = self.read()
        if state.get("routing_started_at") is None:
            state["routing_started_at"] = time.time()

        counts = state.get("routing_counts") or {}
        # Normalise the dict in case the field arrived without all keys.
        for k in ("fast", "standard", "deep_medium", "deep_high", "deep_xhigh"):
            counts.setdefault(k, 0)

        if level == "deep":
            eff = effort if effort in ("medium", "high", "xhigh") else "medium"
            counts[f"deep_{eff}"] = counts.get(f"deep_{eff}", 0) + 1
        elif level in ("fast", "standard"):
            counts[level] = counts.get(level, 0) + 1
        # Unknown levels are silently dropped — never crash on routing record.
        state["routing_counts"] = counts

        if isinstance(method, str) and method:
            mc = state.get("routing_method_counts") or {}
            mc[method] = mc.get(method, 0) + 1
            state["routing_method_counts"] = mc

        if isinstance(language, str) and language:
            lc = state.get("routing_lang_counts") or {}
            lc[language] = lc.get(language, 0) + 1
            state["routing_lang_counts"] = lc

        try:
            state["routing_savings_total"] = round(
                float(state.get("routing_savings_total") or 0.0) + max(0.0, float(savings)),
                4,
            )
        except Exception:
            pass

        self._state = state
        self._write(state)

    def reset_routing_stats(self) -> None:
        """Reset session-scoped routing counters (manual /polyrouter:stats reset)."""
        state = self.read()
        state["routing_started_at"] = None
        state["routing_counts"] = {
            "fast": 0, "standard": 0,
            "deep_medium": 0, "deep_high": 0, "deep_xhigh": 0,
        }
        state["routing_method_counts"] = {}
        state["routing_lang_counts"] = {}
        state["routing_savings_total"] = 0.0
        state["retry_invocations"] = 0
        self._state = state
        self._write(state)

    def inc_retry_invocations(self) -> None:
        """Increment the retry-invocation counter (called by _detect_retry)."""
        state = self.read()
        state["retry_invocations"] = int(state.get("retry_invocations") or 0) + 1
        self._state = state
        self._write(state)

    def is_follow_up(self, query: str, compiled_patterns: list[re.Pattern]) -> bool:
        state = self.read()
        if state.get("last_route") is None:
            return False
        if not isinstance(query, str) or not query.strip():
            return False
        return any(p.search(query) for p in compiled_patterns)

    def get_confidence_boost(self) -> float:
        state = self.read()
        last = state.get("last_route")
        if last in ("standard", "deep"):
            return 0.1
        return 0.0

    def _write(self, data: dict) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass
