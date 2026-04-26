"""Multi-turn session state management."""

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
            self._state = {**DEFAULT_SESSION}
            return self._state
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                self._state = {**DEFAULT_SESSION}
                return self._state
            last_time = data.get("last_query_time")
            if last_time and isinstance(last_time, (int, float)) and (time.time() - last_time) > self._timeout_seconds:
                self._state = {**DEFAULT_SESSION}
                return self._state
            self._state = data
            return self._state
        except Exception:
            self._state = {**DEFAULT_SESSION}
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
