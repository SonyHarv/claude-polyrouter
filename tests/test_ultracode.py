"""Tests for v1.9.8 ultracode — strict explicit Opus-ceiling trigger.

Covers:
  - is_ultracode_trigger: STRICT start-of-prompt detection only
  - mid-text / conversational "ultracode" never fires
  - the xhigh alias constant
  - hook integration: trigger forces deep/xhigh/opus-orchestrator + advisor
  - ultracode_active flag set on the trigger turn, cleared on the next turn
  - no spurious effort skew on an ultracode turn
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import SessionState  # noqa: E402
from lib.effort import (  # noqa: E402
    ULTRACODE_EFFORT,
    VALID_EFFORTS,
    is_ultracode_trigger,
)


# --- Pure-function: strict detection -------------------------------------

class TestStrictDetection:
    @pytest.mark.parametrize("query", [
        "/effort ultracode implementa el módulo",
        "ultracode: refactoriza auth.py",
        "  ultracode: con espacios al inicio",
        "/EFFORT ULTRACODE en mayúsculas",
        "ULTRACODE: mayúsculas con dos puntos",
        "\n  /effort ultracode  tras saltos de línea",
    ])
    def test_valid_triggers(self, query):
        assert is_ultracode_trigger(query) is True

    @pytest.mark.parametrize("query", [
        "deberías usar ultracode aquí?",        # mid-sentence
        "quiero ultracode: pero no al inicio",  # colon present, not at start
        "explica qué es ultracode",             # conversational
        "el modo ultracode es interesante",     # mid-text
        "/effort high implementa algo",         # different effort level
        "ultracode sin dos puntos al inicio",   # bare word, no colon
        "",                                     # empty
        "   ",                                  # whitespace only
    ])
    def test_non_triggers(self, query):
        assert is_ultracode_trigger(query) is False

    def test_none_is_false(self):
        assert is_ultracode_trigger(None) is False

    def test_non_string_is_false(self):
        assert is_ultracode_trigger(123) is False
        assert is_ultracode_trigger(["ultracode:"]) is False


class TestAlias:
    def test_alias_resolves_to_xhigh(self):
        assert ULTRACODE_EFFORT == "xhigh"

    def test_alias_is_a_valid_effort(self):
        assert ULTRACODE_EFFORT in VALID_EFFORTS


# --- Hook integration ----------------------------------------------------

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


def _run_hook(prompt, monkeypatch, session_path, stats_path, cache_path, capsys):
    mod = _classify_module()
    monkeypatch.setattr(mod, "SESSION_PATH", session_path)
    monkeypatch.setattr(mod, "STATS_PATH", stats_path)
    monkeypatch.setattr(mod, "CACHE_PATH", cache_path)
    payload = {"prompt": prompt, "cwd": "/tmp"}
    monkeypatch.setattr("sys.stdin", _StdinStub(json.dumps(payload)))
    mod.main()
    return json.loads(capsys.readouterr().out)


def _ctx(output):
    return output["hookSpecificOutput"]["additionalContext"]


class TestForcedRoute:
    def test_effort_ultracode_forces_opus(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        out = _run_hook(
            "/effort ultracode implementa el módulo de auth",
            monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        ctx = _ctx(out)
        assert "Route: deep" in ctx
        assert "Model: opus" in ctx
        assert "Effort: xhigh" in ctx
        assert "Advisor: required" in ctx
        assert "polyrouter:opus-orchestrator" in ctx

    def test_ultracode_colon_forces_opus(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        out = _run_hook(
            "ultracode: refactoriza el pipeline completo",
            monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        ctx = _ctx(out)
        assert "Route: deep" in ctx
        assert "Model: opus" in ctx
        assert "Effort: xhigh" in ctx

    def test_trigger_sets_session_flag(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        _run_hook(
            "ultracode: haz algo grande",
            monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        state = SessionState(session_path).read()
        assert state["ultracode_active"] is True
        assert state["effort_level"] == "xhigh"
        assert state["requires_advisor"] is True

    def test_trigger_has_no_spurious_skew(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        _run_hook(
            "/effort ultracode construye el sistema",
            monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        assert SessionState(session_path).read()["effort_skew_detected"] is False


class TestStrictNonTrigger:
    def test_midtext_mention_does_not_force(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        _run_hook(
            "deberías usar ultracode aquí o no?",
            monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        assert SessionState(session_path).read()["ultracode_active"] is False

    def test_flag_clears_on_next_turn(
        self, monkeypatch, session_path, stats_path, cache_path, capsys,
    ):
        # turn 1: trigger → flag on
        _run_hook(
            "ultracode: construye el módulo",
            monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        assert SessionState(session_path).read()["ultracode_active"] is True
        # turn 2: ordinary prompt → flag cleared (set every turn, on AND off)
        _run_hook(
            "cómo está el clima hoy",
            monkeypatch, session_path, stats_path, cache_path, capsys,
        )
        assert SessionState(session_path).read()["ultracode_active"] is False
