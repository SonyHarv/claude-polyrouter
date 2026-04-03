"""Atomic statistics logging with file locking."""

import json
import platform
import tempfile
from datetime import date, datetime
from pathlib import Path

DEFAULT_STATS = {
    "version": "1.0",
    "total_queries": 0,
    "routes": {"fast": 0, "standard": 0, "deep": 0},
    "cache_hits": 0,
    "languages_detected": {},
    "estimated_savings": 0.0,
    "sessions": [],
    "last_updated": None,
}


def _lock_file(f):
    """Cross-platform file locking."""
    try:
        if platform.system() == "Windows":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        pass


def _unlock_file(f):
    """Cross-platform file unlocking."""
    try:
        if platform.system() == "Windows":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass


class Stats:
    def __init__(self, path: Path):
        self._path = path

    def read(self) -> dict:
        if not self._path.exists():
            return {**DEFAULT_STATS, "routes": {**DEFAULT_STATS["routes"]}, "languages_detected": {}, "sessions": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {**DEFAULT_STATS, "routes": {**DEFAULT_STATS["routes"]}, "languages_detected": {}, "sessions": []}
            for key, default in DEFAULT_STATS.items():
                if key not in data:
                    data[key] = default if not isinstance(default, (dict, list)) else type(default)(default)
            return data
        except Exception:
            return {**DEFAULT_STATS, "routes": {**DEFAULT_STATS["routes"]}, "languages_detected": {}, "sessions": []}

    def record(self, level: str, language: str | None, cache_hit: bool, savings: float) -> None:
        if not isinstance(level, str):
            return
        data = self.read()
        data["total_queries"] += 1
        data["routes"][level] = data["routes"].get(level, 0) + 1
        if cache_hit:
            data["cache_hits"] += 1
        if language and isinstance(language, str):
            data["languages_detected"][language] = data["languages_detected"].get(language, 0) + 1
        data["estimated_savings"] = round(data["estimated_savings"] + max(0.0, float(savings)), 4)
        data["last_updated"] = datetime.now().isoformat()

        today = date.today().isoformat()
        session = next((s for s in data["sessions"] if s["date"] == today), None)
        if session is None:
            session = {"date": today, "queries": 0, "routes": {"fast": 0, "standard": 0, "deep": 0}, "cache_hits": 0, "savings": 0.0}
            data["sessions"].append(session)
        session["queries"] += 1
        session["routes"][level] = session["routes"].get(level, 0) + 1
        if cache_hit:
            session["cache_hits"] += 1
        session["savings"] = round(session["savings"] + max(0.0, float(savings)), 4)
        data["sessions"] = data["sessions"][-30:]
        self._write(data)

    def _write(self, data: dict) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_fd, tmp_path = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
            try:
                with open(tmp_fd, "w", encoding="utf-8") as f:
                    _lock_file(f)
                    json.dump(data, f, indent=2)
                    _unlock_file(f)
                Path(tmp_path).replace(self._path)
            except Exception:
                Path(tmp_path).unlink(missing_ok=True)
                raise
        except Exception:
            pass
