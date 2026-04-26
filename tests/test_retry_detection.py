"""Tests for v1.7 retry-escalation detection.

Verifies that classify-prompt's _detect_retry() recognizes the
/polyrouter:retry slash-command marker, escalates the routed tier
according to the v1.7 path (fast → standard → deep/medium → deep/high
→ deep/xhigh → ceiling), and persists retry state for the HUD arrow.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import SessionState
from lib.stats import Stats

# Load classify-prompt.py as a module (filename has a hyphen)
_CP_PATH = Path(__file__).parent.parent / "hooks" / "classify-prompt.py"
_spec = importlib.util.spec_from_file_location("classify_prompt", _CP_PATH)
classify_prompt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(classify_prompt)

_RETRY_MARKER = classify_prompt._RETRY_MARKER


@pytest.fixture
def session(tmp_path):
    return SessionState(tmp_path / "session.json")


@pytest.fixture
def stats(tmp_path):
    return Stats(tmp_path / "stats.json")


@pytest.fixture
def config():
    return {
        "levels": {
            "fast": {
                "model": "haiku",
                "agent": "fast-executor",
                "cost_per_1k_input": 0.001,
                "cost_per_1k_output": 0.005,
            },
            "standard": {
                "model": "sonnet",
                "agent": "standard-executor",
                "cost_per_1k_input": 0.003,
                "cost_per_1k_output": 0.015,
            },
            "deep": {
                "model": "opus",
                "agent": "deep-executor",
                "cost_per_1k_input": 0.015,
                "cost_per_1k_output": 0.075,
            },
        },
    }


class TestRetryEscalateTable:
    """_retry_escalate() implements the v1.7 escalation path."""

    def test_fast_to_standard_medium(self):
        assert classify_prompt._retry_escalate("fast", "low") == ("standard", "medium", False)
        assert classify_prompt._retry_escalate("fast", "medium") == ("standard", "medium", False)
        assert classify_prompt._retry_escalate("fast", "high") == ("standard", "medium", False)

    def test_standard_to_deep_medium(self):
        assert classify_prompt._retry_escalate("standard", "medium") == ("deep", "medium", False)
        assert classify_prompt._retry_escalate("standard", "high") == ("deep", "medium", False)

    def test_deep_medium_to_deep_high(self):
        assert classify_prompt._retry_escalate("deep", "medium") == ("deep", "high", False)

    def test_deep_low_bumps_to_high(self):
        # deep tier without explicit high/xhigh effort → escalate effort to high
        assert classify_prompt._retry_escalate("deep", "low") == ("deep", "high", False)

    def test_deep_high_to_deep_xhigh(self):
        assert classify_prompt._retry_escalate("deep", "high") == ("deep", "xhigh", False)

    def test_deep_xhigh_at_ceiling(self):
        to_tier, to_eff, ceiling = classify_prompt._retry_escalate("deep", "xhigh")
        assert (to_tier, to_eff) == ("deep", "xhigh")
        assert ceiling is True

    def test_no_prior_tier_starts_at_standard(self):
        # First retry on a fresh session — sensible default rather than no-op.
        assert classify_prompt._retry_escalate(None, None) == ("standard", "medium", False)

    def test_unknown_tier_starts_at_standard(self):
        assert classify_prompt._retry_escalate("invalid", "medium") == ("standard", "medium", False)


class TestDetectRetryMarker:
    """_detect_retry recognizes the marker and returns a route output."""

    def test_no_marker_returns_none_and_clears_state(self, session, stats, config):
        # Pre-seed retry state to verify it gets cleared.
        session.mark_retry("fast", "low", "standard", "medium", at_ceiling=False)
        assert session.read()["retry_active"] is True

        result = classify_prompt._detect_retry("normal prompt", session, config, stats)
        assert result is None
        assert session.read()["retry_active"] is False
        assert session.read()["retry_from_tier"] is None

    def test_marker_in_prompt_returns_route(self, session, stats, config):
        # No prior session state — should default escalate to standard/medium.
        prompt = f"{_RETRY_MARKER}\n# /retry Command"
        out = classify_prompt._detect_retry(prompt, session, config, stats)
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Route: standard" in ctx
        assert "Model: sonnet" in ctx
        assert "polyrouter:standard-executor" in ctx

    def test_marker_with_prev_fast_escalates_to_standard(self, session, stats, config):
        session.update("fast", "en")
        session.update_effort("low")
        out = classify_prompt._detect_retry(_RETRY_MARKER, session, config, stats)
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Route: standard" in ctx
        state = session.read()
        assert state["retry_active"] is True
        assert state["retry_from_tier"] == "fast"
        assert state["retry_to_tier"] == "standard"
        assert state["retry_at_ceiling"] is False

    def test_marker_with_prev_standard_escalates_to_deep_medium(self, session, stats, config):
        session.update("standard", "en")
        session.update_effort("medium")
        out = classify_prompt._detect_retry(_RETRY_MARKER, session, config, stats)
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Route: deep" in ctx
        state = session.read()
        assert state["retry_to_tier"] == "deep"
        assert state["retry_to_effort"] == "medium"

    def test_marker_with_prev_deep_medium_bumps_effort_to_high(self, session, stats, config):
        session.update("deep", "en")
        session.update_effort("medium")
        out = classify_prompt._detect_retry(_RETRY_MARKER, session, config, stats)
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Route: deep" in ctx
        assert "Effort: high" in ctx
        state = session.read()
        assert state["retry_from_effort"] == "medium"
        assert state["retry_to_effort"] == "high"

    def test_marker_with_prev_deep_high_bumps_to_xhigh(self, session, stats, config):
        session.update("deep", "en")
        session.update_effort("high")
        out = classify_prompt._detect_retry(_RETRY_MARKER, session, config, stats)
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Effort: xhigh" in ctx
        state = session.read()
        assert state["retry_to_effort"] == "xhigh"
        assert state["retry_at_ceiling"] is False

    def test_marker_at_ceiling_keeps_deep_xhigh_marks_ceiling(self, session, stats, config):
        session.update("deep", "en")
        session.update_effort("xhigh")
        out = classify_prompt._detect_retry(_RETRY_MARKER, session, config, stats)
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Route: deep" in ctx
        assert "Effort: xhigh" in ctx
        state = session.read()
        assert state["retry_active"] is True
        assert state["retry_at_ceiling"] is True
        assert state["retry_to_tier"] == "deep"
        assert state["retry_to_effort"] == "xhigh"


class TestRetryChain:
    """Chain of retries walks the escalation path correctly."""

    def test_full_chain_fast_to_ceiling(self, session, stats, config):
        # Start: prev turn was fast/low.
        session.update("fast", "en")
        session.update_effort("low")

        # Retry #1: fast → standard/medium
        classify_prompt._detect_retry(_RETRY_MARKER, session, config, stats)
        assert session.read()["last_level"] == "standard"

        # Retry #2: standard → deep/medium
        classify_prompt._detect_retry(_RETRY_MARKER, session, config, stats)
        s = session.read()
        assert s["last_level"] == "deep"
        assert s["effort_level"] == "medium"

        # Retry #3: deep/medium → deep/high
        classify_prompt._detect_retry(_RETRY_MARKER, session, config, stats)
        s = session.read()
        assert s["last_level"] == "deep"
        assert s["effort_level"] == "high"

        # Retry #4: deep/high → deep/xhigh
        classify_prompt._detect_retry(_RETRY_MARKER, session, config, stats)
        s = session.read()
        assert s["last_level"] == "deep"
        assert s["effort_level"] == "xhigh"
        assert s["retry_at_ceiling"] is False

        # Retry #5: at ceiling — no further escalation, ceiling flag set.
        classify_prompt._detect_retry(_RETRY_MARKER, session, config, stats)
        s = session.read()
        assert s["last_level"] == "deep"
        assert s["effort_level"] == "xhigh"
        assert s["retry_at_ceiling"] is True

    def test_normal_prompt_clears_retry_state(self, session, stats, config):
        # Build up: prev turn was deep/high, retry brought us to deep/xhigh.
        session.update("deep", "en")
        session.update_effort("high")
        classify_prompt._detect_retry(_RETRY_MARKER, session, config, stats)
        assert session.read()["retry_active"] is True

        # Next normal (non-retry) prompt should clear the arrow.
        classify_prompt._detect_retry("just a normal question", session, config, stats)
        s = session.read()
        assert s["retry_active"] is False
        assert s["retry_from_tier"] is None
        assert s["retry_to_tier"] is None
        assert s["retry_at_ceiling"] is False
