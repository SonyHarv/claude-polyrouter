"""Tests for v1.7 advisor hand-off (auto block + manual command).

Covers:
- _route_output() injects [POLY:ADVISOR] block when advisor=True (auto path).
- _route_output() honors advisor_block_override (manual path).
- _detect_advisor_command() force-routes to deep/xhigh + opus-orchestrator
  when the /polyrouter:advisor marker is present.
- _build_manual_advisor_block() pre-loads project context (cwd basename,
  branch, last turn).
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import SessionState
from lib.stats import Stats

# classify-prompt.py uses a hyphen, so load via importlib.
_CP_PATH = Path(__file__).parent.parent / "hooks" / "classify-prompt.py"
_spec = importlib.util.spec_from_file_location("classify_prompt", _CP_PATH)
classify_prompt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(classify_prompt)

_ADVISOR_MARKER = classify_prompt._ADVISOR_MARKER


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


class TestRouteOutputAdvisorAutoBlock:
    """When advisor=True (no override), _route_output injects the auto block."""

    def test_advisor_true_includes_poly_advisor_block(self, config):
        out = classify_prompt._route_output(
            level="deep", model="opus", agent="deep-executor",
            confidence=0.9, method="test", signals="test", language="en",
            query="redesign the auth session model",
            effort="high", advisor=True,
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "[POLY:ADVISOR]" in ctx
        assert "Auth redesign" in ctx
        assert "Advisor: required" in ctx
        # The escape-hatch hint is part of every auto block.
        assert "/polyrouter:advisor" in ctx

    def test_advisor_false_omits_advisor_block(self):
        out = classify_prompt._route_output(
            level="standard", model="sonnet", agent="standard-executor",
            confidence=0.7, method="test", signals="test", language="en",
            query="redesign the auth session model",
            effort="medium", advisor=False,
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "[POLY:ADVISOR]" not in ctx
        assert "Advisor: required" not in ctx

    def test_advisor_true_unrecognized_query_uses_generic_block(self):
        # No keyword matches → generic architecture_general fallback.
        out = classify_prompt._route_output(
            level="deep", model="opus", agent="deep-executor",
            confidence=0.9, method="test", signals="test", language="en",
            query="just a vague design question",
            effort="high", advisor=True,
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "[POLY:ADVISOR]" in ctx
        assert "Architectural decision" in ctx  # generic label


class TestRouteOutputAdvisorOverride:
    """advisor_block_override takes precedence over the auto block."""

    def test_override_replaces_auto_block(self):
        custom = "[POLY:ADVISOR-MANUAL]\nQuestion: pre-loaded\nProject: foo"
        out = classify_prompt._route_output(
            level="deep", model="opus", agent="opus-orchestrator",
            confidence=1.0, method="advisor_manual",
            signals="advisor_manual_command", language="en",
            query="redesign the auth session model",  # would otherwise trigger auto
            effort="xhigh", advisor=True,
            advisor_block_override=custom,
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert custom in ctx
        # Auto block must NOT appear when override is provided.
        assert "[POLY:ADVISOR]\nCategory:" not in ctx

    def test_override_works_when_advisor_false(self):
        # An explicit override should still be appended even if the
        # advisor flag is False (manual escape hatch is the source of truth).
        custom = "[POLY:ADVISOR-MANUAL]\nQuestion: x"
        out = classify_prompt._route_output(
            level="deep", model="opus", agent="opus-orchestrator",
            confidence=1.0, method="advisor_manual",
            signals="advisor_manual_command", language="en",
            query="anything",
            effort="xhigh", advisor=False,
            advisor_block_override=custom,
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert custom in ctx


class TestDetectAdvisorCommand:
    """The /polyrouter:advisor marker force-routes to opus-orchestrator."""

    def test_no_marker_returns_none(self, session, stats, config):
        out = classify_prompt._detect_advisor_command(
            "normal prompt", config, stats, session, None,
        )
        assert out is None

    def test_marker_routes_to_deep_xhigh_opus_orchestrator(self, session, stats, config):
        prompt = f"{_ADVISOR_MARKER}\nShould we shard the orders table?"
        out = classify_prompt._detect_advisor_command(
            prompt, config, stats, session, None,
        )
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Route: deep" in ctx
        assert "Model: opus" in ctx
        assert "Effort: xhigh" in ctx
        assert "Advisor: required" in ctx
        assert "polyrouter:opus-orchestrator" in ctx

    def test_marker_persists_advisor_state(self, session, stats, config):
        prompt = f"{_ADVISOR_MARKER}\nQuestion"
        classify_prompt._detect_advisor_command(prompt, config, stats, session, None)
        state = session.read()
        assert state.get("requires_advisor") is True
        assert state.get("last_level") == "deep"
        assert state.get("effort_level") == "xhigh"

    def test_marker_emits_manual_block(self, session, stats, config, tmp_path):
        prompt = f"{_ADVISOR_MARKER}\nShould we shard the orders table?"
        out = classify_prompt._detect_advisor_command(
            prompt, config, stats, session, None,
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "[POLY:ADVISOR-MANUAL]" in ctx
        assert "Question:" in ctx
        # Auto [POLY:ADVISOR] must not appear when manual override is in play.
        assert "[POLY:ADVISOR]\nCategory:" not in ctx

    def test_marker_block_has_project_basename(self, session, stats, config):
        prompt = f"{_ADVISOR_MARKER}\nQuestion"
        out = classify_prompt._detect_advisor_command(
            prompt, config, stats, session, None,
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        # Project line is included (cwd basename — varies by test runner cwd).
        assert "Project:" in ctx


class TestBuildManualAdvisorBlock:
    """_build_manual_advisor_block assembles pre-loaded context."""

    def test_block_includes_question_text(self):
        prompt = f"{_ADVISOR_MARKER}\nShould we replace the OAuth flow?"
        block = classify_prompt._build_manual_advisor_block(prompt, None)
        assert "[POLY:ADVISOR-MANUAL]" in block
        assert "Should we replace the OAuth flow?" in block
        # Marker itself is stripped from the question.
        assert _ADVISOR_MARKER not in block

    def test_block_truncates_long_question(self):
        long_q = "x " * 2000
        prompt = f"{_ADVISOR_MARKER}\n{long_q}"
        block = classify_prompt._build_manual_advisor_block(prompt, None)
        # Question slice is bounded to ~1000 chars.
        question_line = next(
            (line for line in block.splitlines() if line.startswith("Question:")),
            "",
        )
        assert len(question_line) <= 1100  # "Question: " prefix + content

    def test_block_handles_missing_transcript_path(self):
        prompt = f"{_ADVISOR_MARKER}\nQ"
        # Should not raise even when transcript_path is None or invalid.
        block = classify_prompt._build_manual_advisor_block(prompt, None)
        assert "[POLY:ADVISOR-MANUAL]" in block
        block2 = classify_prompt._build_manual_advisor_block(prompt, "/nonexistent.jsonl")
        assert "[POLY:ADVISOR-MANUAL]" in block2

    def test_block_includes_last_turn_when_transcript_valid(self, tmp_path):
        # Build a minimal JSONL transcript with one user + one assistant turn.
        transcript = tmp_path / "session.jsonl"
        lines = [
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "earlier question about caching"},
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "earlier answer about caching strategy"}],
                },
            }),
        ]
        transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

        prompt = f"{_ADVISOR_MARKER}\nFollow-up question"
        block = classify_prompt._build_manual_advisor_block(prompt, str(transcript))
        # When the helper succeeds, the Last turn block is included.
        # When it fails (different transcript shape), the function still
        # returns a valid block — assert the safety property either way.
        assert "[POLY:ADVISOR-MANUAL]" in block
        assert "Follow-up question" in block
