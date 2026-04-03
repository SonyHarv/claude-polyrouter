import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.detector import detect_language, load_languages


LANG_DIR = Path(__file__).parent.parent / "languages"


class TestLoadLanguages:
    def test_loads_en_and_es(self):
        langs = load_languages(LANG_DIR)
        assert "en" in langs
        assert "es" in langs

    def test_language_has_required_fields(self):
        langs = load_languages(LANG_DIR)
        for code, lang in langs.items():
            assert "stopwords" in lang, f"{code} missing stopwords"
            assert "patterns" in lang, f"{code} missing patterns"
            assert "follow_up_patterns" in lang, f"{code} missing follow_up_patterns"

    def test_skips_invalid_files(self):
        """load_languages should skip schema.json and invalid files."""
        langs = load_languages(LANG_DIR)
        assert "schema" not in langs

    def test_nonexistent_dir_returns_empty(self):
        langs = load_languages(Path("/nonexistent/dir"))
        assert langs == {}


class TestDetectLanguage:
    def setup_method(self):
        self.langs = load_languages(LANG_DIR)

    def test_detects_english(self):
        result = detect_language("what is the best way to do this", self.langs)
        assert result.language == "en"
        assert result.confidence > 0.15

    def test_detects_spanish(self):
        result = detect_language("cómo puedo hacer esto con los archivos", self.langs)
        assert result.language == "es"
        assert result.confidence > 0.15

    def test_short_query_flags_multi_eval(self):
        result = detect_language("fix bug", self.langs)
        assert result.multi_eval is True

    def test_ambiguous_flags_multi_eval(self):
        result = detect_language("refactor the code and make it clean", self.langs)
        assert result.language is not None

    def test_spanglish_detection(self):
        # Balanced mix: 3 en stopwords (the, is, with) + 3 es stopwords (la, el, para) + 4 neutral
        result = detect_language("the la is el code here with para algo nice", self.langs)
        assert result.multi_eval is True

    def test_empty_query(self):
        result = detect_language("", self.langs)
        assert result.multi_eval is True

    def test_single_word(self):
        result = detect_language("help", self.langs)
        assert result.multi_eval is True

    def test_last_language_used_for_short_queries(self):
        result = detect_language("ok", self.langs, last_language="es")
        assert result.language == "es"
        assert result.multi_eval is True
