"""Tests for session_name passthrough + /clear cycle (CALIDAD #17).

Covers:
  - Stats.record() persists per-session_name accumulation
  - SessionState.update_session_name() persists / coerces correctly
  - /clear cycle: two stdin payloads with the same session_name produce
    cumulative stats (the second turn does NOT reset because session_name
    survives the /clear in CC v2.1.120+)
  - Truncation helper produces 20-char + ellipsis output
  - Display section appears in [POLY:STATS] block
  - Absent session_name silently no-ops everywhere
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import DEFAULT_SESSION, SessionState
from lib.stats import DEFAULT_STATS, Stats


# --- Helpers ---


def _classify_module():
    """Lazy-load classify-prompt.py as a module (sibling 'lib' on path)."""
    spec = importlib.util.spec_from_file_location(
        "classify_prompt",
        Path(__file__).parent.parent / "hooks" / "classify-prompt.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def stats_path(tmp_path):
    return tmp_path / "polyrouter-stats.json"


@pytest.fixture
def session_path(tmp_path):
    return tmp_path / "polyrouter-session.json"


# --- Stats.record persistence ---


class TestStatsBySessionName:
    def test_default_stats_has_by_session_name_key(self):
        assert "by_session_name" in DEFAULT_STATS
        assert DEFAULT_STATS["by_session_name"] == {}

    def test_record_with_session_name_creates_entry(self, stats_path):
        stats = Stats(stats_path)
        stats.record("fast", "en", False, 0.05, session_name="feature-auth")
        data = stats.read()
        assert "feature-auth" in data["by_session_name"]
        entry = data["by_session_name"]["feature-auth"]
        assert entry["queries"] == 1
        assert entry["routes"]["fast"] == 1
        assert entry["savings"] == 0.05

    def test_record_accumulates_across_calls(self, stats_path):
        stats = Stats(stats_path)
        stats.record("fast", "en", False, 0.05, session_name="feature-auth")
        stats.record("deep", "en", False, 0.20, session_name="feature-auth")
        stats.record("standard", "es", False, 0.10, session_name="other-session")
        data = stats.read()
        auth = data["by_session_name"]["feature-auth"]
        assert auth["queries"] == 2
        assert auth["routes"]["fast"] == 1
        assert auth["routes"]["deep"] == 1
        assert auth["savings"] == 0.25
        other = data["by_session_name"]["other-session"]
        assert other["queries"] == 1
        assert other["routes"]["standard"] == 1

    def test_record_without_session_name_no_op(self, stats_path):
        stats = Stats(stats_path)
        stats.record("fast", "en", False, 0.05)  # no session_name kwarg
        data = stats.read()
        assert data["by_session_name"] == {}

    def test_record_with_empty_session_name_no_op(self, stats_path):
        stats = Stats(stats_path)
        stats.record("fast", "en", False, 0.05, session_name="")
        stats.record("fast", "en", False, 0.05, session_name=None)
        data = stats.read()
        assert data["by_session_name"] == {}

    def test_record_with_non_string_session_name_no_op(self, stats_path):
        stats = Stats(stats_path)
        stats.record("fast", "en", False, 0.05, session_name=12345)
        stats.record("fast", "en", False, 0.05, session_name=["x"])
        data = stats.read()
        assert data["by_session_name"] == {}

    def test_existing_stats_file_back_compat(self, stats_path):
        # Stats files written before CALIDAD #17 lack the by_session_name key.
        # Read should backfill to {} without crashing.
        stats_path.write_text(json.dumps({
            "version": "1.0",
            "total_queries": 5,
            "routes": {"fast": 5, "standard": 0, "deep": 0},
            "cache_hits": 0,
            "languages_detected": {"en": 5},
            "estimated_savings": 0.25,
            "sessions": [],
            "last_updated": "2026-04-25T12:00:00",
        }))
        stats = Stats(stats_path)
        data = stats.read()
        assert data["by_session_name"] == {}
        # Recording into the legacy file should now populate the key.
        stats.record("fast", "en", False, 0.05, session_name="legacy")
        data = stats.read()
        assert data["by_session_name"]["legacy"]["queries"] == 1


# --- SessionState.update_session_name ---


class TestSessionStateName:
    def test_default_session_has_session_name_key(self):
        assert "session_name" in DEFAULT_SESSION
        assert DEFAULT_SESSION["session_name"] is None

    def test_update_session_name_persists(self, session_path):
        s = SessionState(session_path, timeout_minutes=30)
        s.update_session_name("feature-auth")
        assert s.read()["session_name"] == "feature-auth"
        # Survives a fresh read
        s2 = SessionState(session_path, timeout_minutes=30)
        assert s2.read()["session_name"] == "feature-auth"

    def test_update_with_empty_string_no_op(self, session_path):
        s = SessionState(session_path, timeout_minutes=30)
        s.update_session_name("first")
        s.update_session_name("")
        assert s.read()["session_name"] == "first"

    def test_update_with_none_no_op(self, session_path):
        s = SessionState(session_path, timeout_minutes=30)
        s.update_session_name("first")
        s.update_session_name(None)
        assert s.read()["session_name"] == "first"

    def test_update_with_non_string_no_op(self, session_path):
        s = SessionState(session_path, timeout_minutes=30)
        s.update_session_name(42)
        assert s.read()["session_name"] is None


# --- Truncation helper ---


class TestTruncation:
    def test_short_name_unchanged(self):
        mod = _classify_module()
        assert mod._truncate_session_name("short") == "short"
        assert mod._truncate_session_name("a" * 20) == "a" * 20  # exactly 20

    def test_long_name_truncates_to_20_with_ellipsis(self):
        mod = _classify_module()
        result = mod._truncate_session_name("feature-auth-jwt-refresh-rotation")
        assert len(result) == 20
        assert result.endswith("…")
        assert result == "feature-auth-jwt-re" + "…"

    def test_custom_limit(self):
        mod = _classify_module()
        result = mod._truncate_session_name("hello-world", limit=8)
        assert result == "hello-w…"
        assert len(result) == 8

    def test_non_string_returns_empty(self):
        mod = _classify_module()
        assert mod._truncate_session_name(None) == ""
        assert mod._truncate_session_name(123) == ""

    def test_zero_limit_returns_empty(self):
        mod = _classify_module()
        assert mod._truncate_session_name("anything", limit=0) == ""


# --- /clear cycle simulation ---


class TestClearCycle:
    """Simulate two stdin payloads with the same session_name across /clear.

    CC v2.1.120+ preserves session_name across /clear. Poly's stats
    file lives outside CC's session state, so it should accumulate
    routes across both turns into the same `by_session_name[name]` entry
    even when SessionState (the in-memory polyrouter session) gets
    timed out / reset between the two turns.
    """

    def test_two_turns_same_name_accumulate(self, stats_path, session_path):
        # Turn 1
        stats = Stats(stats_path)
        s1 = SessionState(session_path, timeout_minutes=30)
        s1.update_session_name("feature-jwt")
        stats.record("fast", "en", False, 0.05, session_name="feature-jwt")

        # Simulate /clear: brand-new SessionState instance with the same
        # underlying file. CC's session_name comes back via stdin and is
        # written into the (possibly fresh) session.
        s2 = SessionState(session_path, timeout_minutes=30)
        s2.update_session_name("feature-jwt")
        stats.record("deep", "en", False, 0.20, session_name="feature-jwt")

        data = stats.read()
        entry = data["by_session_name"]["feature-jwt"]
        assert entry["queries"] == 2
        assert entry["routes"]["fast"] == 1
        assert entry["routes"]["deep"] == 1

    def test_clear_with_different_session_name_creates_new_bucket(
        self, stats_path, session_path,
    ):
        stats = Stats(stats_path)
        SessionState(session_path).update_session_name("feature-a")
        stats.record("fast", "en", False, 0.05, session_name="feature-a")

        # User invokes /clear AND switches to a different named session.
        SessionState(session_path).update_session_name("feature-b")
        stats.record("deep", "en", False, 0.20, session_name="feature-b")

        data = stats.read()
        assert data["by_session_name"]["feature-a"]["queries"] == 1
        assert data["by_session_name"]["feature-b"]["queries"] == 1


# --- Stats block rendering includes by-session section ---


class TestStatsBlockRendering:
    def test_block_includes_by_session_section_when_data_present(
        self, stats_path, session_path, monkeypatch,
    ):
        # Seed both stats and session with at least one named-session entry.
        Stats(stats_path).record("fast", "en", False, 0.05, session_name="feat-jwt")
        s = SessionState(session_path)
        s.update_session_name("feat-jwt")
        s.record_route("fast", "low", "scoring", "en", 0.05)

        mod = _classify_module()
        # Point STATS_PATH inside the module to our temp file so the
        # block reader picks up the seeded data.
        monkeypatch.setattr(mod, "STATS_PATH", stats_path)
        block = mod._build_stats_block(s, config={"tokenizer_factor": 1.35})

        assert "By session:" in block
        assert "feat-jwt" in block
        assert "1 routes" in block

    def test_block_omits_section_when_no_named_sessions(
        self, stats_path, session_path, monkeypatch,
    ):
        # Routes recorded but without session_name → by_session_name stays {}
        Stats(stats_path).record("fast", "en", False, 0.05)
        s = SessionState(session_path)
        s.record_route("fast", "low", "scoring", "en", 0.05)

        mod = _classify_module()
        monkeypatch.setattr(mod, "STATS_PATH", stats_path)
        block = mod._build_stats_block(s, config={"tokenizer_factor": 1.35})

        assert "By session:" not in block

    def test_block_truncates_long_names_in_display(
        self, stats_path, session_path, monkeypatch,
    ):
        long_name = "feature-auth-jwt-refresh-rotation"
        Stats(stats_path).record("fast", "en", False, 0.05, session_name=long_name)
        s = SessionState(session_path)
        s.update_session_name(long_name)
        s.record_route("fast", "low", "scoring", "en", 0.05)

        mod = _classify_module()
        monkeypatch.setattr(mod, "STATS_PATH", stats_path)
        block = mod._build_stats_block(s, config={"tokenizer_factor": 1.35})

        # Full name must NOT appear; truncated version with ellipsis must.
        assert long_name not in block
        assert "feature-auth-jwt-re…" in block

    def test_block_caps_at_top_n_named_sessions(
        self, stats_path, session_path, monkeypatch,
    ):
        stats = Stats(stats_path)
        # 7 distinct named sessions, varying counts so sort is meaningful.
        for i, n in enumerate([10, 8, 6, 4, 3, 2, 1]):
            for _ in range(n):
                stats.record("fast", "en", False, 0.01, session_name=f"sess-{i}")
        s = SessionState(session_path)
        s.record_route("fast", "low", "scoring", "en", 0.01)

        mod = _classify_module()
        monkeypatch.setattr(mod, "STATS_PATH", stats_path)
        block = mod._build_stats_block(s, config={"tokenizer_factor": 1.35})

        # Top 5 by query count → sess-0..sess-4 included, sess-5/sess-6 not.
        assert "sess-0" in block
        assert "sess-4" in block
        assert "sess-5" not in block
        assert "sess-6" not in block


# --- Hook end-to-end (stdin path) ---


class TestHookStdinSessionName:
    def test_hook_main_persists_session_name_from_stdin(
        self, stats_path, session_path, monkeypatch, capsys,
    ):
        mod = _classify_module()
        monkeypatch.setattr(mod, "STATS_PATH", stats_path)
        monkeypatch.setattr(mod, "SESSION_PATH", session_path)

        payload = {
            "prompt": "fix the bug",
            "session_name": "feature-jwt",
            "session_id": "test-sess-id",
            "cwd": "/tmp",
        }
        monkeypatch.setattr("sys.stdin", _StdinStub(json.dumps(payload)))

        mod.main()

        # Session state must carry the name.
        sess = SessionState(session_path).read()
        assert sess["session_name"] == "feature-jwt"

        # Stats must have a per-name bucket.
        st = Stats(stats_path).read()
        assert "feature-jwt" in st["by_session_name"]
        assert st["by_session_name"]["feature-jwt"]["queries"] >= 1

    def test_hook_main_silent_when_session_name_absent(
        self, stats_path, session_path, monkeypatch,
    ):
        mod = _classify_module()
        monkeypatch.setattr(mod, "STATS_PATH", stats_path)
        monkeypatch.setattr(mod, "SESSION_PATH", session_path)

        payload = {"prompt": "fix the bug", "cwd": "/tmp"}
        monkeypatch.setattr("sys.stdin", _StdinStub(json.dumps(payload)))

        mod.main()

        sess = SessionState(session_path).read()
        assert sess["session_name"] is None

        st = Stats(stats_path).read()
        assert st["by_session_name"] == {}


class _StdinStub:
    def __init__(self, content: str):
        self._content = content

    def read(self) -> str:
        return self._content
