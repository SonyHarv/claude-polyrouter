"""Tests for dynamic effort mapping (Sprint 2)."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.effort import (
    compute_effort,
    compute_deep_effort,
    normalize_effort_for_env,
    requires_advisor,
    maybe_promote_to_deep_xhigh,
    EFFORT_MAP,
    VALID_EFFORTS,
    DISPLAY_EFFORTS,
)


class TestTierMapping:
    """Tier → effort mapping without overrides."""

    def test_fast_maps_to_low(self):
        assert compute_effort("fast") == "low"

    def test_standard_maps_to_medium(self):
        assert compute_effort("standard") == "medium"

    def test_deep_maps_to_high(self):
        assert compute_effort("deep") == "high"

    def test_unknown_tier_defaults_to_medium(self):
        assert compute_effort("unknown") == "medium"

    def test_empty_tier_defaults_to_medium(self):
        assert compute_effort("") == "medium"


class TestUserOverride:
    """User override always takes priority."""

    def test_override_low(self):
        assert compute_effort("deep", user_override="low") == "low"

    def test_override_high_on_fast_tier(self):
        assert compute_effort("fast", user_override="high") == "high"

    def test_override_max_falls_back_to_high(self):
        assert compute_effort("standard", user_override="max") == "high"

    def test_override_medium(self):
        assert compute_effort("deep", user_override="medium") == "medium"

    def test_invalid_override_ignored(self):
        assert compute_effort("deep", user_override="turbo") == "high"

    def test_empty_override_ignored(self):
        assert compute_effort("fast", user_override="") == "low"

    def test_none_override_ignored(self):
        assert compute_effort("fast", user_override=None) == "low"


class TestEnvOverride:
    """Environment variable is second priority after user override."""

    @patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": "max"})
    def test_env_max_falls_back_to_high(self):
        assert compute_effort("fast") == "high"

    @patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": "low"})
    def test_env_low_overrides_deep(self):
        assert compute_effort("deep") == "low"

    @patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": "high"})
    def test_user_override_beats_env(self):
        assert compute_effort("fast", user_override="low") == "low"

    @patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": "invalid"})
    def test_invalid_env_ignored(self):
        assert compute_effort("standard") == "medium"

    @patch.dict(os.environ, {}, clear=True)
    def test_no_env_falls_through(self):
        # Ensure CLAUDE_CODE_EFFORT_LEVEL is not set
        os.environ.pop("CLAUDE_CODE_EFFORT_LEVEL", None)
        assert compute_effort("deep") == "high"


class TestConstants:
    """Verify constants are correct."""

    def test_all_tiers_have_mapping(self):
        for tier in ("fast", "standard", "deep"):
            assert tier in EFFORT_MAP

    def test_all_mappings_are_valid(self):
        for effort in EFFORT_MAP.values():
            assert effort in VALID_EFFORTS

    def test_valid_efforts_complete(self):
        assert VALID_EFFORTS == {"low", "medium", "high"}

    def test_display_efforts_include_xhigh(self):
        assert DISPLAY_EFFORTS == {"low", "medium", "high", "xhigh"}


class TestDynamicDeepEffort:
    """compute_deep_effort classifies deep-tier complexity sub-levels."""

    def test_single_deep_no_combo_is_medium(self):
        assert compute_deep_effort(
            score=0.70, signals={"deep": 1}, query="debug this function", word_count=4,
        ) == "medium"

    def test_bare_deep_spanish_is_medium(self):
        assert compute_deep_effort(
            score=0.68, signals={"deep": 1}, query="arregla este bug por favor", word_count=5,
        ) == "medium"

    def test_deep_plus_standard_is_high(self):
        assert compute_deep_effort(
            score=0.72, signals={"deep": 1, "standard": 1}, query="fix auth logic", word_count=3,
        ) == "high"

    def test_deep_plus_tool_is_high(self):
        assert compute_deep_effort(
            score=0.72, signals={"deep": 1, "tool_intensive": 1}, query="run tests and debug", word_count=4,
        ) == "high"

    def test_deep_plus_orchestration_is_high(self):
        assert compute_deep_effort(
            score=0.72, signals={"deep": 1, "orchestration": 1}, query="coordina pruebas", word_count=2,
        ) == "high"

    def test_double_deep_is_high(self):
        assert compute_deep_effort(
            score=0.72, signals={"deep": 2}, query="refactor audit module", word_count=3,
        ) == "high"

    def test_score_over_80_is_high(self):
        assert compute_deep_effort(
            score=0.82, signals={"deep": 1}, query="refactor this module", word_count=4,
        ) == "high"

    def test_two_files_plus_deep_is_high(self):
        assert compute_deep_effort(
            score=0.70,
            signals={"deep": 1},
            query="update auth.py and login.py",
            word_count=5,
        ) == "high"

    def test_two_code_blocks_plus_deep_is_high(self):
        query = "refactor this:\n```\nfoo\n```\nand this:\n```\nbar\n```"
        assert compute_deep_effort(
            score=0.70, signals={"deep": 1}, query=query, word_count=8,
        ) == "high"

    def test_architecture_keyword_en_is_xhigh(self):
        assert compute_deep_effort(
            score=0.70,
            signals={"deep": 1},
            query="design the authentication architecture",
            word_count=5,
        ) == "xhigh"

    def test_architecture_keyword_es_is_xhigh(self):
        assert compute_deep_effort(
            score=0.70,
            signals={"deep": 1},
            query="diseña la arquitectura del sistema de pagos",
            word_count=7,
        ) == "xhigh"

    def test_system_design_is_xhigh(self):
        assert compute_deep_effort(
            score=0.70,
            signals={"orchestration": 1},
            query="new system design for caching layer",
            word_count=7,
        ) == "xhigh"

    def test_major_refactor_is_xhigh(self):
        assert compute_deep_effort(
            score=0.72,
            signals={"deep": 1},
            query="plan a major refactor across services",
            word_count=7,
        ) == "xhigh"

    def test_redesign_spanish_is_xhigh(self):
        assert compute_deep_effort(
            score=0.70,
            signals={"deep": 1},
            query="rediseño completo del módulo de auth",
            word_count=6,
        ) == "xhigh"

    def test_migration_strategy_is_xhigh(self):
        assert compute_deep_effort(
            score=0.72,
            signals={"deep": 1},
            query="define migration strategy for legacy DB",
            word_count=6,
        ) == "xhigh"

    def test_orchestration_plus_deep_plus_three_files_is_xhigh(self):
        assert compute_deep_effort(
            score=0.75,
            signals={"deep": 1, "orchestration": 1},
            query="refactor auth.py login.py session.py together",
            word_count=6,
        ) == "xhigh"

    def test_score_over_85_with_long_prompt_is_xhigh(self):
        long_query = " ".join(["refactor"] * 85)
        assert compute_deep_effort(
            score=0.88, signals={"deep": 1}, query=long_query, word_count=85,
        ) == "xhigh"

    def test_score_over_85_but_short_prompt_not_xhigh(self):
        result = compute_deep_effort(
            score=0.88, signals={"deep": 1}, query="fix bug", word_count=2,
        )
        assert result == "high"

    def test_handles_missing_signals(self):
        assert compute_deep_effort(
            score=0.65, signals={}, query="fix", word_count=1,
        ) == "medium"

    def test_handles_non_dict_signals(self):
        assert compute_deep_effort(
            score=0.65, signals=None, query="fix", word_count=1,
        ) == "medium"

    def test_handles_non_string_query(self):
        assert compute_deep_effort(
            score=0.65, signals={"deep": 1}, query=None, word_count=0,
        ) == "medium"


class TestNormalizeForEnv:
    """normalize_effort_for_env maps display labels to CC-valid values."""

    def test_xhigh_normalizes_to_high(self):
        assert normalize_effort_for_env("xhigh") == "high"

    def test_high_stays_high(self):
        assert normalize_effort_for_env("high") == "high"

    def test_medium_stays_medium(self):
        assert normalize_effort_for_env("medium") == "medium"

    def test_low_stays_low(self):
        assert normalize_effort_for_env("low") == "low"

    def test_unknown_falls_back_to_medium(self):
        assert normalize_effort_for_env("ultra") == "medium"


class TestRequiresAdvisor:
    """requires_advisor flags xhigh as the Advisor trigger."""

    def test_xhigh_requires_advisor(self):
        assert requires_advisor("xhigh") is True

    def test_high_does_not(self):
        assert requires_advisor("high") is False

    def test_medium_does_not(self):
        assert requires_advisor("medium") is False

    def test_low_does_not(self):
        assert requires_advisor("low") is False


class TestArchPromotion:
    """maybe_promote_to_deep_xhigh lifts standard → deep when arch keyword
    co-occurs with at least one standard/tool/orch signal."""

    def test_major_refactor_promotes_standard(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"standard": 2},
            "plan a major refactor across all our microservices",
        )
        assert tier == "deep"
        assert promoted is True

    def test_architecture_en_promotes(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"standard": 1},
            "rework the system architecture for scaling",
        )
        assert tier == "deep"
        assert promoted is True

    def test_redesign_conjugation_es_promotes(self):
        # "rediseña" is a verb form not matched by the old regex.
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"standard": 1},
            "rediseña el módulo de pagos",
        )
        assert tier == "deep"
        assert promoted is True

    def test_migration_strategy_promotes(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"tool_intensive": 1},
            "define migration strategy for the database",
        )
        assert tier == "deep"
        assert promoted is True

    def test_arch_keyword_without_signals_does_not_promote(self):
        # Guard: avoid false positives on questions like "what is architecture?"
        tier, promoted = maybe_promote_to_deep_xhigh(
            "fast",
            {},
            "what is software architecture",
        )
        assert tier == "fast"
        assert promoted is False

    def test_signals_without_arch_keyword_does_not_promote(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"standard": 3},
            "refactor the login function",
        )
        assert tier == "standard"
        assert promoted is False

    def test_already_deep_never_promotes(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "deep",
            {"deep": 1, "standard": 1},
            "redesign the payments architecture",
        )
        assert tier == "deep"
        assert promoted is False

    def test_handles_non_dict_signals(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard", None, "major refactor across services",
        )
        assert tier == "standard"
        assert promoted is False

    def test_handles_non_string_query(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard", {"standard": 1}, None,
        )
        assert tier == "standard"
        assert promoted is False
