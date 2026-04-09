"""Microcompact + Session Memory compact advisory system.

Two cheap layers from Claude Code's compression architecture (zero API calls):

Layer 1 — MicroCompact:
  Tracks tool_result counts per session. When stale results exceed
  KEEP_LAST_N, emits an advisory recommendation to clear old results.
  Does NOT modify messages directly (polyrouter is a hook, not the runtime).

Layer 2 — Session Memory Compact:
  Monitors estimated token usage. When approaching limits, recommends
  using session memory as a lightweight summary instead of full LLM compact.

Circuit breaker: after MAX_CONSECUTIVE_FAILURES advisory attempts
that don't reduce context, stop recommending.
"""

import json
import time
from pathlib import Path

COMPACTABLE_TOOLS = frozenset({
    "Read", "Bash", "Grep", "Glob", "Edit", "Write", "WebSearch", "WebFetch",
})

KEEP_LAST_N = 5
MAX_CONSECUTIVE_FAILURES = 3

# Session memory compact thresholds
SM_MIN_TOKENS = 10_000
SM_MIN_MESSAGES = 5
SM_MAX_TOKENS = 40_000

COMPACT_STATE_FILE = Path.home() / ".claude" / "polyrouter-compact.json"


def _read_state() -> dict:
    """Read compact tracking state."""
    try:
        if COMPACT_STATE_FILE.exists():
            data = json.loads(COMPACT_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return _default_state()


def _write_state(data: dict) -> None:
    """Write compact state atomically."""
    try:
        COMPACT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = COMPACT_STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(COMPACT_STATE_FILE)
    except Exception:
        pass


def _default_state() -> dict:
    return {
        "tool_result_count": 0,
        "compactable_count": 0,
        "compact_attempts": 0,
        "compact_successes": 0,
        "consecutive_failures": 0,
        "breaker_tripped": False,
        "last_compact_time": None,
        "last_token_estimate": 0,
        "last_message_count": 0,
    }


class MicroCompact:
    """Advisory: detect stale tool results and recommend clearing."""

    def __init__(self, keep_last_n: int = KEEP_LAST_N):
        self._keep_last_n = max(1, keep_last_n)

    def check(self, state: dict) -> str | None:
        """Check if microcompact advisory should be emitted.

        Returns advisory message or None.
        """
        compactable = state.get("compactable_count", 0)
        stale = compactable - self._keep_last_n

        if stale <= 0:
            return None

        return (
            f"[polyrouter:compact] Recommend clearing {stale} old tool results "
            f"({compactable} total, keeping last {self._keep_last_n})"
        )

    @staticmethod
    def record_tool_use(state: dict, tool_name: str) -> dict:
        """Record a tool use, tracking compactable tools separately."""
        state["tool_result_count"] = state.get("tool_result_count", 0) + 1
        if tool_name in COMPACTABLE_TOOLS:
            state["compactable_count"] = state.get("compactable_count", 0) + 1
        return state


class SessionMemoryCompact:
    """Advisory: recommend session memory compact when tokens are high."""

    def __init__(
        self,
        min_tokens: int = SM_MIN_TOKENS,
        min_messages: int = SM_MIN_MESSAGES,
        max_tokens: int = SM_MAX_TOKENS,
    ):
        self._min_tokens = min_tokens
        self._min_messages = min_messages
        self._max_tokens = max_tokens

    def check(self, state: dict) -> str | None:
        """Check if session memory compact should be recommended.

        Returns advisory message or None.
        """
        token_est = state.get("last_token_estimate", 0)
        msg_count = state.get("last_message_count", 0)

        if token_est < self._min_tokens:
            return None
        if msg_count < self._min_messages:
            return None

        return (
            f"[polyrouter:compact] Session approaching context limits "
            f"(~{token_est} tokens, {msg_count} messages). "
            f"Recommend /compact or session memory summary."
        )


class CompactAdvisor:
    """Orchestrates microcompact and session memory checks with circuit breaker."""

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        compact_cfg = cfg.get("compact", {})

        self._micro = MicroCompact(
            keep_last_n=compact_cfg.get("keep_last_n", KEEP_LAST_N),
        )
        self._sm = SessionMemoryCompact(
            min_tokens=compact_cfg.get("sm_min_tokens", SM_MIN_TOKENS),
            min_messages=compact_cfg.get("sm_min_messages", SM_MIN_MESSAGES),
            max_tokens=compact_cfg.get("sm_max_tokens", SM_MAX_TOKENS),
        )
        self._max_failures = compact_cfg.get(
            "circuit_breaker_max", MAX_CONSECUTIVE_FAILURES,
        )
        self._enabled = compact_cfg.get("enabled", True)

    def get_advisory(self, state: dict) -> str | None:
        """Run both checks and return advisory if warranted.

        Returns None if circuit breaker is tripped or no advisory needed.
        """
        if not self._enabled:
            return None

        if state.get("breaker_tripped", False):
            return None

        if state.get("consecutive_failures", 0) >= self._max_failures:
            state["breaker_tripped"] = True
            return None

        # Try microcompact first (cheaper)
        advisory = self._micro.check(state)
        if advisory:
            return advisory

        # Then session memory check
        return self._sm.check(state)

    def record_attempt(self, state: dict, success: bool) -> dict:
        """Record a compact advisory outcome for circuit breaker tracking."""
        state["compact_attempts"] = state.get("compact_attempts", 0) + 1

        if success:
            state["compact_successes"] = state.get("compact_successes", 0) + 1
            state["consecutive_failures"] = 0
            state["last_compact_time"] = time.time()
        else:
            state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
            if state["consecutive_failures"] >= self._max_failures:
                state["breaker_tripped"] = True

        return state

    def record_tool_use(self, state: dict, tool_name: str) -> dict:
        """Delegate tool recording to microcompact."""
        return self._micro.record_tool_use(state, tool_name)


def load_compact_state() -> dict:
    """Load compact tracking state from disk."""
    return _read_state()


def save_compact_state(state: dict) -> None:
    """Persist compact tracking state to disk."""
    _write_state(state)
