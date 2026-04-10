"""Tests for dynamic effort mapping (Sprint 2)."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.effort import compute_effort, EFFORT_MAP, VALID_EFFORTS


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
