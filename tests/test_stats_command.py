"""Tests for v1.7 ADICIONAL #9: per-session routing breakdown.

Covers:
- SessionState.record_route / reset_routing_stats / inc_retry_invocations.
- _build_stats_block: render correctness, empty session, mini-bar widths.
- _detect_stats_command: marker detection, reset arg routing.
- End-to-end: classifying prompts through the simulated paths populates
  the breakdown counters as expected.
"""

import importlib.util
import re
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

_STATS_MARKER = classify_prompt._STATS_MARKER
_BAR_WIDTH = classify_prompt._BAR_WIDTH
_BAR_FILL = classify_prompt._BAR_FILL
_BAR_EMPTY = classify_prompt._BAR_EMPTY


@pytest.fixture
def session(tmp_path):
    return SessionState(tmp_path / "session.json")


class TestRecordRouteCounters:
    """SessionState.record_route accumulates the right buckets."""

    def test_fast_increments_fast_bucket(self, session):
        session.record_route("fast", None, "scoring", "en", 0.01)
        state = session.read()
        assert state["routing_counts"]["fast"] == 1
        assert state["routing_counts"]["standard"] == 0
        assert sum(state["routing_counts"][k] for k in (
            "deep_medium", "deep_high", "deep_xhigh",
        )) == 0
        assert state["routing_method_counts"] == {"scoring": 1}
        assert state["routing_lang_counts"] == {"en": 1}
        assert state["routing_savings_total"] == pytest.approx(0.01)

    def test_deep_with_effort_buckets_correctly(self, session):
        session.record_route("deep", "medium", "arch", "en", 0.0)
        session.record_route("deep", "high", "arch", "en", 0.0)
        session.record_route("deep", "xhigh", "arch", "en", 0.0)
        state = session.read()
        assert state["routing_counts"]["deep_medium"] == 1
        assert state["routing_counts"]["deep_high"] == 1
        assert state["routing_counts"]["deep_xhigh"] == 1

    def test_deep_unknown_effort_falls_to_medium(self, session):
        session.record_route("deep", None, "arch", "en", 0.0)
        session.record_route("deep", "weird", "arch", "en", 0.0)
        assert session.read()["routing_counts"]["deep_medium"] == 2

    def test_unknown_level_does_not_crash(self, session):
        # Should silently drop — never raise on routing record.
        session.record_route("garbage", None, "x", "en", 0.0)
        assert sum(session.read()["routing_counts"].values()) == 0

    def test_routing_started_at_set_on_first_record(self, session):
        assert session.read()["routing_started_at"] is None
        session.record_route("fast", None, "scoring", "en", 0.01)
        first_ts = session.read()["routing_started_at"]
        assert isinstance(first_ts, float)
        # Subsequent records do not overwrite the started_at.
        session.record_route("fast", None, "scoring", "en", 0.01)
        assert session.read()["routing_started_at"] == first_ts

    def test_savings_accumulates(self, session):
        session.record_route("fast", None, "scoring", "en", 0.01)
        session.record_route("fast", None, "scoring", "en", 0.02)
        assert session.read()["routing_savings_total"] == pytest.approx(0.03)

    def test_negative_savings_clamped(self, session):
        session.record_route("fast", None, "scoring", "en", -5.0)
        assert session.read()["routing_savings_total"] == pytest.approx(0.0)


class TestRetryAndReset:
    """Retry-invocation counter and reset_routing_stats wipe semantics."""

    def test_inc_retry_invocations(self, session):
        for _ in range(3):
            session.inc_retry_invocations()
        assert session.read()["retry_invocations"] == 3

    def test_reset_routing_stats(self, session):
        session.record_route("fast", None, "scoring", "en", 0.01)
        session.record_route("deep", "xhigh", "arch", "es", 0.0)
        session.inc_retry_invocations()
        assert session.read()["routing_started_at"] is not None
        session.reset_routing_stats()
        state = session.read()
        assert state["routing_started_at"] is None
        assert all(v == 0 for v in state["routing_counts"].values())
        assert state["routing_method_counts"] == {}
        assert state["routing_lang_counts"] == {}
        assert state["routing_savings_total"] == 0.0
        assert state["retry_invocations"] == 0

    def test_reset_does_not_touch_other_session_state(self, session):
        # Plant unrelated session fields and confirm reset preserves them.
        session.update("standard", "en")
        session.update_effort("high")
        session.set_advisor(True)
        session.record_route("standard", None, "cache(rules)", "en", 0.0)

        session.reset_routing_stats()
        state = session.read()
        assert state["last_level"] == "standard"
        assert state["effort_level"] == "high"
        assert state["requires_advisor"] is True


class TestBuildStatsBlock:
    """_build_stats_block renders the well-known mini-bar format."""

    def test_empty_session_emits_no_data_line(self, session):
        block = classify_prompt._build_stats_block(session)
        assert "[POLY:STATS]" in block
        assert "no routes recorded" in block

    def test_block_contains_each_tier_row(self, session):
        session.record_route("fast", None, "scoring", "en", 0.01)
        session.record_route("standard", None, "cache(rules)", "en", 0.0)
        session.record_route("deep", "xhigh", "arch", "es", 0.0)
        block = classify_prompt._build_stats_block(session)
        for label in ("fast", "standard", "deep·medium", "deep·high", "deep·xhigh"):
            assert label in block

    def test_block_includes_methods_languages_savings_retries(self, session):
        session.record_route("fast", None, "scoring", "en", 0.01)
        session.record_route("standard", None, "cache(rules)", "es", 0.0)
        session.inc_retry_invocations()
        block = classify_prompt._build_stats_block(session)
        assert "Top methods:" in block
        assert "scoring" in block
        assert "cache(rules)" in block
        assert "Languages:" in block
        assert "en" in block and "es" in block
        assert "Savings:" in block
        assert "Retries:" in block
        assert "1 invocation" in block

    def test_bar_widths_are_fixed(self, session):
        # Single 100% record → its bar is fully filled at _BAR_WIDTH.
        session.record_route("fast", None, "scoring", "en", 0.0)
        block = classify_prompt._build_stats_block(session)
        # The fast row contains _BAR_FILL repeated _BAR_WIDTH times.
        assert (_BAR_FILL * _BAR_WIDTH) in block

    def test_bar_renders_proportional_fill(self, session):
        # 4:1 fast:standard → fast bar ~80%, standard ~20%.
        for _ in range(4):
            session.record_route("fast", None, "scoring", "en", 0.0)
        session.record_route("standard", None, "scoring", "en", 0.0)
        block = classify_prompt._build_stats_block(session)
        assert "80.0%" in block
        assert "20.0%" in block

    def test_session_clock_and_age_lines_present(self, session):
        session.record_route("fast", None, "scoring", "en", 0.0)
        block = classify_prompt._build_stats_block(session)
        assert re.search(r"Session: \d+ routes since \d{2}:\d{2}", block)


class TestDetectStatsCommand:
    """_detect_stats_command marker / reset / no-marker handling."""

    def test_no_marker_returns_none(self, session):
        assert classify_prompt._detect_stats_command("normal prompt", session) is None

    def test_marker_emits_breakdown(self, session):
        session.record_route("fast", None, "scoring", "en", 0.0)
        out = classify_prompt._detect_stats_command(_STATS_MARKER, session)
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "[POLY:STATS]" in ctx
        assert "fast" in ctx
        # Slash-command turn must NOT spawn a subagent.
        assert "Spawn" not in ctx
        assert "Route:" not in ctx

    def test_marker_with_reset_zeros_counters(self, session):
        session.record_route("fast", None, "scoring", "en", 0.05)
        session.inc_retry_invocations()
        prompt = f"{_STATS_MARKER}\nreset"
        out = classify_prompt._detect_stats_command(prompt, session)
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Reset complete" in ctx
        state = session.read()
        assert state["routing_started_at"] is None
        assert all(v == 0 for v in state["routing_counts"].values())
        assert state["retry_invocations"] == 0
        assert state["routing_savings_total"] == 0.0

    def test_marker_reset_case_insensitive(self, session):
        session.record_route("fast", None, "scoring", "en", 0.0)
        prompt = f"{_STATS_MARKER}\nRESET please"
        out = classify_prompt._detect_stats_command(prompt, session)
        assert "Reset complete" in out["hookSpecificOutput"]["additionalContext"]


class TestFormatHelpers:
    """Ancillary formatters used by the breakdown builder."""

    def test_ascii_bar_full(self):
        bar = classify_prompt._ascii_bar(1.0)
        assert bar == _BAR_FILL * _BAR_WIDTH

    def test_ascii_bar_empty(self):
        bar = classify_prompt._ascii_bar(0.0)
        assert bar == _BAR_EMPTY * _BAR_WIDTH

    def test_ascii_bar_half(self):
        bar = classify_prompt._ascii_bar(0.5, width=10)
        assert bar.count(_BAR_FILL) == 5
        assert bar.count(_BAR_EMPTY) == 5

    def test_ascii_bar_clamps_out_of_range(self):
        # Out-of-range fractions render as fully empty (defensive).
        assert classify_prompt._ascii_bar(-0.1) == _BAR_EMPTY * _BAR_WIDTH
        assert classify_prompt._ascii_bar(1.5) == _BAR_EMPTY * _BAR_WIDTH

    def test_format_top_freq_orders_by_count(self):
        d = {"a": 1, "b": 5, "c": 3}
        result = classify_prompt._format_top_freq(d, top_n=3)
        # b (5) first, then c (3), then a (1).
        assert result.index("b") < result.index("c") < result.index("a")

    def test_format_top_freq_truncates_to_top_n(self):
        d = {f"k{i}": i for i in range(10)}
        result = classify_prompt._format_top_freq(d, top_n=3)
        # Only 3 entries → 2 separators.
        assert result.count("·") == 2

    def test_format_top_freq_handles_empty(self):
        assert classify_prompt._format_top_freq({}) == "(none)"

    def test_format_duration_buckets(self):
        assert classify_prompt._format_duration(30) == "<1m"
        assert classify_prompt._format_duration(60) == "1m"
        assert classify_prompt._format_duration(125) == "2m 5s"
        assert classify_prompt._format_duration(3600) == "1h"
        assert classify_prompt._format_duration(3725) == "1h 2m"
