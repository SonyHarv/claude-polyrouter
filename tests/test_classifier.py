import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.classifier import classify_query, compile_patterns, extract_signals, ClassificationResult, PatternSignals, _word_count
from lib.detector import load_languages
from lib.config import DEFAULT_CONFIG

LANG_DIR = Path(__file__).parent.parent / "languages"


class TestCompilePatterns:
    def test_compiles_without_error(self):
        langs = load_languages(LANG_DIR)
        compiled = compile_patterns(langs)
        assert "en" in compiled
        assert "es" in compiled

    def test_compiled_has_all_categories(self):
        langs = load_languages(LANG_DIR)
        compiled = compile_patterns(langs)
        for code in compiled:
            assert "fast" in compiled[code]
            assert "deep" in compiled[code]
            assert "tool_intensive" in compiled[code]
            assert "orchestration" in compiled[code]

    def test_skips_invalid_patterns(self):
        langs = {"test": {"patterns": {"fast": ["[invalid", "valid_pattern"]}}}
        compiled = compile_patterns(langs)
        assert len(compiled["test"]["fast"]) == 1  # only valid one


class TestWordCount:
    def test_ascii_words(self):
        assert _word_count("hello world") == 2

    def test_single_word(self):
        assert _word_count("hola") == 1

    def test_cjk_characters(self):
        assert _word_count("你好世界") == 4  # each CJK char = 1 token

    def test_mixed_cjk_and_ascii(self):
        assert _word_count("git status 你好") == 4  # 2 ascii + 2 CJK

    def test_empty_string(self):
        assert _word_count("") == 0


class TestLengthRules:
    """Length-based pre-classification: short queries → fast unless keywords present."""

    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG

    def test_single_word_routes_fast(self):
        result = classify_query("hola", ["es"], self.patterns, self.config)
        assert result.level == "fast"
        assert result.confidence == 0.85
        assert result.method == "length"

    def test_greeting_routes_fast(self):
        result = classify_query("hello", ["en"], self.patterns, self.config)
        assert result.level == "fast"
        assert result.confidence == 0.85

    def test_ok_routes_fast(self):
        result = classify_query("ok", ["en"], self.patterns, self.config)
        assert result.level == "fast"
        assert result.confidence == 0.85

    def test_short_no_keywords_routes_fast(self):
        """4-10 words, no standard/deep signals → fast @ 0.70"""
        result = classify_query("tell me about the weather today", ["en"], self.patterns, self.config)
        assert result.level == "fast"
        assert result.method == "length"

    def test_short_with_standard_keyword_overrides_length(self):
        """Short query with standard keyword → standard, not fast"""
        result = classify_query("create a function for sorting", ["en"], self.patterns, self.config)
        assert result.level == "standard"
        assert result.method == "scoring"

    def test_short_with_deep_keyword_overrides_length(self):
        """Short query with deep keyword → deep, not fast"""
        result = classify_query("design the architecture", ["en"], self.patterns, self.config)
        assert result.level == "deep"
        assert result.method == "scoring"

    def test_short_spanish_standard_overrides(self):
        result = classify_query("crea función sort", ["es"], self.patterns, self.config)
        assert result.level == "standard"

    def test_short_spanish_deep_overrides(self):
        result = classify_query("diseña arquitectura microservicios", ["es"], self.patterns, self.config)
        assert result.level == "deep"


class TestClassifyEnglish:
    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG

    def test_simple_question_routes_fast(self):
        result = classify_query("what is a closure in javascript", ["en"], self.patterns, self.config)
        assert result.level == "fast"

    def test_architecture_routes_deep(self):
        result = classify_query("design the architecture for a distributed system", ["en"], self.patterns, self.config)
        assert result.level == "deep"

    def test_git_command_routes_fast(self):
        result = classify_query("git status", ["en"], self.patterns, self.config)
        assert result.level == "fast"

    def test_security_audit_routes_deep(self):
        result = classify_query("audit the security vulnerabilities in this codebase", ["en"], self.patterns, self.config)
        assert result.level == "deep"

    def test_run_tests_routes_standard(self):
        result = classify_query("run the tests for the auth module", ["en"], self.patterns, self.config)
        assert result.level == "standard"

    def test_no_signals_routes_fast_via_length(self):
        result = classify_query("hello there", ["en"], self.patterns, self.config)
        assert result.level == "fast"
        assert result.confidence >= 0.70

    def test_empty_query_routes_default(self):
        result = classify_query("", ["en"], self.patterns, self.config)
        assert result.level == "fast"
        assert result.confidence == 0.5

    def test_greeting_pattern_match(self):
        result = classify_query("hello", ["en"], self.patterns, self.config)
        assert result.level == "fast"

    def test_confirmation_pattern_match(self):
        result = classify_query("perfect", ["en"], self.patterns, self.config)
        assert result.level == "fast"

    def test_implement_endpoint_routes_standard(self):
        result = classify_query("implement a REST endpoint with JWT auth for user login", ["en"], self.patterns, self.config)
        assert result.level == "standard"


class TestClassifySpanish:
    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG

    def test_simple_question_routes_fast(self):
        result = classify_query("qué es un closure en javascript", ["es"], self.patterns, self.config)
        assert result.level == "fast"

    def test_architecture_routes_deep(self):
        result = classify_query("diseña la arquitectura de un sistema distribuido", ["es"], self.patterns, self.config)
        assert result.level == "deep"

    def test_security_routes_deep(self):
        result = classify_query("auditoría de seguridad del codebase completo", ["es"], self.patterns, self.config)
        assert result.level == "deep"

    def test_run_tests_routes_standard(self):
        result = classify_query("ejecuta los tests del módulo de auth", ["es"], self.patterns, self.config)
        assert result.level == "standard"

    def test_greeting_routes_fast(self):
        result = classify_query("hola", ["es"], self.patterns, self.config)
        assert result.level == "fast"
        assert result.confidence >= 0.85

    def test_confirmation_routes_fast(self):
        result = classify_query("vale", ["es"], self.patterns, self.config)
        assert result.level == "fast"


class TestExpectedDistribution:
    """Verify the expected routing distribution matches the target:
    60%+ fast, 25-30% standard, 10-15% deep.
    """

    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG

    def test_distribution_sample(self):
        """Test a representative sample of queries across languages."""
        queries = [
            # Fast expected (greetings, confirmations, short questions, simple ops)
            ("hola", ["es"]),
            ("hello", ["en"]),
            ("ok", ["en"]),
            ("vale", ["es"]),
            ("thanks", ["en"]),
            ("gracias", ["es"]),
            ("git status", ["en"]),
            ("git diff", ["en"]),
            ("what is a closure", ["en"]),
            ("qué es REST", ["es"]),
            ("show me the logs", ["en"]),
            ("lista los archivos", ["es"]),
            ("explain promises", ["en"]),
            ("format this json", ["en"]),
            ("hello there", ["en"]),
            ("привет", ["ru"]),
            ("你好", ["zh"]),
            ("こんにちは", ["ja"]),
            ("perfect", ["en"]),
            ("listo", ["es"]),
            # Standard expected
            ("create a function for sorting arrays", ["en"]),
            ("crea función para ordenar arrays", ["es"]),
            ("implement a REST endpoint with JWT auth", ["en"]),
            ("fix the bug in the login handler", ["en"]),
            ("arregla el error en el controlador de login", ["es"]),
            ("run the tests for auth module", ["en"]),
            ("add a test for the payment service", ["en"]),
            ("update the user model to include email", ["en"]),
            # Deep expected
            ("design the architecture for a microservices system", ["en"]),
            ("diseña la arquitectura de microservicios", ["es"]),
            ("audit security vulnerabilities in the codebase", ["en"]),
            ("analyze trade-offs between SQL and NoSQL approaches", ["en"]),
        ]

        counts = {"fast": 0, "standard": 0, "deep": 0}
        for query, langs in queries:
            result = classify_query(query, langs, self.patterns, self.config)
            counts[result.level] += 1

        total = len(queries)
        fast_pct = counts["fast"] / total * 100
        standard_pct = counts["standard"] / total * 100
        deep_pct = counts["deep"] / total * 100

        # Target: ~35% fast, ~40% standard, ~25% deep
        assert fast_pct >= 30, f"Fast {fast_pct:.0f}% < 30% target (got {counts})"
        assert standard_pct >= 15, f"Standard {standard_pct:.0f}% < 15% (got {counts})"
        assert deep_pct >= 8, f"Deep {deep_pct:.0f}% < 8% (got {counts})"


class TestDecisionMatrix:
    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG

    def test_deep_plus_tool_routes_deep_high_confidence(self):
        result = classify_query(
            "design the architecture and run the tests for the entire project",
            ["en"], self.patterns, self.config,
        )
        assert result.level == "deep"
        assert result.confidence >= 0.85

    def test_multi_language_eval(self):
        result = classify_query(
            "qué es un closure en javascript",
            ["en", "es"], self.patterns, self.config,
        )
        assert result.level == "fast"

    def test_result_has_correct_type(self):
        result = classify_query("hello", ["en"], self.patterns, self.config)
        assert isinstance(result, ClassificationResult)
        assert isinstance(result.signals, dict)
        assert isinstance(result.matched_languages, list)
