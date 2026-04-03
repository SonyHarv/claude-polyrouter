import json
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.cache import Cache, fingerprint


class TestFingerprint:
    def test_same_query_same_fingerprint(self):
        assert fingerprint("hello world") == fingerprint("hello world")

    def test_case_insensitive(self):
        assert fingerprint("Hello World") == fingerprint("hello world")

    def test_order_independent(self):
        assert fingerprint("hello world") == fingerprint("world hello")

    def test_strips_punctuation(self):
        assert fingerprint("hello, world!") == fingerprint("hello world")

    def test_different_queries_different_fingerprints(self):
        assert fingerprint("hello world") != fingerprint("goodbye world")

    def test_empty_string(self):
        fp = fingerprint("")
        assert isinstance(fp, str) and len(fp) == 32


class TestCacheL1:
    def test_miss_returns_none(self):
        cache = Cache(memory_size=10, file_size=0, ttl_days=30, cache_file=None)
        assert cache.get("nonexistent") is None

    def test_set_and_get(self):
        cache = Cache(memory_size=10, file_size=0, ttl_days=30, cache_file=None)
        cache.set("key1", {"level": "fast", "confidence": 0.9})
        result = cache.get("key1")
        assert result["level"] == "fast"

    def test_lru_eviction(self):
        cache = Cache(memory_size=2, file_size=0, ttl_days=30, cache_file=None)
        cache.set("key1", {"level": "fast"})
        cache.set("key2", {"level": "standard"})
        cache.set("key3", {"level": "deep"})
        assert cache.get("key1") is None
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None

    def test_invalid_key_returns_none(self):
        cache = Cache(memory_size=10, file_size=0, ttl_days=30, cache_file=None)
        assert cache.get("") is None
        assert cache.get(None) is None

    def test_invalid_value_ignored(self):
        cache = Cache(memory_size=10, file_size=0, ttl_days=30, cache_file=None)
        cache.set("key1", "not a dict")
        assert cache.get("key1") is None


class TestCacheL2:
    def test_persists_to_file(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            cache_file = Path(f.name)
        try:
            cache = Cache(memory_size=10, file_size=10, ttl_days=30, cache_file=cache_file)
            cache.set("key1", {"level": "fast", "confidence": 0.9})
            cache.flush()
            cache2 = Cache(memory_size=10, file_size=10, ttl_days=30, cache_file=cache_file)
            result = cache2.get("key1")
            assert result is not None
            assert result["level"] == "fast"
        finally:
            cache_file.unlink(missing_ok=True)

    def test_file_cache_eviction(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            cache_file = Path(f.name)
        try:
            cache = Cache(memory_size=10, file_size=2, ttl_days=30, cache_file=cache_file)
            cache.set("key1", {"level": "fast"})
            cache.set("key2", {"level": "standard"})
            cache.set("key3", {"level": "deep"})
            cache.flush()
            data = json.loads(cache_file.read_text())
            assert len(data["entries"]) <= 2
        finally:
            cache_file.unlink(missing_ok=True)

    def test_corrupted_file_handled_gracefully(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("NOT VALID JSON")
            cache_file = Path(f.name)
        try:
            cache = Cache(memory_size=10, file_size=10, ttl_days=30, cache_file=cache_file)
            assert cache.get("anything") is None
        finally:
            cache_file.unlink(missing_ok=True)
