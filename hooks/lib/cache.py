"""Two-level cache: in-memory LRU (L1) + file-based persistent (L2)."""

import hashlib
import json
import re
import time
from collections import OrderedDict
from pathlib import Path

_PLUGIN_JSON = Path(__file__).resolve().parents[2] / "plugin.json"


def _read_plugin_version() -> str:
    """Read current plugin version from plugin.json."""
    try:
        data = json.loads(_PLUGIN_JSON.read_text(encoding="utf-8"))
        return data.get("version", "unknown")
    except Exception:
        return "unknown"


def fingerprint(query: str) -> str:
    """Generate order-independent MD5 fingerprint of normalized query."""
    normalized = re.sub(r"[^\w\s]", "", query.lower())
    words = sorted(normalized.split())
    return hashlib.md5(" ".join(words).encode()).hexdigest()


class Cache:
    """Two-level cache with in-memory LRU (L1) and file-based (L2)."""

    def __init__(
        self,
        memory_size: int,
        file_size: int,
        ttl_days: int,
        cache_file: Path | None,
    ):
        self._memory_size = max(1, memory_size)
        self._file_size = max(0, file_size)
        self._ttl_seconds = max(0, ttl_days) * 86400
        self._cache_file = cache_file
        self._l1: OrderedDict[str, dict] = OrderedDict()
        self._l2: OrderedDict[str, dict] = OrderedDict()
        self._l2_dirty = False

        if cache_file:
            self._load_l2()
            self._check_version()

    def get(self, key: str) -> dict | None:
        """Look up a cached route by fingerprint key. L1 first, then L2."""
        if not isinstance(key, str) or not key:
            return None

        # L1 check
        if key in self._l1:
            self._l1.move_to_end(key)
            return self._l1[key]

        # L2 check
        if key in self._l2:
            entry = self._l2[key]
            if time.time() - entry.get("_cached_at", 0) > self._ttl_seconds:
                del self._l2[key]
                self._l2_dirty = True
                return None
            self._l1[key] = entry
            self._evict_l1()
            return entry

        return None

    def set(self, key: str, value: dict) -> None:
        """Store a route in both L1 and L2."""
        if not isinstance(key, str) or not key:
            return
        if not isinstance(value, dict):
            return

        entry = {**value, "_cached_at": time.time()}

        self._l1[key] = entry
        self._evict_l1()

        if self._cache_file is not None:
            self._l2[key] = entry
            self._evict_l2()
            self._l2_dirty = True

    def flush(self) -> None:
        """Write L2 cache to disk if dirty."""
        if not self._l2_dirty or not self._cache_file:
            return
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "plugin_version": _read_plugin_version(),
                "version": "1.0",
                "entries": {k: v for k, v in self._l2.items()},
            }
            tmp_path = self._cache_file.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data), encoding="utf-8")
            tmp_path.replace(self._cache_file)
            self._l2_dirty = False
        except Exception:
            pass

    def _check_version(self) -> None:
        """Invalidate L2 cache if plugin version changed."""
        if not self._cache_file or not self._cache_file.exists():
            return
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            cached_version = data.get("plugin_version", "")
            current_version = _read_plugin_version()
            if cached_version != current_version:
                self._l2.clear()
                self._l2_dirty = True
                self.flush()
        except Exception:
            pass

    def _load_l2(self) -> None:
        """Load L2 cache from disk."""
        if not self._cache_file or not self._cache_file.exists():
            return
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            entries = data.get("entries", {})
            if not isinstance(entries, dict):
                return
            now = time.time()
            for key, entry in entries.items():
                if isinstance(entry, dict) and now - entry.get("_cached_at", 0) <= self._ttl_seconds:
                    self._l2[key] = entry
        except Exception:
            self._l2 = OrderedDict()

    def _evict_l1(self) -> None:
        while len(self._l1) > self._memory_size:
            self._l1.popitem(last=False)

    def _evict_l2(self) -> None:
        while len(self._l2) > self._file_size:
            self._l2.popitem(last=False)
