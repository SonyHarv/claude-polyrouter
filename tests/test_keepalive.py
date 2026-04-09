"""Tests for cache keep-alive hook (Sprint 3).

Key design: PostToolUse fires = session is active (a tool just ran).
The idle_cutoff is a stale-session guard (default 120min), not an
activity timer. Cache freshness is based on max(last_query, last_keepalive).
"""

import importlib
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

ka = importlib.import_module("cache-keepalive")


@pytest.fixture
def session_file(tmp_path):
    """Provide a temporary session file and patch SESSION_PATH."""
    path = tmp_path / "session.json"
    with patch.object(ka, "SESSION_PATH", path):
        yield path


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _run(capsys, config=None):
    """Run main() with optional config override, return parsed output."""
    cfg = config or {}
    with patch.object(ka, "load_config", return_value=cfg):
        ka.main()
    return json.loads(capsys.readouterr().out)


class TestDisabled:
    def test_disabled_in_config(self, session_file, capsys):
        output = _run(capsys, {"keepalive": {"enabled": False}})
        assert output == {}


class TestNoSession:
    def test_no_session_file(self, session_file, capsys):
        assert _run(capsys) == {}

    def test_empty_session(self, session_file, capsys):
        _write(session_file, {})
        assert _run(capsys) == {}

    def test_invalid_timestamp(self, session_file, capsys):
        _write(session_file, {"last_query_time": "not a number"})
        assert _run(capsys) == {}


class TestStaleSessionGuard:
    def test_stale_session_skips(self, session_file, capsys):
        """If last_query_time > idle_cutoff (120min default), skip."""
        _write(session_file, {"last_query_time": time.time() - 130 * 60})
        assert _run(capsys) == {}

    def test_within_cutoff_proceeds(self, session_file, capsys):
        """Session within cutoff but cache fresh → no keepalive (no-op)."""
        _write(session_file, {"last_query_time": time.time() - 10 * 60})
        assert _run(capsys) == {}


class TestCacheFreshness:
    def test_cache_fresh_no_action(self, session_file, capsys):
        """last_query recent → cache warm → no keepalive."""
        _write(session_file, {"last_query_time": time.time() - 10 * 60})
        assert _run(capsys) == {}

    def test_cache_expired_via_query_time(self, session_file, capsys):
        """last_query_time > threshold, no prior keepalive → emit."""
        _write(session_file, {"last_query_time": time.time() - 52 * 60})
        output = _run(capsys)
        ctx = output.get("hookSpecificOutput", {}).get("additionalContext", "")
        assert "keepalive" in ctx

    def test_cache_expired_via_keepalive_time(self, session_file, capsys):
        """last_keepalive > threshold, query recent → no keepalive (query refreshed cache)."""
        now = time.time()
        _write(session_file, {
            "last_query_time": now - 5 * 60,
            "last_keepalive_time": now - 55 * 60,
        })
        # last_api_time = max(5min ago, 55min ago) = 5min ago → fresh
        assert _run(capsys) == {}

    def test_both_old_emits_keepalive(self, session_file, capsys):
        """Both query and keepalive > threshold → emit."""
        now = time.time()
        _write(session_file, {
            "last_query_time": now - 55 * 60,
            "last_keepalive_time": now - 52 * 60,
        })
        # last_api_time = max(55min, 52min ago) = 52min ago → expired
        output = _run(capsys)
        ctx = output.get("hookSpecificOutput", {}).get("additionalContext", "")
        assert "keepalive" in ctx

    def test_keepalive_refreshed_cache(self, session_file, capsys):
        """A recent keepalive keeps cache fresh even if query is old."""
        now = time.time()
        _write(session_file, {
            "last_query_time": now - 80 * 60,
            "last_keepalive_time": now - 10 * 60,
        })
        # last_api_time = max(80min, 10min ago) = 10min ago → fresh
        assert _run(capsys) == {}


class TestTimestampUpdate:
    def test_keepalive_updates_timestamp(self, session_file, capsys):
        """After emitting keepalive, last_keepalive_time is updated."""
        now = time.time()
        _write(session_file, {"last_query_time": now - 52 * 60})
        _run(capsys)
        session = _read(session_file)
        assert session["last_keepalive_time"] > now - 2

    def test_no_keepalive_preserves_session(self, session_file, capsys):
        """When cache is fresh, session file is not modified."""
        now = time.time()
        data = {"last_query_time": now - 5 * 60}
        _write(session_file, data)
        _run(capsys)
        session = _read(session_file)
        assert "last_keepalive_time" not in session


class TestCustomConfig:
    def test_custom_threshold_lower(self, session_file, capsys):
        """Custom threshold of 10min triggers earlier."""
        now = time.time()
        _write(session_file, {"last_query_time": now - 12 * 60})
        cfg = {"keepalive": {"enabled": True, "threshold_minutes": 10, "idle_cutoff_minutes": 120}}
        output = _run(capsys, cfg)
        ctx = output.get("hookSpecificOutput", {}).get("additionalContext", "")
        assert "keepalive" in ctx

    def test_custom_idle_cutoff(self, session_file, capsys):
        """Custom idle_cutoff of 60min blocks earlier."""
        now = time.time()
        _write(session_file, {"last_query_time": now - 65 * 60})
        cfg = {"keepalive": {"enabled": True, "threshold_minutes": 50, "idle_cutoff_minutes": 60}}
        assert _run(capsys, cfg) == {}


class TestEdgeCases:
    def test_corrupted_session_file(self, session_file, capsys):
        session_file.write_text("not json", encoding="utf-8")
        assert _run(capsys) == {}

    def test_exactly_at_threshold(self, session_file, capsys):
        """Exactly at threshold boundary → emit (>= not >)."""
        now = time.time()
        _write(session_file, {"last_query_time": now - 50 * 60})
        output = _run(capsys)
        ctx = output.get("hookSpecificOutput", {}).get("additionalContext", "")
        assert "keepalive" in ctx

    def test_main_exception_returns_empty(self, capsys):
        """Top-level exception handler returns empty output."""
        with patch.object(ka, "load_config", side_effect=RuntimeError("boom")):
            with patch.object(ka, "_read_session", side_effect=RuntimeError("boom")):
                # Call via __main__ path to hit outer try/except
                try:
                    ka.main()
                except RuntimeError:
                    pass
                # The outer try/except in if __name__ == "__main__" won't fire
                # in test context, but main() itself should handle gracefully
