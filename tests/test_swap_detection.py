"""Tests for v1.7 silent model swap detection.

Verifies that classify-prompt's _detect_silent_swap() compares the
previous turn's tier against the model Claude Code actually used and
flags divergence in session state for the HUD to surface.
"""

import json
import sys
import importlib.util
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import SessionState
from lib.ctx_usage import get_last_assistant_model

# Load classify-prompt.py as a module (filename has a hyphen)
_CP_PATH = Path(__file__).parent.parent / "hooks" / "classify-prompt.py"
_spec = importlib.util.spec_from_file_location("classify_prompt", _CP_PATH)
classify_prompt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(classify_prompt)


@pytest.fixture
def session(tmp_path):
    return SessionState(tmp_path / "session.json")


@pytest.fixture
def transcript(tmp_path):
    """Build a JSONL transcript file with N assistant turns of given models."""
    def _build(models: list[str]) -> Path:
        path = tmp_path / "transcript.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for m in models:
                f.write(json.dumps({
                    "type": "assistant",
                    "message": {"role": "assistant", "model": m},
                }) + "\n")
        return path
    return _build


class TestGetLastAssistantModel:
    """ctx_usage.get_last_assistant_model() reads the most recent assistant model."""

    def test_returns_none_for_missing_path(self):
        assert get_last_assistant_model(None) is None
        assert get_last_assistant_model("/nonexistent/path.jsonl") is None

    def test_returns_last_of_multiple(self, transcript):
        path = transcript([
            "claude-haiku-4-5",
            "claude-sonnet-4-6",
            "claude-opus-4-7",
        ])
        assert get_last_assistant_model(str(path)) == "claude-opus-4-7"

    def test_returns_none_for_empty_transcript(self, tmp_path):
        empty = tmp_path / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        assert get_last_assistant_model(str(empty)) is None

    def test_skips_non_assistant_messages(self, tmp_path):
        path = tmp_path / "mixed.jsonl"
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"message": {"role": "user", "model": "ignored"}}) + "\n")
            f.write(json.dumps({"message": {"role": "assistant", "model": "claude-haiku-4-5"}}) + "\n")
        assert get_last_assistant_model(str(path)) == "claude-haiku-4-5"


class TestDetectSilentSwap:
    """classify-prompt._detect_silent_swap() persists swap state in the session."""

    def test_first_turn_no_last_level_clears_flag(self, session):
        # Pre-seed an old swap flag to verify it's cleared.
        session.mark_swap("haiku", "claude-opus-4-7")
        assert session.read()["swap_detected"] is True

        classify_prompt._detect_silent_swap({}, session)
        assert session.read()["swap_detected"] is False
        assert session.read()["swap_expected"] is None

    def test_match_haiku_no_swap(self, session, transcript):
        session.update("fast", "en")
        path = transcript(["claude-haiku-4-5-20251001"])
        classify_prompt._detect_silent_swap(
            {"transcript_path": str(path)}, session
        )
        assert session.read()["swap_detected"] is False

    def test_match_sonnet_no_swap(self, session, transcript):
        session.update("standard", "en")
        path = transcript(["claude-sonnet-4-6"])
        classify_prompt._detect_silent_swap(
            {"transcript_path": str(path)}, session
        )
        assert session.read()["swap_detected"] is False

    def test_match_opus_no_swap(self, session, transcript):
        session.update("deep", "en")
        path = transcript(["claude-opus-4-7"])
        classify_prompt._detect_silent_swap(
            {"transcript_path": str(path)}, session
        )
        assert session.read()["swap_detected"] is False

    def test_fast_tier_transcript_signal_is_gated_v1_8_1(self, session, transcript):
        """v1.8.1: transcript-only signal is ignored for non-deep tiers.

        The transcript's last assistant model is the HOST CC model (always
        opus in current installs), not the routed subagent. Comparing it
        against fast/standard tier expectations is a structural false
        positive, so the gate clears the flag without firing mark_swap.
        """
        session.update("fast", "en")
        path = transcript(["claude-opus-4-7"])
        classify_prompt._detect_silent_swap(
            {"transcript_path": str(path)}, session
        )
        state = session.read()
        assert state["swap_detected"] is False
        assert state["swap_expected"] is None
        assert state["swap_actual"] is None

    def test_standard_tier_transcript_signal_is_gated_v1_8_1(self, session, transcript):
        """v1.8.1: same gate applies to `standard` tier."""
        session.update("standard", "en")
        path = transcript(["claude-opus-4-7"])
        classify_prompt._detect_silent_swap(
            {"transcript_path": str(path)}, session
        )
        assert session.read()["swap_detected"] is False

    def test_fast_tier_clears_prior_swap_flag_v1_8_1(self, session, transcript):
        """Gate must clear any stale swap flag from a prior turn."""
        session.mark_swap("haiku", "claude-opus-4-7")
        session.update("fast", "en")
        path = transcript(["claude-opus-4-7"])
        classify_prompt._detect_silent_swap(
            {"transcript_path": str(path)}, session
        )
        assert session.read()["swap_detected"] is False

    def test_mismatch_deep_to_haiku(self, session, transcript):
        """Opus→haiku — CC downgraded silently."""
        session.update("deep", "en")
        path = transcript(["claude-haiku-4-5"])
        classify_prompt._detect_silent_swap(
            {"transcript_path": str(path)}, session
        )
        state = session.read()
        assert state["swap_detected"] is True
        assert state["swap_expected"] == "opus"
        assert state["swap_actual"] == "claude-haiku-4-5"

    def test_effective_model_in_stdin_wins_for_deep(self, session, transcript):
        """For deep tier, stdin's effective_model takes precedence over transcript.

        Updated in v1.8.2: non-deep tiers are gated before reading stdin,
        so this stdin-wins behavior only applies to deep routes now.
        """
        session.update("deep", "en")
        # Transcript says opus (would match expected) — stdin says haiku
        # (mismatches) → swap is detected on stdin signal.
        path = transcript(["claude-opus-4-7"])
        classify_prompt._detect_silent_swap(
            {"transcript_path": str(path), "effective_model": "claude-haiku-4-5"},
            session,
        )
        state = session.read()
        assert state["swap_detected"] is True
        assert state["swap_actual"] == "claude-haiku-4-5"

    def test_standard_tier_stdin_model_is_gated_v1_8_2(self, session):
        """v1.8.2: standard tier must gate even when stdin.model is present.

        Reproduces the production bug: CC always populates stdin.model with
        the HOST session model. The v1.8.1 gate only fired when stdin was
        empty, so standard prompts always reached the comparison branch and
        produced a false `▲swap` indicator. The v1.8.2 fix moves the gate
        BEFORE the stdin read.
        """
        session.update("standard", "en")
        classify_prompt._detect_silent_swap(
            {"effective_model": "claude-opus-4-7", "model": "claude-opus-4-7"},
            session,
        )
        state = session.read()
        assert state["swap_detected"] is False
        assert state["swap_expected"] is None
        assert state["swap_actual"] is None

    def test_fast_tier_stdin_model_is_gated_v1_8_2(self, session):
        """v1.8.2: same gate must apply to fast tier when stdin.model present."""
        session.update("fast", "en")
        classify_prompt._detect_silent_swap(
            {"model": "claude-opus-4-7"},
            session,
        )
        assert session.read()["swap_detected"] is False

    def test_missing_transcript_does_not_crash(self, session):
        session.update("fast", "en")
        classify_prompt._detect_silent_swap({"transcript_path": None}, session)
        # No actual model available → flag untouched.
        assert session.read()["swap_detected"] is False

    def test_substring_match_is_case_insensitive(self, session, transcript):
        """v1.8.2: case-insensitivity is only reachable for deep tier
        (the only tier whose comparison branch still executes)."""
        session.update("deep", "en")
        # Hypothetical capitalized model id; family substring still matches.
        path = transcript(["Claude-Opus-Future"])
        classify_prompt._detect_silent_swap(
            {"transcript_path": str(path)}, session
        )
        assert session.read()["swap_detected"] is False

    def test_match_clears_prior_swap(self, session, transcript):
        # Turn N-1: swap was detected.
        session.mark_swap("haiku", "claude-opus-4-7")
        # Turn N: poly routes deep, CC follows → expected family matches.
        session.update("deep", "en")
        path = transcript(["claude-opus-4-7"])
        classify_prompt._detect_silent_swap(
            {"transcript_path": str(path)}, session
        )
        assert session.read()["swap_detected"] is False
        assert session.read()["swap_expected"] is None
