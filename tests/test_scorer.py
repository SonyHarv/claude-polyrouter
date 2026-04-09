"""Tests for the multi-signal scoring engine (Sprint 1)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.scorer import compute_score, score_to_tier, DEFAULT_THRESHOLDS


# --- compute_score tests ---


class TestShortQueryFastTrack:
    """Short queries with no complex signals get fast-tracked."""

    def test_single_word_no_signals(self):
        score, method = compute_score("hello", {}, 1)
        assert method == "length"
        assert score == 0.05

    def test_three_words_no_signals(self):
        score, method = compute_score("how are you", {}, 3)
        assert method == "length"
        assert score == 0.05

    def test_ten_words_no_signals(self):
        score, method = compute_score("tell me about the weather today please thanks a lot", {}, 10)
        assert method == "length"
        assert score == 0.10

    def test_short_with_fast_signal_only(self):
        score, method = compute_score("hello", {"fast": 1}, 1)
        assert method == "length"
        assert score == 0.05

    def test_short_with_standard_signal_bypasses_fasttrack(self):
        score, method = compute_score("create function", {"standard": 1}, 2)
        assert method == "scoring"
        assert score >= 0.20  # should route standard

    def test_short_with_deep_signal_bypasses_fasttrack(self):
        score, method = compute_score("design architecture", {"deep": 1}, 2)
        assert method == "scoring"
        assert score >= 0.40  # should route deep

    def test_short_with_tool_signal_bypasses_fasttrack(self):
        score, method = compute_score("run tests", {"tool_intensive": 1}, 2)
        assert method == "scoring"
        assert score >= 0.20

    def test_eleven_words_not_fasttracked(self):
        score, method = compute_score(
            "tell me about the weather in the city today please sir okay",
            {}, 12,
        )
        assert method == "scoring"


class TestPatternSignals:
    """Pattern-based signals dominate the scoring."""

    def test_deep_plus_tool_max_score(self):
        score, _ = compute_score("x", {"deep": 1, "tool_intensive": 1}, 20)
        assert score >= 0.50

    def test_deep_plus_orch_max_score(self):
        score, _ = compute_score("x", {"deep": 1, "orchestration": 1}, 20)
        assert score >= 0.50

    def test_double_deep(self):
        score, _ = compute_score("x", {"deep": 2}, 20)
        assert 0.45 <= score <= 0.55

    def test_single_deep(self):
        score, _ = compute_score("x", {"deep": 1}, 20)
        assert 0.40 <= score <= 0.50

    def test_double_standard(self):
        score, _ = compute_score("x", {"standard": 2}, 20)
        assert 0.30 <= score <= 0.40

    def test_single_standard_plus_tool(self):
        score, _ = compute_score("x", {"standard": 1, "tool_intensive": 1}, 20)
        assert 0.28 <= score <= 0.38

    def test_single_standard(self):
        score, _ = compute_score("x", {"standard": 1}, 20)
        assert 0.24 <= score <= 0.34

    def test_single_tool(self):
        score, _ = compute_score("x", {"tool_intensive": 1}, 20)
        assert 0.20 <= score <= 0.30

    def test_single_orch(self):
        score, _ = compute_score("x", {"orchestration": 1}, 20)
        assert 0.24 <= score <= 0.34

    def test_fast_only(self):
        score, _ = compute_score("x", {"fast": 1}, 20)
        assert score < 0.10

    def test_no_signals(self):
        score, _ = compute_score("a medium length query with no matches at all here", {}, 20)
        assert score < 0.05


class TestStructuralSignals:
    """Code blocks, error traces, file paths boost the score."""

    def test_code_blocks_boost(self):
        query_no_code = "implement sorting"
        query_with_code = "implement sorting ```python\ndef sort():\n  pass\n```"
        score_no, _ = compute_score(query_no_code, {"standard": 1}, 20)
        score_yes, _ = compute_score(query_with_code, {"standard": 1}, 20)
        assert score_yes > score_no

    def test_multiple_code_blocks_capped(self):
        query = "fix ```a``` and ```b``` and ```c```"
        score, _ = compute_score(query, {"standard": 1}, 20)
        # 3 blocks = 6 backtick-triplets // 2 = 3. Capped at 0.08.
        assert score < 0.50  # shouldn't push standard into deep

    def test_error_trace_boost(self):
        query_clean = "fix the login handler"
        query_error = "fix the login handler Error: connection refused"
        score_clean, _ = compute_score(query_clean, {"standard": 1}, 20)
        score_error, _ = compute_score(query_error, {"standard": 1}, 20)
        assert score_error > score_clean

    def test_traceback_detection(self):
        query = "Traceback (most recent call last): fix this"
        score, _ = compute_score(query, {"standard": 1}, 20)
        assert score > 0.30

    def test_file_path_boost(self):
        query_no = "fix the handler"
        query_yes = "fix src/handlers/auth.ts"
        score_no, _ = compute_score(query_no, {"standard": 1}, 20)
        score_yes, _ = compute_score(query_yes, {"standard": 1}, 20)
        assert score_yes > score_no

    def test_long_prompt_slight_boost(self):
        short = "fix bug"
        long = "fix bug " + "with detailed context " * 50
        score_short, _ = compute_score(short, {"standard": 1}, 20)
        score_long, _ = compute_score(long, {"standard": 1}, 20)
        assert score_long > score_short


class TestContextSignals:
    """Session context enriches the scoring."""

    def test_no_context(self):
        score_none, _ = compute_score("x", {"standard": 1}, 20, context=None)
        score_empty, _ = compute_score("x", {"standard": 1}, 20, context={})
        assert score_none == score_empty

    def test_tool_result_length_boost(self):
        score_low, _ = compute_score("x", {"standard": 1}, 20, context={"last_tool_result_len": 0})
        score_high, _ = compute_score("x", {"standard": 1}, 20, context={"last_tool_result_len": 40000})
        assert score_high > score_low

    def test_conversation_depth_boost(self):
        score_new, _ = compute_score("x", {"standard": 1}, 20, context={"conversation_depth": 0})
        score_deep, _ = compute_score("x", {"standard": 1}, 20, context={"conversation_depth": 8})
        assert score_deep > score_new

    def test_effort_high_boosts(self):
        score_low, _ = compute_score("x", {"standard": 1}, 20, context={"effort_level": "low"})
        score_high, _ = compute_score("x", {"standard": 1}, 20, context={"effort_level": "high"})
        assert score_high > score_low

    def test_effort_max_same_as_high(self):
        score_high, _ = compute_score("x", {"standard": 1}, 20, context={"effort_level": "high"})
        score_max, _ = compute_score("x", {"standard": 1}, 20, context={"effort_level": "max"})
        assert score_max == score_high

    def test_context_never_dominates(self):
        """Context alone cannot push a no-signal query into standard tier."""
        score, _ = compute_score(
            "short query here",
            {},
            20,
            context={"last_tool_result_len": 50000, "conversation_depth": 10, "effort_level": "high"},
        )
        assert score < 0.20  # still fast


# --- score_to_tier tests ---


class TestScoreToTier:
    def test_zero_is_fast(self):
        tier, conf = score_to_tier(0.0)
        assert tier == "fast"
        assert conf >= 0.80

    def test_low_score_is_fast(self):
        tier, _ = score_to_tier(0.10)
        assert tier == "fast"

    def test_boundary_fast_standard(self):
        tier, _ = score_to_tier(0.20)
        assert tier == "standard"

    def test_mid_standard(self):
        tier, _ = score_to_tier(0.30)
        assert tier == "standard"

    def test_boundary_standard_deep(self):
        tier, _ = score_to_tier(0.40)
        assert tier == "deep"

    def test_high_score_is_deep(self):
        tier, _ = score_to_tier(0.60)
        assert tier == "deep"

    def test_max_score_is_deep(self):
        tier, conf = score_to_tier(1.0)
        assert tier == "deep"
        assert conf == 0.95

    def test_confidence_higher_far_from_boundary(self):
        _, conf_edge = score_to_tier(0.20)  # exactly at standard boundary
        _, conf_mid = score_to_tier(0.30)  # middle of standard
        assert conf_mid > conf_edge

    def test_deep_high_confidence_for_strong_score(self):
        _, conf = score_to_tier(0.50)
        assert conf >= 0.85

    def test_custom_thresholds(self):
        custom = {"fast_max": 0.30, "standard_max": 0.60}
        tier, _ = score_to_tier(0.25, thresholds=custom)
        assert tier == "fast"  # 0.25 < 0.30 custom threshold

    def test_confidence_capped_at_095(self):
        _, conf = score_to_tier(0.0)
        assert conf <= 0.95


# --- Integration: score → tier mapping ---


class TestScoringEndToEnd:
    """Verify that the full scoring pipeline produces expected tier mappings."""

    def test_fast_query(self):
        score, _ = compute_score("hello", {"fast": 1}, 1)
        tier, _ = score_to_tier(score)
        assert tier == "fast"

    def test_standard_query(self):
        score, _ = compute_score(
            "create a function for sorting arrays",
            {"standard": 1},
            20,
        )
        tier, _ = score_to_tier(score)
        assert tier == "standard"

    def test_deep_query(self):
        score, _ = compute_score(
            "design the architecture for a distributed system",
            {"deep": 1},
            20,
        )
        tier, _ = score_to_tier(score)
        assert tier == "deep"

    def test_deep_with_tool_high_confidence(self):
        score, _ = compute_score(
            "design the architecture and run tests for the entire project",
            {"deep": 1, "tool_intensive": 1},
            20,
        )
        tier, conf = score_to_tier(score)
        assert tier == "deep"
        assert conf >= 0.90

    def test_standard_with_error_trace(self):
        score, _ = compute_score(
            "fix this error: TypeError: cannot read property of undefined",
            {"standard": 1},
            20,
        )
        tier, _ = score_to_tier(score)
        assert tier == "standard"

    def test_standard_with_code_block(self):
        score, _ = compute_score(
            "implement this ```def sort(arr): pass```",
            {"standard": 1},
            20,
        )
        tier, _ = score_to_tier(score)
        assert tier == "standard"

    def test_context_can_tip_borderline(self):
        """A borderline standard query with deep context tips into deep."""
        # std=2 gives ~0.32, plus deep context might push past 0.40
        score_no_ctx, _ = compute_score("x", {"standard": 2}, 20)
        score_ctx, _ = compute_score(
            "x",
            {"standard": 2},
            20,
            context={"last_tool_result_len": 50000, "conversation_depth": 10, "effort_level": "high"},
        )
        assert score_ctx > score_no_ctx
