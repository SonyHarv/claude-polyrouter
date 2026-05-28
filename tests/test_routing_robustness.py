"""Tests for v1.9.6 Group 2 — routing robustness.

Covers three features:

1. Fallback-model degradation (classify-prompt Stage 8e): when CC exports
   ANTHROPIC_FALLBACK_MODEL with a non-opus model and poly routed deep, the
   deep model is effectively unavailable — degrade deep→standard, tag the
   method with "+fallback", and persist session.fallback_used.

2. Max-effort skew detection: when CC requested "max" effort but poly routed
   below the deep tier, session.effort_skew_detected is flipped on so the HUD
   renders ⚠skew.

3. 🤖99+ subagent counter cap: the HUD caps the displayed subagent count at
   "99+" so Dynamic Workflows fanning out to hundreds never bloat the line.
"""

import json
import sys
import importlib.util
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import SessionState
from lib.hud import format_status_line


def _load_hook_module(name: str, filename: str):
    """Load a hyphenated hook script as an importable module."""
    path = Path(__file__).parent.parent / "hooks" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


classify_prompt = _load_hook_module("classify_prompt", "classify-prompt.py")


# --- Shared pipeline runner -----------------------------------------------

def _run(prompt, tmp_path, monkeypatch, force_level=None, payload=None, env=None):
    """Run classify-prompt.main() and return (additionalContext, session_file).

    force_level pins the scoring stage so the floor / fallback can be exercised
    independently of the keyword scorer. payload extends the stdin JSON (e.g.
    an effort block). env sets process env vars for the run (e.g. the fallback
    model); listed keys are removed afterwards by monkeypatch teardown.
    """
    session_file = tmp_path / "session.json"
    monkeypatch.setattr(classify_prompt, "SESSION_PATH", session_file)
    if force_level is not None:
        monkeypatch.setattr(
            classify_prompt, "_stage_scoring",
            lambda *a, **k: (force_level, 0.9, "scoring", 0.5),
        )
    # Clear effort env so only the explicit payload/env drives the run.
    for var in ("CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_EFFORT", "ANTHROPIC_FALLBACK_MODEL"):
        monkeypatch.delenv(var, raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)

    stdin_payload = {"prompt": prompt}
    if payload:
        stdin_payload.update(payload)

    captured = {}
    monkeypatch.setattr("builtins.print", lambda s: captured.update(out=json.loads(s)))
    monkeypatch.setattr(sys, "stdin", mock.Mock(read=lambda: json.dumps(stdin_payload)))
    classify_prompt.main()
    ctx = captured["out"].get("hookSpecificOutput", {}).get("additionalContext", "")
    return ctx, session_file


# --- Feature 1: fallback-model degradation --------------------------------

class TestFallbackModelDegradation:

    def test_non_opus_fallback_degrades_deep_to_standard(self, tmp_path, monkeypatch):
        # Routed deep, but CC's fallback is a sonnet model → deep unavailable.
        ctx, session_file = _run(
            "hola", tmp_path, monkeypatch, force_level="deep",
            env={"ANTHROPIC_FALLBACK_MODEL": "claude-sonnet-4-6"},
        )
        assert "Route: standard" in ctx
        state = SessionState(session_file).read()
        assert state["fallback_used"] is True
        # method tag is surfaced via session routing counts, not the directive.
        assert any("fallback" in m for m in state.get("routing_method_counts", {}))

    def test_opus_fallback_keeps_deep(self, tmp_path, monkeypatch):
        # Fallback is itself an opus model → deep is still available.
        ctx, session_file = _run(
            "hola", tmp_path, monkeypatch, force_level="deep",
            env={"ANTHROPIC_FALLBACK_MODEL": "claude-opus-4-8"},
        )
        assert "Route: deep" in ctx
        assert SessionState(session_file).read()["fallback_used"] is False

    def test_no_fallback_env_keeps_deep(self, tmp_path, monkeypatch):
        # No ANTHROPIC_FALLBACK_MODEL → no degradation.
        ctx, session_file = _run("hola", tmp_path, monkeypatch, force_level="deep")
        assert "Route: deep" in ctx
        assert SessionState(session_file).read()["fallback_used"] is False

    def test_fallback_ignored_when_tier_not_deep(self, tmp_path, monkeypatch):
        # A non-opus fallback only matters for the deep tier; standard is left
        # untouched and not flagged.
        ctx, session_file = _run(
            "hola", tmp_path, monkeypatch, force_level="standard",
            env={"ANTHROPIC_FALLBACK_MODEL": "claude-sonnet-4-6"},
        )
        assert "Route: standard" in ctx
        assert SessionState(session_file).read()["fallback_used"] is False

    def test_update_fallback_used_unit(self, tmp_path):
        session = SessionState(tmp_path / "session.json")
        session.update_fallback_used(True)
        assert session.read()["fallback_used"] is True
        session.update_fallback_used(False)
        assert session.read()["fallback_used"] is False

    def test_default_session_has_fallback_used(self, tmp_path):
        # A fresh session defaults the flag to False.
        session = SessionState(tmp_path / "session.json")
        assert session.read()["fallback_used"] is False


# --- Feature 2: max-effort skew detection ---------------------------------

class TestMaxEffortSkew:

    def test_max_effort_below_deep_flags_skew(self, tmp_path, monkeypatch):
        # CC asked for max effort but poly routed fast → skew.
        _, session_file = _run(
            "hola", tmp_path, monkeypatch, force_level="fast",
            payload={"effort": {"level": "max"}},
        )
        assert SessionState(session_file).read()["effort_skew_detected"] is True

    def test_max_effort_with_deep_does_not_flag_skew(self, tmp_path, monkeypatch):
        # CC asked for max and poly routed deep → intents agree, so Feature 2's
        # rule must NOT fire. Pre-seed the prior effort_level to "xhigh" (what
        # CC's "max" normalizes to) so the pre-existing update_cc_effort
        # comparison also computes no-skew; this isolates the Feature 2 rule.
        import time
        session_file = tmp_path / "session.json"
        session_file.write_text(json.dumps({
            "effort_level": "xhigh",
            "last_query_time": time.time(),
        }), encoding="utf-8")
        _run(
            "hola", tmp_path, monkeypatch, force_level="deep",
            payload={"effort": {"level": "max"}},
        )
        assert SessionState(session_file).read()["effort_skew_detected"] is False

    def test_set_effort_skew_unit(self, tmp_path):
        session = SessionState(tmp_path / "session.json")
        session.set_effort_skew(True)
        assert session.read()["effort_skew_detected"] is True
        session.set_effort_skew(False)
        assert session.read()["effort_skew_detected"] is False

    def test_hud_renders_skew_glyph(self):
        line = format_status_line(
            "idle", 0, tier="fast", exec_model="sonnet",
            effort_skew_detected=True,
        )
        assert "⚠skew" in line

    def test_hud_omits_skew_glyph_when_clear(self):
        line = format_status_line(
            "idle", 0, tier="fast", exec_model="sonnet",
            effort_skew_detected=False,
        )
        assert "⚠skew" not in line


# --- Feature 3: 🤖99+ subagent counter cap --------------------------------

class TestSubagentCounterCap:

    def test_single_digit_count(self):
        line = format_status_line("idle", 0, tier="fast", subagent_count=5)
        assert "\U0001f9165" in line

    def test_double_digit_count(self):
        line = format_status_line("idle", 0, tier="fast", subagent_count=50)
        assert "\U0001f91650" in line

    def test_count_99_not_capped(self):
        line = format_status_line("idle", 0, tier="fast", subagent_count=99)
        assert "\U0001f91699" in line
        assert "99+" not in line

    def test_count_100_capped(self):
        line = format_status_line("idle", 0, tier="fast", subagent_count=100)
        assert "\U0001f91699+" in line

    def test_count_hundreds_capped(self):
        line = format_status_line("idle", 0, tier="fast", subagent_count=347)
        assert "\U0001f91699+" in line
        assert "347" not in line

    def test_zero_count_no_glyph(self):
        line = format_status_line("idle", 0, tier="fast", subagent_count=0)
        assert "\U0001f916" not in line

    def test_mark_subagent_active_has_no_cap(self, tmp_path):
        # context.py must not clamp the counter — the cap is display-only.
        session = SessionState(tmp_path / "session.json")
        for _ in range(150):
            session.mark_subagent_active()
        assert session.read()["subagent_count"] == 150
