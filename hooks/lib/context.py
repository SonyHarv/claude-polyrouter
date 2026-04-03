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

    def update(self, level: str, language: str | None) -> None:
        state = self.read()
        state["last_route"] = level
        state["last_level"] = level
        state["conversation_depth"] = state.get("conversation_depth", 0) + 1
        state["last_query_time"] = time.time()
        if language and isinstance(language, str):
            state["last_language"] = language
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
