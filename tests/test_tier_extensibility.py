"""Tier extensibility tests (CALIDAD #16).

Demonstrates that adding a new tier (e.g. "ultra") to config.json works
end-to-end without code changes in scorer.py / effort.py.

Each test simulates a config with an `ultra` tier appended after `deep`
and asserts:
  - score_to_tier walks tier_order and routes high-score prompts to ultra
  - effort_for_tier reads default_effort from the config block
  - validate_config emits warnings for malformed setups
  - savings calc tolerates pricing=null on the new tier
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.config import DEFAULT_CONFIG, validate_config
from lib.effort import EFFORT_MAP, effort_for_tier
from lib.scorer import DEFAULT_THRESHOLDS, DEFAULT_TIER_ORDER, score_to_tier


# --- Fixtures ---


def _make_ultra_config(*, ultra_pricing: dict | None = None) -> dict:
    """Build a config dict with a fourth `ultra` tier appended."""
    cfg = {
        "tier_order": ["fast", "standard", "deep", "ultra"],
        "levels": {
            "fast": {
                "model": "haiku",
                "agent": "fast-executor",
                "default_effort": "low",
                "cost_per_1k_input": 0.001,
                "cost_per_1k_output": 0.005,
            },
            "standard": {
                "model": "sonnet",
                "agent": "standard-executor",
                "default_effort": "medium",
                "cost_per_1k_input": 0.003,
                "cost_per_1k_output": 0.015,
            },
            "deep": {
                "model": "opus",
                "agent": "deep-executor",
                "default_effort": "high",
                "cost_per_1k_input": 0.015,
                "cost_per_1k_output": 0.075,
            },
            "ultra": {
                "model": "opus-ultra",
                "agent": "deep-executor",
                "default_effort": "xhigh",
                # By default leave pricing null — exercises Q5 (pricing TBD)
                "cost_per_1k_input": None,
                "cost_per_1k_output": None,
            },
        },
        "scoring": {
            "thresholds": {
                "fast_max": 0.30,
                "standard_max": 0.55,
                "deep_max": 0.80,
            },
        },
    }
    if ultra_pricing is not None:
        cfg["levels"]["ultra"]["cost_per_1k_input"] = ultra_pricing["in"]
        cfg["levels"]["ultra"]["cost_per_1k_output"] = ultra_pricing["out"]
    return cfg


# --- score_to_tier with extended tier_order ---


class TestScoreToTierUltra:
    def test_low_score_routes_to_fast(self):
        cfg = _make_ultra_config()
        tier, _ = score_to_tier(0.10, cfg["scoring"]["thresholds"], cfg["tier_order"])
        assert tier == "fast"

    def test_mid_score_routes_to_standard(self):
        cfg = _make_ultra_config()
        tier, _ = score_to_tier(0.40, cfg["scoring"]["thresholds"], cfg["tier_order"])
        assert tier == "standard"

    def test_high_score_routes_to_deep(self):
        cfg = _make_ultra_config()
        tier, _ = score_to_tier(0.70, cfg["scoring"]["thresholds"], cfg["tier_order"])
        assert tier == "deep"

    def test_top_score_routes_to_ultra(self):
        cfg = _make_ultra_config()
        tier, conf = score_to_tier(0.90, cfg["scoring"]["thresholds"], cfg["tier_order"])
        assert tier == "ultra"
        # Catch-all tier confidence floor is 0.80
        assert conf >= 0.80

    def test_boundary_inclusive_lower(self):
        cfg = _make_ultra_config()
        tier, _ = score_to_tier(0.80, cfg["scoring"]["thresholds"], cfg["tier_order"])
        assert tier == "ultra"  # >= deep_max → catch-all

    def test_default_tier_order_unchanged(self):
        # No ultra tier — legacy 3-tier behavior preserved.
        tier, _ = score_to_tier(0.90)
        assert tier == "deep"
        assert DEFAULT_TIER_ORDER == ["fast", "standard", "deep"]


# --- effort_for_tier reads default_effort from config ---


class TestEffortForTier:
    def test_reads_config_default_effort(self):
        cfg = _make_ultra_config()
        assert effort_for_tier("ultra", cfg) == "xhigh"
        assert effort_for_tier("deep", cfg) == "high"
        assert effort_for_tier("standard", cfg) == "medium"
        assert effort_for_tier("fast", cfg) == "low"

    def test_falls_back_to_legacy_map_without_config(self):
        assert effort_for_tier("fast") == EFFORT_MAP["fast"]
        assert effort_for_tier("deep") == EFFORT_MAP["deep"]

    def test_unknown_tier_without_config_returns_medium(self):
        assert effort_for_tier("unknown") == "medium"

    def test_invalid_default_effort_falls_back(self):
        cfg = {"levels": {"x": {"default_effort": "garbage"}}}
        # No EFFORT_MAP entry for "x" → falls through to "medium"
        assert effort_for_tier("x", cfg) == "medium"


# --- validate_config: lenient + warnings ---


class TestValidateConfigUltra:
    def test_well_formed_ultra_config_no_warnings(self):
        cfg = _make_ultra_config()
        warnings = validate_config(cfg)
        assert warnings == []

    def test_tier_order_missing_levels_entry_warns(self):
        cfg = _make_ultra_config()
        del cfg["levels"]["ultra"]
        warnings = validate_config(cfg)
        assert any("ultra" in w and "no levels" in w for w in warnings)

    def test_levels_entry_missing_from_tier_order_warns(self):
        cfg = _make_ultra_config()
        cfg["tier_order"] = ["fast", "standard", "deep"]  # ultra dropped
        warnings = validate_config(cfg)
        assert any("ultra" in w and "missing from tier_order" in w for w in warnings)

    def test_missing_threshold_warns(self):
        cfg = _make_ultra_config()
        del cfg["scoring"]["thresholds"]["deep_max"]
        warnings = validate_config(cfg)
        assert any("deep_max" in w for w in warnings)

    def test_non_monotonic_thresholds_warn(self):
        cfg = _make_ultra_config()
        cfg["scoring"]["thresholds"]["standard_max"] = 0.20  # < fast_max
        warnings = validate_config(cfg)
        assert any("standard_max" in w and "not greater" in w for w in warnings)

    def test_invalid_default_effort_warns(self):
        cfg = _make_ultra_config()
        cfg["levels"]["ultra"]["default_effort"] = "extreme"
        warnings = validate_config(cfg)
        assert any("ultra" in w and "extreme" in w for w in warnings)

    def test_default_config_passes_validation(self):
        # Sanity: shipped DEFAULT_CONFIG must be warning-free.
        warnings = validate_config(DEFAULT_CONFIG)
        assert warnings == []


# --- Savings calc tolerates pricing=null ---


class TestSavingsWithNullPricing:
    """Verify _calculate_savings does not crash when a tier has null pricing.

    Imported lazily to avoid pulling the full classify-prompt module at
    collection time when its sibling modules are not on path.
    """

    def _get_calc(self):
        # Sibling 'lib' modules are reachable because tests/ injected
        # hooks/ at sys.path[0] above.
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "classify_prompt",
            Path(__file__).parent.parent / "hooks" / "classify-prompt.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod._calculate_savings

    def test_null_pricing_tier_savings_zero(self):
        calc = self._get_calc()
        cfg = _make_ultra_config()  # ultra pricing = None
        # Routing to ultra should yield savings=0 (no max_cost - 0 = max_cost,
        # but ultra cost is 0; max_cost comes from deep)
        savings = calc("ultra", cfg)
        # max_cost = deep cost; ultra cost = 0 → savings = max_cost
        assert savings > 0.0  # Routing to a "free" tier saves vs deep

    def test_null_pricing_does_not_crash_max(self):
        calc = self._get_calc()
        cfg = _make_ultra_config()
        # Even when computing across all tiers (None included), no crash
        savings = calc("fast", cfg)
        assert savings >= 0.0

    def test_explicit_pricing_overrides_null(self):
        calc = self._get_calc()
        cfg = _make_ultra_config(ultra_pricing={"in": 0.030, "out": 0.150})
        # Now ultra is the most expensive tier — fast saves more vs ultra
        savings_fast = calc("fast", cfg)
        cfg_no_ultra = _make_ultra_config()
        savings_fast_no_ultra = calc("fast", cfg_no_ultra)
        assert savings_fast > savings_fast_no_ultra
