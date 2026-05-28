"""Tests for v1.9.4 intelligent slash-command routing.

Covers:
  - /spec → forced to deep (with or without context)
  - /work → never fast, uses active spec, falls back to standard with warning
  - /commit-push-pr → always standard
  - Other slash commands with context → continue to scoring
  - Bare slash commands → skip
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import DEFAULT_SESSION, SessionState  # noqa: E402


def _classify_module():
    spec = importlib.util.spec_from_file_location(
        "classify_prompt",
        Path(__file__).parent.parent / "hooks" / "classify-prompt.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _StdinStub:
    def __init__(self, content: str):
        self._content = content

    def read(self) -> str:
        return self._content


@pytest.fixture
def session_path(tmp_path):
    return tmp_path / "polyrouter-session.json"


@pytest.fixture
def stats_path(tmp_path):
    return tmp_path / "polyrouter-stats.json"


@pytest.fixture
def cache_path(tmp_path):
    return tmp_path / "polyrouter-cache.json"


def _run_hook(
    prompt: str, monkeypatch, session_path, stats_path, cache_path, capsys,
) -> dict:
    mod = _classify_module()
    monkeypatch.setattr(mod, "SESSION_PATH", session_path)
    monkeypatch.setattr(mod, "STATS_PATH", stats_path)
    monkeypatch.setattr(mod, "CACHE_PATH", cache_path)
    payload = {"prompt": prompt, "cwd": "/tmp"}
    monkeypatch.setattr("sys.stdin", _StdinStub(json.dumps(payload)))
    mod.main()
    out = capsys.readouterr().out
    return json.loads(out)


def _ctx(output: dict) -> str:
    return output["hookSpecificOutput"]["additionalContext"]


# --- /spec ---

class TestSpecCommand:
    def test_spec_routes_to_deep(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        """/spec alone (no context) → deep/opus."""
        out = _run_hook(
            "/spec", monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        ctx = _ctx(out)
        assert "Route: deep" in ctx
        assert "Model: opus" in ctx

    def test_spec_with_context_routes_to_deep(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        """/spec implementa login con JWT → deep/opus."""
        out = _run_hook(
            "/spec implementa login con JWT",
            monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        ctx = _ctx(out)
        assert "Route: deep" in ctx
        assert "Model: opus" in ctx

    def test_spec_persists_active_spec(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        """/spec X must save the spec content so /work can pick it up."""
        _run_hook(
            "/spec implementa login con JWT",
            monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        saved = SessionState(session_path).get_active_spec()
        assert saved is not None
        assert "implementa login" in saved


# --- /work ---

class TestWorkCommand:
    def test_work_with_active_spec_complex(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        """/work with complex spec → deep/opus."""
        sess = SessionState(session_path)
        sess.set_active_spec(
            "diseña la arquitectura de un sistema distribuido "
            "escalable con microservicios y refactor mayor"
        )
        out = _run_hook(
            "/work", monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        ctx = _ctx(out)
        assert "Route: deep" in ctx

    def test_work_with_active_spec_simple(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        """/work with simple spec → standard/sonnet (never fast)."""
        sess = SessionState(session_path)
        sess.set_active_spec("rename a variable in one file")
        out = _run_hook(
            "/work", monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        ctx = _ctx(out)
        # never fast (floor enforced), can be standard or deep
        assert "Route: fast" not in ctx
        assert "Route: standard" in ctx or "Route: deep" in ctx

    def test_work_without_spec_routes_standard(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        """/work alone with no spec → standard with warning advisor block."""
        out = _run_hook(
            "/work", monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        ctx = _ctx(out)
        assert "Route: standard" in ctx
        assert "No hay spec activo" in ctx

    def test_work_never_haiku(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        """/work must never resolve to fast/haiku, even on trivial input."""
        sess = SessionState(session_path)
        sess.set_active_spec("hi")
        out = _run_hook(
            "/work", monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        ctx = _ctx(out)
        assert "Route: fast" not in ctx
        assert "Model: haiku" not in ctx


# --- /commit-push-pr ---

class TestCommitCommand:
    def test_commit_routes_standard(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        """/commit-push-pr → standard/sonnet."""
        out = _run_hook(
            "/commit-push-pr",
            monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        ctx = _ctx(out)
        assert "Route: standard" in ctx or "Route: deep" in ctx
        assert "Route: fast" not in ctx


# --- generic slash behavior ---

class TestGenericSlash:
    def test_slash_with_context_not_skipped(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        """/random-cmd <context> → analyses the context, not skipped."""
        out = _run_hook(
            "/random-cmd explain closures in javascript",
            monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        ctx = _ctx(out)
        assert "ROUTING SKIPPED" not in ctx
        assert "Route:" in ctx

    def test_slash_alone_skipped(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        """/cancelomc alone → skip routing."""
        out = _run_hook(
            "/cancelomc",
            monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        ctx = _ctx(out)
        assert "ROUTING SKIPPED" in ctx


# --- active_spec helpers ---

class TestActiveSpecHelpers:
    def test_default_session_has_active_spec(self):
        assert "active_spec" in DEFAULT_SESSION
        assert DEFAULT_SESSION["active_spec"] is None

    def test_set_get_clear_active_spec(self, session_path):
        s = SessionState(session_path)
        assert s.get_active_spec() is None
        s.set_active_spec("my spec")
        assert s.get_active_spec() == "my spec"
        s.clear_active_spec()
        assert s.get_active_spec() is None
