"""Tests for v1.9.6 Group 3 — intelligent HUD.

Covers three features:

1. Prompt quality scorer (classify-prompt.score_prompt_quality): a 0-100
   heuristic persisted to session.prompt_quality and rendered as a q:N% HUD
   nudge when the prompt is under-specified.

2. Soul Map (classify-prompt soul helpers): learns ONLY explicit user model
   preferences ("usa opus", "with sonnet"…) into ~/.claude/poly-soul.json and
   boosts routing confidence once a preference recurs 3+ times.

3. Active-session time: format_status_line renders ⏱{m}m in the tail from the
   session's routing_started_at.
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

score = classify_prompt.score_prompt_quality
detect_soul = classify_prompt.detect_soul_preference
learn_soul = classify_prompt.learn_soul_preference
soul_boost = classify_prompt.soul_confidence_boost


def _run(prompt, tmp_path, monkeypatch, force_level=None, payload=None):
    """Run classify-prompt.main() and return (additionalContext, session_file).

    Redirects SESSION_PATH and SOUL_PATH to tmp so the real ~/.claude is never
    touched, and pins scoring when force_level is given.
    """
    session_file = tmp_path / "session.json"
    monkeypatch.setattr(classify_prompt, "SESSION_PATH", session_file)
    monkeypatch.setattr(classify_prompt, "SOUL_PATH", tmp_path / "poly-soul.json")
    if force_level is not None:
        monkeypatch.setattr(
            classify_prompt, "_stage_scoring",
            lambda *a, **k: (force_level, 0.9, "scoring", 0.5),
        )
    for var in ("CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_EFFORT", "ANTHROPIC_FALLBACK_MODEL"):
        monkeypatch.delenv(var, raising=False)

    stdin_payload = {"prompt": prompt}
    if payload:
        stdin_payload.update(payload)

    captured = {}
    monkeypatch.setattr("builtins.print", lambda s: captured.update(out=json.loads(s)))
    monkeypatch.setattr(sys, "stdin", mock.Mock(read=lambda: json.dumps(stdin_payload)))
    classify_prompt.main()
    ctx = captured["out"].get("hookSpecificOutput", {}).get("additionalContext", "")
    return ctx, session_file


# --- Feature 1: prompt quality scorer -------------------------------------

class TestScorePromptQuality:

    def test_empty_and_non_string(self):
        assert score("") == 0
        assert score("   ") == 0
        assert score(None) == 0

    def test_bare_one_liner_is_low(self):
        # 1-3 words, no context → ambiguity penalty lands in the red zone (<50).
        # base 50 - 30 (ambiguous) = 20.
        assert score("fix it") == 20
        assert score("fix it") < 50

    def test_vague_language_penalised(self):
        # "improve" is vague; padded to >3 words so only the vague penalty hits.
        # base 50 - 20 (vague) = 30, still in the red zone.
        assert score("please just improve this code now") == 30
        assert score("please just improve this code now") < 50

    def test_well_structured_prompt_is_high(self):
        # success + scope + context + XML + length → hidden by the HUD (>=80).
        body = " ".join(["carefully"] * 25)
        query = (
            "<task>refactor</task> the success criteria is clear: only touch "
            f"the auth.py file and nothing else. {body}"
        )
        assert score(query) >= 80

    def test_context_via_file_path(self):
        # A file path satisfies the project-context criterion (+15). Kept >3
        # words so the ambiguity penalty does not cancel it.
        assert score("please open the src/server/handler.ts now") >= 15

    def test_clamped_to_range(self):
        for q in ("", "fix it", "x " * 300):
            assert 0 <= score(q) <= 100

    def test_persisted_to_session(self, tmp_path, monkeypatch):
        _, session_file = _run("hola", tmp_path, monkeypatch, force_level="fast")
        # "hola" is a 1-word prompt → base 50 - 30 (ambiguous) = 20.
        assert SessionState(session_file).read()["prompt_quality"] == 20


class TestUpdatePromptQualityUnit:

    def test_clamps_and_stores(self, tmp_path):
        session = SessionState(tmp_path / "session.json")
        session.update_prompt_quality(150)
        assert session.read()["prompt_quality"] == 100
        session.update_prompt_quality(-5)
        assert session.read()["prompt_quality"] == 0

    def test_none_clears(self, tmp_path):
        session = SessionState(tmp_path / "session.json")
        session.update_prompt_quality(40)
        session.update_prompt_quality(None)
        assert session.read()["prompt_quality"] is None

    def test_default_is_none(self, tmp_path):
        session = SessionState(tmp_path / "session.json")
        assert session.read()["prompt_quality"] is None


class TestQualityHudRender:

    def test_low_quality_shows_red_nudge(self):
        line = format_status_line("idle", 0, tier="fast", prompt_quality=40)
        assert "q:40%" in line

    def test_mid_quality_shows_nudge(self):
        line = format_status_line("idle", 0, tier="fast", prompt_quality=65)
        assert "q:65%" in line

    def test_good_quality_hidden(self):
        line = format_status_line("idle", 0, tier="fast", prompt_quality=85)
        assert "q:" not in line

    def test_none_quality_hidden(self):
        line = format_status_line("idle", 0, tier="fast", prompt_quality=None)
        assert "q:" not in line


# --- Feature 2: Soul Map ---------------------------------------------------

class TestDetectSoulPreference:

    @pytest.mark.parametrize("prompt,model", [
        ("usa opus para esto", "opus"),
        ("use sonnet please", "sonnet"),
        ("fuerza haiku aquí", "haiku"),
        ("hazlo con opus", "opus"),
        ("do it with sonnet", "sonnet"),
        ("quiero opus", "opus"),
        ("I need haiku for this", "haiku"),
    ])
    def test_explicit_mentions(self, prompt, model):
        result = detect_soul(prompt)
        assert result is not None
        assert result[1] == model

    def test_no_mention_returns_none(self):
        assert detect_soul("implement the login feature") is None
        assert detect_soul("") is None
        assert detect_soul("opus is a great model name") is None


class TestLearnSoulPreference:

    def test_learns_and_increments(self, tmp_path):
        soul = tmp_path / "poly-soul.json"
        learn_soul("usa opus", path=soul, now=100.0)
        rec = learn_soul("usa opus", path=soul, now=200.0)
        assert rec["count"] == 2
        assert rec["model"] == "opus"
        assert rec["last_seen"] == 200.0
        data = json.loads(soul.read_text())
        assert len(data["patterns"]) == 1

    def test_never_learns_without_explicit_mention(self, tmp_path):
        soul = tmp_path / "poly-soul.json"
        assert learn_soul("refactor the auth module", path=soul) is None
        # No file is written when there is nothing explicit to learn.
        assert not soul.exists()

    def test_distinct_signals_tracked_separately(self, tmp_path):
        soul = tmp_path / "poly-soul.json"
        learn_soul("usa opus", path=soul, now=1.0)
        learn_soul("use sonnet", path=soul, now=2.0)
        data = json.loads(soul.read_text())
        assert len(data["patterns"]) == 2


class TestSoulConfidenceBoost:

    def test_no_boost_below_threshold(self):
        soul = {"patterns": [{"signal": "usa opus", "model": "opus", "count": 2}]}
        assert soul_boost("opus", soul) == 0.0

    def test_boost_at_threshold(self):
        soul = {"patterns": [{"signal": "usa opus", "model": "opus", "count": 3}]}
        assert soul_boost("opus", soul) == pytest.approx(0.15)

    def test_counts_aggregate_across_signals(self):
        soul = {"patterns": [
            {"signal": "usa opus", "model": "opus", "count": 2},
            {"signal": "con opus", "model": "opus", "count": 1},
        ]}
        assert soul_boost("opus", soul) == pytest.approx(0.15)

    def test_no_boost_for_unknown_model(self):
        assert soul_boost(None, {"patterns": []}) == 0.0
        assert soul_boost("haiku", {"patterns": []}) == 0.0

    def test_established_preference_boosts_routing(self, tmp_path, monkeypatch):
        # Pre-seed sonnet at the threshold, then route a prompt that names
        # sonnet (not caught by intent_override, which only handles opus/haiku).
        soul = tmp_path / "poly-soul.json"
        soul.write_text(json.dumps({"patterns": [
            {"signal": "with sonnet", "model": "sonnet", "count": 3, "last_seen": 1.0},
        ]}), encoding="utf-8")
        monkeypatch.setattr(classify_prompt, "SOUL_PATH", soul)
        _, session_file = _run(
            "do it with sonnet please", tmp_path, monkeypatch, force_level="standard",
        )
        methods = SessionState(session_file).read().get("routing_method_counts", {})
        assert any("soul" in m for m in methods)


# --- Feature 3: active-session time ---------------------------------------

class TestSessionTimeHud:

    def test_renders_minutes(self):
        line = format_status_line("idle", 0, tier="fast", session_elapsed_min=47)
        assert "⏱47m" in line

    def test_zero_minutes(self):
        line = format_status_line("idle", 0, tier="fast", session_elapsed_min=0)
        assert "⏱0m" in line

    def test_none_hidden(self):
        line = format_status_line("idle", 0, tier="fast", session_elapsed_min=None)
        assert "⏱" not in line
