import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.classifier import classify_query, compile_patterns, ClassificationResult
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

    def test_no_signals_routes_default(self):
        result = classify_query("hello there", ["en"], self.patterns, self.config)
        assert result.level == "fast"
        assert result.confidence == 0.5

    def test_empty_query_routes_default(self):
        result = classify_query("", ["en"], self.patterns, self.config)
        assert result.level == "fast"
        assert result.confidence == 0.5


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
        assert result.confidence >= 0.9

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
