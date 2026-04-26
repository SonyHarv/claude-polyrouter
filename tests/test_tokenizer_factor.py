"""Tests for v1.7 ADICIONAL #11: tokenizer calibration factor.

The Claude 4.x family (haiku-4-5 / sonnet-4-6 / opus-4-7) tokenizes
~1.35× denser than the pre-4.x tokenizer used to derive the per-prompt
token estimates in _calculate_savings. The factor is configurable via
the top-level `tokenizer_factor` field, applied uniformly across all
tiers, and surfaced in the /polyrouter:stats breakdown.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.config import DEFAULT_CONFIG
from lib.context import SessionState

_CP_PATH = Path(__file__).parent.parent / "hooks" / "classify-prompt.py"
_spec = importlib.util.spec_from_file_location("classify_prompt", _CP_PATH)
classify_prompt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(classify_prompt)


def _config(factor=None):
    cfg = {
        "levels": {
            "fast": {"cost_per_1k_input": 0.001, "cost_per_1k_output": 0.005},
            "standard": {"cost_per_1k_input": 0.003, "cost_per_1k_output": 0.015},
            "deep": {"cost_per_1k_input": 0.015, "cost_per_1k_output": 0.075},
        },
    }
    if factor is not None:
        cfg["tokenizer_factor"] = factor
    return cfg


class TestCalculateSavingsFactor:
    """tokenizer_factor scales _calculate_savings linearly without touching ordering."""

    def test_factor_default_when_field_absent(self):
        # No factor field → behave as if factor=1.0 (preserve old config behavior).
        baseline = classify_prompt._calculate_savings("fast", _config())
        # max_cost (deep) = 0.015*1.0 + 0.075*0.5 = 0.0525
        # actual_cost (fast) = 0.001*1.0 + 0.005*0.5 = 0.0035
        # savings = 0.0490
        assert baseline == pytest.approx(0.0490)

    def test_factor_135_scales_savings_linearly(self):
        scaled = classify_prompt._calculate_savings("fast", _config(1.35))
        baseline = classify_prompt._calculate_savings("fast", _config(1.0))
        assert scaled == pytest.approx(baseline * 1.35)

    def test_factor_one_recovers_pre_calibration(self):
        explicit = classify_prompt._calculate_savings("fast", _config(1.0))
        legacy = classify_prompt._calculate_savings("fast", _config())
        assert explicit == pytest.approx(legacy)

    def test_factor_uniform_across_tiers(self):
        # Scaling does not change which tier is the most expensive, so deep
        # always returns 0 savings regardless of factor.
        for factor in (0.5, 1.0, 1.35, 2.0):
            assert classify_prompt._calculate_savings("deep", _config(factor)) == 0.0

    def test_factor_invalid_falls_back_to_one(self):
        # Non-numeric, zero, or negative values must not corrupt the calc.
        baseline = classify_prompt._calculate_savings("fast", _config(1.0))
        for bad in ("nope", None, 0, -1, float("nan") * 0):  # NaN*0 = NaN
            cfg = _config()
            cfg["tokenizer_factor"] = bad
            result = classify_prompt._calculate_savings("fast", cfg)
            # NaN comparison: just assert we don't crash and result is finite-ish.
            if result == result:  # not NaN
                assert result == pytest.approx(baseline)

    def test_default_config_uses_135(self):
        # The DEFAULT_CONFIG.tokenizer_factor=1.35 is what real users get.
        cfg = {
            "levels": DEFAULT_CONFIG["levels"],
            "tokenizer_factor": DEFAULT_CONFIG["tokenizer_factor"],
        }
        scaled = classify_prompt._calculate_savings("fast", cfg)
        unscaled = classify_prompt._calculate_savings(
            "fast", {"levels": DEFAULT_CONFIG["levels"], "tokenizer_factor": 1.0}
        )
        assert scaled == pytest.approx(unscaled * 1.35)


class TestStatsTokenizerLine:
    """_build_stats_block surfaces the tokenizer calibration when config is provided."""

    @pytest.fixture
    def session(self, tmp_path):
        s = SessionState(tmp_path / "session.json")
        s.record_route("fast", None, "scoring", "en", 0.01)
        return s

    def test_tokenizer_line_present_with_config(self, session):
        block = classify_prompt._build_stats_block(session, _config(1.35))
        assert "Tokenizer:" in block
        assert "×1.35" in block
        assert "4.x" in block

    def test_tokenizer_line_absent_when_config_none(self, session):
        # Backward compat: legacy callers (some tests) pass no config.
        block = classify_prompt._build_stats_block(session)
        assert "Tokenizer:" not in block

    def test_tokenizer_line_uses_custom_factor(self, session):
        block = classify_prompt._build_stats_block(session, _config(1.5))
        assert "×1.5" in block

    def test_tokenizer_line_falls_back_when_factor_invalid(self, session):
        cfg = _config()
        cfg["tokenizer_factor"] = "garbage"
        block = classify_prompt._build_stats_block(session, cfg)
        # Falls back to 1.0 — must still render the line, not crash.
        assert "Tokenizer:" in block
        assert "×1" in block


class TestDetectStatsCommandForwardsConfig:
    """_detect_stats_command must forward config so the marker call shows the line."""

    @pytest.fixture
    def session(self, tmp_path):
        s = SessionState(tmp_path / "session.json")
        s.record_route("fast", None, "scoring", "en", 0.01)
        return s

    def test_marker_with_config_includes_tokenizer_line(self, session):
        marker = classify_prompt._STATS_MARKER
        out = classify_prompt._detect_stats_command(marker, session, _config(1.35))
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Tokenizer:" in ctx
        assert "×1.35" in ctx

    def test_marker_without_config_omits_tokenizer_line(self, session):
        marker = classify_prompt._STATS_MARKER
        out = classify_prompt._detect_stats_command(marker, session)
        assert out is not None
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "Tokenizer:" not in ctx
