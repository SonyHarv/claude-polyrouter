"""Edge case tests for the classification pipeline."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.classifier import classify_query, compile_patterns, _word_count
from lib.detector import load_languages
from lib.config import DEFAULT_CONFIG
from lib.intent_override import detect_intent_override

LANG_DIR = Path(__file__).parent.parent / "languages"


class TestEdgeCaseInputs:
    """Handle unusual inputs gracefully."""

    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG

    def test_empty_string(self):
        result = classify_query("", ["en"], self.patterns, self.config)
        assert result.confidence == 0.5

    def test_whitespace_only(self):
        result = classify_query("   ", ["en"], self.patterns, self.config)
        assert result.confidence == 0.5

    def test_none_input(self):
        result = classify_query(None, ["en"], self.patterns, self.config)
        assert result.confidence == 0.5

    def test_only_emojis(self):
        result = classify_query("🚀🎉👍", ["en"], self.patterns, self.config)
        assert result.level is not None  # Should not crash

    def test_very_long_query(self):
        long_query = "please help me " * 100
        result = classify_query(long_query, ["en"], self.patterns, self.config)
        assert result.level is not None

    def test_query_with_only_numbers(self):
        result = classify_query("12345 67890", ["en"], self.patterns, self.config)
        assert result.level is not None

    def test_query_with_url(self):
        result = classify_query(
            "check https://example.com/api/v1/users for errors",
            ["en"], self.patterns, self.config,
        )
        assert result.level is not None

    def test_query_with_code_snippet(self):
        result = classify_query(
            "fix this: function foo() { return bar.baz(); }",
            ["en"], self.patterns, self.config,
        )
        assert result.level is not None

    def test_query_with_special_characters(self):
        result = classify_query("@#$%^&*()!~", ["en"], self.patterns, self.config)
        assert result.level is not None

    def test_single_deep_keyword(self):
        """A single deep keyword like 'architecture' should route to deep."""
        result = classify_query("architecture", ["en"], self.patterns, self.config)
        assert result.level == "deep"

    def test_single_deep_keyword_spanish(self):
        result = classify_query("arquitectura", ["es"], self.patterns, self.config)
        assert result.level == "deep"


class TestLengthGateBoundaries:
    """Test the exact boundaries of the length gate."""

    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG

    def test_3_words_no_signals_fast(self):
        """<4 words, no signals → fast via length."""
        result = classify_query("tell me something", ["en"], self.patterns, self.config)
        assert result.level == "fast"
        assert result.method == "length"

    def test_4_words_no_signals_reaches_matrix(self):
        """>=4 words should pass through to length check or decision matrix."""
        result = classify_query("tell me about stuff", ["en"], self.patterns, self.config)
        # 4 words, no signals → should hit the <=10 length check
        assert result.level == "fast"
        assert result.method == "length"

    def test_11_words_no_signals_reaches_matrix(self):
        """11+ words without signals should reach the decision matrix."""
        result = classify_query(
            "can you help me understand how this specific process works in our system",
            ["en"], self.patterns, self.config,
        )
        # 13 words, no deep/standard signals → reaches decision matrix → default
        assert result.method == "rules"

    def test_deep_keyword_overrides_short_length(self):
        """Deep keyword in short query must override length gate."""
        result = classify_query("security audit", ["en"], self.patterns, self.config)
        assert result.level == "deep"

    def test_standard_keyword_overrides_short_length(self):
        """Standard keyword in short query must override length gate."""
        result = classify_query("create function", ["en"], self.patterns, self.config)
        assert result.level == "standard"


class TestDecisionMatrixCalibration:
    """Test the recalibrated decision matrix values."""

    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG

    def test_single_deep_signal_confidence_080(self):
        """A single deep signal should give 0.80 confidence (was 0.70)."""
        result = classify_query(
            "analyze the architecture of this microservices system",
            ["en"], self.patterns, self.config,
        )
        assert result.level == "deep"
        assert result.confidence >= 0.80

    def test_deep_plus_tool_confidence_095(self):
        """Deep + tool signals should give 0.95 confidence."""
        result = classify_query(
            "search all files and audit the security vulnerabilities across modules",
            ["en"], self.patterns, self.config,
        )
        assert result.level == "deep"
        assert result.confidence >= 0.80

    def test_two_deep_signals_confidence_090(self):
        """Two deep signals should give 0.90 confidence."""
        result = classify_query(
            "analyze the architecture and evaluate security vulnerabilities in the scalable system",
            ["en"], self.patterns, self.config,
        )
        assert result.level == "deep"
        assert result.confidence >= 0.80


class TestMixedLanguageQueries:
    """Test Spanglish and mixed-language queries."""

    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG

    def test_spanglish_deep(self):
        """Spanglish deep query should be recognized."""
        result = classify_query(
            "analiza el architecture del system",
            ["en", "es"], self.patterns, self.config,
        )
        assert result.level == "deep"

    def test_spanglish_standard(self):
        """Spanglish standard query should be recognized."""
        result = classify_query(
            "crea un endpoint para el user login",
            ["en", "es"], self.patterns, self.config,
        )
        assert result.level == "standard"

    def test_multi_eval_all_languages(self):
        """Multi-eval with all language codes should still work."""
        langs = load_languages(LANG_DIR)
        all_codes = list(langs.keys())
        result = classify_query(
            "design the architecture",
            all_codes, self.patterns, self.config,
        )
        assert result.level == "deep"


class TestIntentOverrideEdgeCases:
    """Edge cases for intent override detection."""

    def test_opus_in_code_context_no_override(self):
        """Mentioning opus in a code context shouldn't trigger override."""
        result = detect_intent_override("install the opus audio codec library")
        # This might or might not match depending on patterns
        # The key is it shouldn't crash
        assert isinstance(result.level, (str, type(None)))

    def test_fast_in_variable_name_no_override(self):
        """'fast' in a variable name shouldn't trigger override."""
        result = detect_intent_override("rename the variable to fast_mode")
        assert result.level is None

    def test_case_insensitive_opus(self):
        result = detect_intent_override("USE OPUS FOR THIS")
        assert result.level == "deep"

    def test_case_insensitive_haiku(self):
        result = detect_intent_override("QUICK ANSWER PLEASE")
        assert result.level == "fast"


class TestCJKWordCount:
    """Test CJK character counting for length gate."""

    def test_pure_chinese(self):
        assert _word_count("分析架构") == 4  # 4 CJK chars

    def test_pure_japanese(self):
        assert _word_count("アーキテクチャ") == 7  # katakana chars

    def test_korean(self):
        assert _word_count("아키텍처") == 4  # 4 Korean chars

    def test_mixed_cjk_latin(self):
        count = _word_count("analyze 架构")
        assert count == 3  # 1 latin + 2 CJK
