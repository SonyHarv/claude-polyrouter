"""Tests for v1.7 /polyrouter:effort one-shot override.

Covers:
- _detect_effort_command: marker + valid/invalid arg handling, session writes.
- _apply_effort_override: consume + clear semantics, auto-promote-to-deep on xhigh.
- End-to-end: /polyrouter:effort xhigh sets override on turn N, the next
  prompt's normal scoring path consumes and clears it.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import SessionState

# classify-prompt.py uses a hyphen, so load via importlib.
_CP_PATH = Path(__file__).parent.parent / "hooks" / "classify-prompt.py"
_spec = importlib.util.spec_from_file_location("classify_prompt", _CP_PATH)
classify_prompt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(classify_prompt)

_EFFORT_MARKER = classify_prompt._EFFORT_MARKER


@pytest.fixture
def session(tmp_path):
    return SessionState(tmp_path / "session.json")


@pytest.fixture
def config():
    return {
        "levels": {
            "fast": {"model": "haiku", "agent": "fast-executor",
                     "cost_per_1k_input": 0.001, "cost_per_1k_output": 0.005},
            "standard": {"model": "sonnet", "agent": "standard-executor",
                         "cost_per_1k_input": 0.003, "cost_per_1k_output": 0.015},
            "deep": {"model": "opus", "agent": "deep-executor",
                     "cost_per_1k_input": 0.015, "cost_per_1k_output": 0.075},
        },
    }


class TestExtractEffortArg:
    """_extract_effort_arg pulls the level token from the prompt body."""

    @pytest.mark.parametrize("arg", ["low", "medium", "high", "xhigh"])
    def test_valid_levels(self, arg):
        prompt = f"{_EFFORT_MARKER}\n{arg}"
        assert classify_prompt._extract_effort_arg(prompt) == arg

    def test_case_insensitive(self):
        prompt = f"{_EFFORT_MARKER}\nXHIGH"
        assert classify_prompt._extract_effort_arg(prompt) == "xhigh"

    def test_no_arg_returns_none(self):
        assert classify_prompt._extract_effort_arg(_EFFORT_MARKER) is None

    def test_invalid_arg_returns_none(self):
        prompt = f"{_EFFORT_MARKER}\nultrahigh"
        assert classify_prompt._extract_effort_arg(prompt) is None

    def test_non_string_returns_none(self):
        assert classify_prompt._extract_effort_arg(None) is None

    def test_picks_first_valid_token_when_extra_text(self):
        prompt = f"{_EFFORT_MARKER}\nhigh because reasons follow"
        assert classify_prompt._extract_effort_arg(prompt) == "high"


class TestDetectEffortCommand:
    """_detect_effort_command marker handling and session writes."""

    def test_no_marker_returns_none(self, session):
        out = classify_prompt._detect_effort_command("normal prompt", session)
        assert out is None
        assert session.read().get("effort_override_active") is False

    def test_valid_xhigh_sets_promote_deep(self, session):
        out = classify_prompt._detect_effort_command(
            f"{_EFFORT_MARKER}\nxhigh", session,
        )
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "[POLY:EFFORT]" in ctx
        assert "xhigh" in ctx
        assert "Auto-promote" in ctx
        state = session.read()
        assert state["effort_override_active"] is True
        assert state["effort_override_level"] == "xhigh"
        assert state["effort_override_promote_deep"] is True

    def test_valid_high_does_not_promote(self, session):
        out = classify_prompt._detect_effort_command(
            f"{_EFFORT_MARKER}\nhigh", session,
        )
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "[POLY:EFFORT]" in ctx
        assert "Auto-promote" not in ctx
        state = session.read()
        assert state["effort_override_level"] == "high"
        assert state["effort_override_promote_deep"] is False

    def test_invalid_arg_emits_error_block_no_persist(self, session):
        out = classify_prompt._detect_effort_command(
            f"{_EFFORT_MARKER}\nultrahigh", session,
        )
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "[POLY:EFFORT-ERROR]" in ctx
        # The error block lists valid levels.
        for valid in ("low", "medium", "high", "xhigh"):
            assert valid in ctx
        # Override must NOT be persisted on invalid input.
        assert session.read().get("effort_override_active") is False

    def test_missing_arg_emits_error_block(self, session):
        out = classify_prompt._detect_effort_command(_EFFORT_MARKER, session)
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "[POLY:EFFORT-ERROR]" in ctx
        assert session.read().get("effort_override_active") is False

    def test_ack_block_has_no_spawn_directive(self, session):
        # The slash-command turn must NOT instruct CC to spawn a subagent —
        # the override is a sticky note for the *next* turn.
        out = classify_prompt._detect_effort_command(
            f"{_EFFORT_MARKER}\nlow", session,
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Spawn" not in ctx
        assert "Route:" not in ctx


class TestApplyEffortOverride:
    """_apply_effort_override consumes + auto-promotes correctly."""

    def test_no_override_is_noop(self, session, config):
        out = classify_prompt._apply_effort_override(
            "fast", "haiku", "fast-executor", "low",
            session, config,
        )
        assert out == ("fast", "haiku", "fast-executor", "low")

    def test_high_override_keeps_tier(self, session, config):
        session.set_effort_override("high", promote_deep=False)
        out = classify_prompt._apply_effort_override(
            "fast", "haiku", "fast-executor", "low",
            session, config,
        )
        # Tier preserved; effort replaced.
        assert out == ("fast", "haiku", "fast-executor", "high")
        # Single-fire — second call is a no-op.
        again = classify_prompt._apply_effort_override(
            "fast", "haiku", "fast-executor", "low",
            session, config,
        )
        assert again == ("fast", "haiku", "fast-executor", "low")

    def test_xhigh_promotes_to_deep(self, session, config):
        session.set_effort_override("xhigh", promote_deep=True)
        out = classify_prompt._apply_effort_override(
            "fast", "haiku", "fast-executor", "low",
            session, config,
        )
        assert out == ("deep", "opus", "deep-executor", "xhigh")

    def test_xhigh_on_already_deep_keeps_deep(self, session, config):
        session.set_effort_override("xhigh", promote_deep=True)
        out = classify_prompt._apply_effort_override(
            "deep", "opus", "deep-executor", "high",
            session, config,
        )
        # Already deep — model/agent untouched, effort upgraded.
        assert out == ("deep", "opus", "deep-executor", "xhigh")

    def test_consume_clears_override(self, session, config):
        session.set_effort_override("high", promote_deep=False)
        classify_prompt._apply_effort_override(
            "fast", "haiku", "fast-executor", "low",
            session, config,
        )
        state = session.read()
        assert state["effort_override_active"] is False
        assert state["effort_override_level"] is None


class TestSessionStateAPI:
    """SessionState.set_effort_override / consume / clear semantics."""

    def test_invalid_level_not_persisted(self, session):
        session.set_effort_override("ultrahigh")  # type: ignore[arg-type]
        assert session.read().get("effort_override_active") is False

    def test_consume_returns_none_when_inactive(self, session):
        assert session.consume_effort_override() is None

    def test_consume_returns_dict_then_clears(self, session):
        session.set_effort_override("high", promote_deep=False)
        result = session.consume_effort_override()
        assert result == {"level": "high", "promote_deep": False}
        # Second consume is a no-op.
        assert session.consume_effort_override() is None

    def test_clear_without_consuming(self, session):
        session.set_effort_override("xhigh", promote_deep=True)
        session.clear_effort_override()
        assert session.consume_effort_override() is None
        state = session.read()
        assert state["effort_override_active"] is False
        assert state["effort_override_level"] is None
        assert state["effort_override_promote_deep"] is False


class TestTwoTurnFlow:
    """End-to-end: slash-command turn arms, next turn consumes + clears."""

    def test_xhigh_armed_then_consumed_with_promotion(self, session, config):
        # Turn N: user types /polyrouter:effort xhigh — armed only.
        ack = classify_prompt._detect_effort_command(
            f"{_EFFORT_MARKER}\nxhigh", session,
        )
        assert ack is not None
        assert "[POLY:EFFORT]" in ack["hookSpecificOutput"]["additionalContext"]
        assert session.read()["effort_override_active"] is True

        # Turn N+1: a normal "fast" route call applies override.
        level, model, agent, effort = classify_prompt._apply_effort_override(
            "fast", "haiku", "fast-executor", "low",
            session, config,
        )
        assert (level, model, agent, effort) == ("deep", "opus", "deep-executor", "xhigh")
        # Override cleared after one use.
        assert session.read()["effort_override_active"] is False

    def test_low_armed_keeps_tier_on_consume(self, session, config):
        classify_prompt._detect_effort_command(
            f"{_EFFORT_MARKER}\nlow", session,
        )
        level, model, agent, effort = classify_prompt._apply_effort_override(
            "standard", "sonnet", "standard-executor", "medium",
            session, config,
        )
        assert (level, model, agent, effort) == ("standard", "sonnet", "standard-executor", "low")

    def test_invalid_arg_does_not_arm_so_next_turn_routes_normally(self, session, config):
        classify_prompt._detect_effort_command(
            f"{_EFFORT_MARKER}\nbogus", session,
        )
        # Next turn — no override to apply, route untouched.
        out = classify_prompt._apply_effort_override(
            "fast", "haiku", "fast-executor", "low",
            session, config,
        )
        assert out == ("fast", "haiku", "fast-executor", "low")
