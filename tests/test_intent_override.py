import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.intent_override import detect_intent_override, OverrideResult


class TestForceOpus:
    """User explicitly requests the best/opus model."""

    @pytest.mark.parametrize("query", [
        # English
        "use opus for this",
        "I need the best model for this task",
        "think deeply about this problem",
        "analyze this carefully please",
        "this is critical, don't rush",
        "take your time with this",
        "opus mode please",
        "give me your best analysis",
        "deep analysis of this codebase",
        # Spanish
        "usa opus para esto",
        "necesito el mejor modelo",
        "piensa bien sobre este problema",
        "analiza a fondo el proyecto",
        "esto es crítico",
        "esto es importante",
        "tómate tu tiempo",
        "dame el mejor análisis",
        "revisión profunda del código",
        # Portuguese
        "use o melhor modelo",
        "pense bem sobre isso",
        "isso é crítico",
        "análise profunda",
        # French
        "utilise le meilleur modèle",
        "réfléchis bien à ça",
        "c'est critique",
        "analyse approfondie",
        # German
        "benutze das beste modell",
        "das ist kritisch",
        "tiefe analyse",
    ])
    def test_opus_override_detected(self, query):
        result = detect_intent_override(query)
        assert result.level == "deep", f"'{query}' should force deep, got {result.level}"
        assert result.confidence == 0.95
        assert "opus" in result.reason or "intent" in result.reason

    @pytest.mark.parametrize("query", [
        # Russian
        "используй лучший для этого",
        "подумай хорошо",
        "это критично",
        # Chinese
        "用最好的模型",
        "仔细分析这个",
        "这很重要",
        # Japanese
        "最高モデルを使って",
        "慎重に考えてください",
        "これは重要",
        # Korean
        "최고 모델 사용해",
        "신중하게 분석해",
        "이것은 중요",
        # Arabic
        "استخدم أفضل نموذج",
        "فكر جيدا",
        "هذا مهم",
    ])
    def test_opus_override_non_latin_languages(self, query):
        result = detect_intent_override(query)
        assert result.level == "deep", f"'{query}' should force deep, got {result.level}"
        assert result.confidence == 0.95


class TestForceHaiku:
    """User explicitly requests a quick/fast response."""

    @pytest.mark.parametrize("query", [
        # English
        "quick answer please",
        "just tell me the command",
        "keep it short",
        "in one line",
        "tldr",
        "tl;dr",
        "haiku mode",
        "fast answer please",
        # Spanish
        "respuesta rápida por favor",
        "solo dime el comando",
        "resúmelo",
        "en una línea",
        # Portuguese
        "resposta rápida",
        "só me diz",
        # French
        "réponse rapide",
        "dis-moi juste",
        # German
        "schnelle antwort",
        "sag mir nur",
        "kurz und knapp",
        # Russian
        "быстрый ответ",
        "просто скажи",
        "кратко",
    ])
    def test_haiku_override_detected(self, query):
        result = detect_intent_override(query)
        assert result.level == "fast", f"'{query}' should force fast, got {result.level}"
        assert result.confidence == 0.95


class TestNoOverride:
    """Normal queries should not trigger any override."""

    @pytest.mark.parametrize("query", [
        "create a function to sort arrays",
        "fix the bug in auth.py",
        "crea una función de login",
        "what is a closure",
        "git status",
        "run the tests",
        "explain promises in javascript",
        "how do I use async await",
        "implement the payment endpoint",
        "refactor the user module",
        "hello",
        "ok",
        "",
    ])
    def test_no_false_positives(self, query):
        result = detect_intent_override(query)
        assert result.level is None, f"'{query}' should NOT trigger override, got {result.level}"
        assert result.reason == "no_override"


class TestOverrideResultStructure:
    def test_override_result_fields(self):
        result = detect_intent_override("use opus for this")
        assert isinstance(result, OverrideResult)
        assert isinstance(result.level, str)
        assert isinstance(result.confidence, float)
        assert isinstance(result.reason, str)

    def test_no_override_result_fields(self):
        result = detect_intent_override("hello world")
        assert result.level is None
        assert result.confidence == 0.0
        assert result.reason == "no_override"

    def test_empty_string(self):
        result = detect_intent_override("")
        assert result.level is None

    def test_none_input(self):
        result = detect_intent_override(None)
        assert result.level is None

    def test_whitespace_only(self):
        result = detect_intent_override("   ")
        assert result.level is None
