"""Tests for MicroCompact + SessionMemoryCompact advisory system (Sprint 4)."""

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.compact import (
    COMPACTABLE_TOOLS,
    KEEP_LAST_N,
    MAX_CONSECUTIVE_FAILURES,
    SM_MIN_MESSAGES,
    SM_MIN_TOKENS,
    CompactAdvisor,
    MicroCompact,
    SessionMemoryCompact,
    load_compact_state,
    save_compact_state,
    _default_state,
    COMPACT_STATE_FILE,
)


# ── MicroCompact ──────────────────────────────────────────────────────


class TestMicroCompactRecording:
    def test_record_compactable_tool(self):
        state = _default_state()
        MicroCompact.record_tool_use(state, "Read")
        assert state["tool_result_count"] == 1
        assert state["compactable_count"] == 1

    def test_record_non_compactable_tool(self):
        state = _default_state()
        MicroCompact.record_tool_use(state, "Agent")
        assert state["tool_result_count"] == 1
        assert state["compactable_count"] == 0

    def test_all_compactable_tools_tracked(self):
        state = _default_state()
        for tool in COMPACTABLE_TOOLS:
            MicroCompact.record_tool_use(state, tool)
        assert state["compactable_count"] == len(COMPACTABLE_TOOLS)

    def test_increments_correctly(self):
        state = _default_state()
        for _ in range(10):
            MicroCompact.record_tool_use(state, "Bash")
        assert state["compactable_count"] == 10
        assert state["tool_result_count"] == 10


class TestMicroCompactCheck:
    def test_no_advisory_under_threshold(self):
        mc = MicroCompact()
        state = _default_state()
        state["compactable_count"] = KEEP_LAST_N
        assert mc.check(state) is None

    def test_no_advisory_zero(self):
        mc = MicroCompact()
        assert mc.check(_default_state()) is None

    def test_advisory_when_stale(self):
        mc = MicroCompact()
        state = _default_state()
        state["compactable_count"] = KEEP_LAST_N + 3
        result = mc.check(state)
        assert result is not None
        assert "3" in result
        assert "polyrouter:compact" in result

    def test_advisory_exactly_one_over(self):
        mc = MicroCompact()
        state = _default_state()
        state["compactable_count"] = KEEP_LAST_N + 1
        result = mc.check(state)
        assert "1" in result

    def test_custom_keep_last_n(self):
        mc = MicroCompact(keep_last_n=2)
        state = _default_state()
        state["compactable_count"] = 3
        assert mc.check(state) is not None

    def test_keep_last_n_minimum_one(self):
        mc = MicroCompact(keep_last_n=0)
        assert mc._keep_last_n == 1


# ── SessionMemoryCompact ──────────────────────────────────────────────


class TestSessionMemoryCompact:
    def test_no_advisory_low_tokens(self):
        smc = SessionMemoryCompact()
        state = _default_state()
        state["last_token_estimate"] = 5000
        state["last_message_count"] = 10
        assert smc.check(state) is None

    def test_no_advisory_low_messages(self):
        smc = SessionMemoryCompact()
        state = _default_state()
        state["last_token_estimate"] = 20000
        state["last_message_count"] = 2
        assert smc.check(state) is None

    def test_advisory_when_both_above_min(self):
        smc = SessionMemoryCompact()
        state = _default_state()
        state["last_token_estimate"] = SM_MIN_TOKENS + 1000
        state["last_message_count"] = SM_MIN_MESSAGES + 1
        result = smc.check(state)
        assert result is not None
        assert "polyrouter:compact" in result
        assert "compact" in result.lower()

    def test_exactly_at_min_tokens(self):
        smc = SessionMemoryCompact()
        state = _default_state()
        state["last_token_estimate"] = SM_MIN_TOKENS
        state["last_message_count"] = SM_MIN_MESSAGES + 1
        assert smc.check(state) is not None

    def test_custom_thresholds(self):
        smc = SessionMemoryCompact(min_tokens=100, min_messages=2)
        state = _default_state()
        state["last_token_estimate"] = 150
        state["last_message_count"] = 3
        assert smc.check(state) is not None


# ── CompactAdvisor ────────────────────────────────────────────────────


class TestCompactAdvisorOrchestration:
    def test_disabled_returns_none(self):
        advisor = CompactAdvisor({"compact": {"enabled": False}})
        state = _default_state()
        state["compactable_count"] = 100
        assert advisor.get_advisory(state) is None

    def test_microcompact_priority_over_session(self):
        """MicroCompact fires first when both would trigger."""
        advisor = CompactAdvisor()
        state = _default_state()
        state["compactable_count"] = KEEP_LAST_N + 5
        state["last_token_estimate"] = SM_MIN_TOKENS + 5000
        state["last_message_count"] = SM_MIN_MESSAGES + 5
        result = advisor.get_advisory(state)
        assert "old tool results" in result

    def test_session_memory_fires_when_micro_quiet(self):
        """SessionMemory fires when MicroCompact has nothing to report."""
        advisor = CompactAdvisor()
        state = _default_state()
        state["compactable_count"] = 2  # under KEEP_LAST_N
        state["last_token_estimate"] = SM_MIN_TOKENS + 5000
        state["last_message_count"] = SM_MIN_MESSAGES + 5
        result = advisor.get_advisory(state)
        assert "context limits" in result

    def test_neither_fires(self):
        advisor = CompactAdvisor()
        state = _default_state()
        assert advisor.get_advisory(state) is None


class TestCompactAdvisorCircuitBreaker:
    def test_breaker_trips_after_max_failures(self):
        advisor = CompactAdvisor()
        state = _default_state()
        state["compactable_count"] = 20

        for _ in range(MAX_CONSECUTIVE_FAILURES):
            advisor.record_attempt(state, success=False)

        assert state["breaker_tripped"] is True
        assert advisor.get_advisory(state) is None

    def test_success_resets_consecutive_failures(self):
        advisor = CompactAdvisor()
        state = _default_state()

        advisor.record_attempt(state, success=False)
        advisor.record_attempt(state, success=False)
        advisor.record_attempt(state, success=True)

        assert state["consecutive_failures"] == 0
        assert state["breaker_tripped"] is False
        assert state["compact_successes"] == 1

    def test_success_updates_timestamp(self):
        advisor = CompactAdvisor()
        state = _default_state()
        before = time.time()
        advisor.record_attempt(state, success=True)
        assert state["last_compact_time"] >= before

    def test_already_tripped_stays_tripped(self):
        advisor = CompactAdvisor()
        state = _default_state()
        state["breaker_tripped"] = True
        state["compactable_count"] = 100
        assert advisor.get_advisory(state) is None

    def test_custom_circuit_breaker_max(self):
        advisor = CompactAdvisor({"compact": {"circuit_breaker_max": 1}})
        state = _default_state()
        state["compactable_count"] = 20
        advisor.record_attempt(state, success=False)
        assert state["breaker_tripped"] is True

    def test_record_tool_use_delegates(self):
        advisor = CompactAdvisor()
        state = _default_state()
        advisor.record_tool_use(state, "Read")
        assert state["compactable_count"] == 1


# ── State persistence ─────────────────────────────────────────────────


class TestStatePersistence:
    def test_load_returns_default_when_missing(self, tmp_path):
        fake_path = tmp_path / "missing.json"
        with patch("lib.compact.COMPACT_STATE_FILE", fake_path):
            state = load_compact_state()
        assert state == _default_state()

    def test_save_and_load_roundtrip(self, tmp_path):
        fake_path = tmp_path / "compact.json"
        with patch("lib.compact.COMPACT_STATE_FILE", fake_path):
            state = _default_state()
            state["compactable_count"] = 42
            save_compact_state(state)
            loaded = load_compact_state()
        assert loaded["compactable_count"] == 42

    def test_corrupted_file_returns_default(self, tmp_path):
        fake_path = tmp_path / "compact.json"
        fake_path.write_text("not json", encoding="utf-8")
        with patch("lib.compact.COMPACT_STATE_FILE", fake_path):
            state = load_compact_state()
        assert state == _default_state()

    def test_non_dict_returns_default(self, tmp_path):
        fake_path = tmp_path / "compact.json"
        fake_path.write_text("[1,2,3]", encoding="utf-8")
        with patch("lib.compact.COMPACT_STATE_FILE", fake_path):
            state = load_compact_state()
        assert state == _default_state()
