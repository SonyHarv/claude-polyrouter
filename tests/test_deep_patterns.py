"""Test enriched deep patterns across all 10 languages."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.classifier import classify_query, compile_patterns
from lib.detector import load_languages
from lib.config import DEFAULT_CONFIG

LANG_DIR = Path(__file__).parent.parent / "languages"


class TestDeepPatternsBase:
    """Base setup for deep pattern tests."""

    def setup_method(self):
        langs = load_languages(LANG_DIR)
        self.patterns = compile_patterns(langs)
        self.config = DEFAULT_CONFIG


class TestEnglishDeepPatterns(TestDeepPatternsBase):
    @pytest.mark.parametrize("query", [
        "analyze the architecture and propose improvements",
        "review the security of our authentication system",
        "design a scalable microservices migration plan",
        "think carefully about the best approach for this",
        "review the entire codebase for vulnerabilities",
        "investigate the root cause of this intermittent bug",
        "rewrite the authentication module from scratch",
        "what is the optimal solution for this problem",
        "give me an in-depth analysis of the system",
        "analyze the trade-offs between SQL and NoSQL and evaluate the best approach",
    ])
    def test_routes_to_deep(self, query):
        result = classify_query(query, ["en"], self.patterns, self.config)
        assert result.level == "deep", f"EN '{query}' → {result.level} (signals: {result.signals})"


class TestSpanishDeepPatterns(TestDeepPatternsBase):
    @pytest.mark.parametrize("query", [
        "analiza la arquitectura y propón mejoras",
        "revisa la seguridad del sistema de autenticación",
        "diseña un plan de migración a microservicios escalable",
        "piensa bien sobre el mejor enfoque para esto",
        "revisa todo el código completo en busca de vulnerabilidades",
        "investiga la causa raíz del bug intermitente",
        "reescribe el módulo de autenticación desde cero",
        "cuál es la mejor solución para este problema",
        "analiza a fondo el sistema",
        "esto es crítico para el proyecto",
    ])
    def test_routes_to_deep(self, query):
        result = classify_query(query, ["es"], self.patterns, self.config)
        assert result.level == "deep", f"ES '{query}' → {result.level} (signals: {result.signals})"


class TestPortugueseDeepPatterns(TestDeepPatternsBase):
    @pytest.mark.parametrize("query", [
        "analise a arquitetura e proponha melhorias",
        "revise a segurança do sistema de autenticação",
        "pense bem sobre a melhor abordagem para isso",
        "revise todo o código completo",
        "reescreva o módulo de autenticação",
        "isso é crítico para o projeto",
    ])
    def test_routes_to_deep(self, query):
        result = classify_query(query, ["pt"], self.patterns, self.config)
        assert result.level == "deep", f"PT '{query}' → {result.level} (signals: {result.signals})"


class TestFrenchDeepPatterns(TestDeepPatternsBase):
    @pytest.mark.parametrize("query", [
        "analyse l'architecture et propose des améliorations",
        "vérifie la sécurité du système d'authentification",
        "réfléchis bien à la meilleure approche pour cela",
        "examine tout le code complet",
        "réécris le module d'authentification",
        "c'est critique pour le projet",
    ])
    def test_routes_to_deep(self, query):
        result = classify_query(query, ["fr"], self.patterns, self.config)
        assert result.level == "deep", f"FR '{query}' → {result.level} (signals: {result.signals})"


class TestGermanDeepPatterns(TestDeepPatternsBase):
    @pytest.mark.parametrize("query", [
        "analysiere die Architektur und schlage Verbesserungen vor",
        "überprüfe die Sicherheit des Authentifizierungssystems",
        "denk gründlich über den besten Ansatz nach",
        "überprüfe alles komplett im Code",
        "das ist kritisch für das Projekt",
        "detailliert den kompletten Code analysieren und Sicherheit überprüfen",
    ])
    def test_routes_to_deep(self, query):
        result = classify_query(query, ["de"], self.patterns, self.config)
        assert result.level == "deep", f"DE '{query}' → {result.level} (signals: {result.signals})"


class TestRussianDeepPatterns(TestDeepPatternsBase):
    @pytest.mark.parametrize("query", [
        "проверь архитектуру и проведи аудит безопасности",
        "проверь безопасность системы аутентификации",
        "подумай хорошо о лучшем подходе",
        "перепиши модуль аутентификации",
        "это критично для проекта",
    ])
    def test_routes_to_deep(self, query):
        result = classify_query(query, ["ru"], self.patterns, self.config)
        assert result.level == "deep", f"RU '{query}' → {result.level} (signals: {result.signals})"


class TestChineseDeepPatterns(TestDeepPatternsBase):
    @pytest.mark.parametrize("query", [
        "分析架构并提出改进建议",
        "检查认证系统的安全漏洞",
        "仔细分析最好的方案",
        "重写认证模块",
        "这很重要需要深入分析",
        "优化性能的最佳策略",
    ])
    def test_routes_to_deep(self, query):
        result = classify_query(query, ["zh"], self.patterns, self.config)
        assert result.level == "deep", f"ZH '{query}' → {result.level} (signals: {result.signals})"


class TestJapaneseDeepPatterns(TestDeepPatternsBase):
    @pytest.mark.parametrize("query", [
        "アーキテクチャを分析して改善を提案してください",
        "認証システムのセキュリティを確認してください",
        "慎重に考えて最善のアプローチを見つけてください",
        "認証モジュールを書き直してください",
        "パフォーマンスの最適化について深く分析してください",
    ])
    def test_routes_to_deep(self, query):
        result = classify_query(query, ["ja"], self.patterns, self.config)
        assert result.level == "deep", f"JA '{query}' → {result.level} (signals: {result.signals})"


class TestKoreanDeepPatterns(TestDeepPatternsBase):
    @pytest.mark.parametrize("query", [
        "아키텍처를 분석하고 개선을 제안해주세요",
        "인증 시스템의 보안 취약점을 검토해주세요",
        "보안 취약점에 대해 깊이 검토해주세요",
        "인증 모듈을 재설계해주세요",
        "보안 취약점을 철저하게 분석해주세요",
    ])
    def test_routes_to_deep(self, query):
        result = classify_query(query, ["ko"], self.patterns, self.config)
        assert result.level == "deep", f"KO '{query}' → {result.level} (signals: {result.signals})"


class TestArabicDeepPatterns(TestDeepPatternsBase):
    @pytest.mark.parametrize("query", [
        "حلل هندسة النظام واقترح تحسينات",
        "راجع أمان نظام المصادقة",
        "فكر جيدا في أفضل نهج",
        "أعد كتابة وحدة المصادقة",
        "هذا مهم جدا للمشروع",
    ])
    def test_routes_to_deep(self, query):
        result = classify_query(query, ["ar"], self.patterns, self.config)
        assert result.level == "deep", f"AR '{query}' → {result.level} (signals: {result.signals})"


class TestDeepPatternsNotFalsePositive(TestDeepPatternsBase):
    """Ensure simple queries don't accidentally match deep patterns."""

    @pytest.mark.parametrize("query,lang", [
        ("hello", "en"),
        ("git status", "en"),
        ("what is a closure", "en"),
        ("hola", "es"),
        ("qué es REST", "es"),
        ("formatea este json", "es"),
        ("bonjour", "fr"),
        ("hallo", "de"),
        ("привет", "ru"),
        ("你好", "zh"),
        ("こんにちは", "ja"),
        ("안녕하세요", "ko"),
        ("مرحبا", "ar"),
    ])
    def test_simple_queries_not_deep(self, query, lang):
        result = classify_query(query, [lang], self.patterns, self.config)
        assert result.level != "deep", f"[{lang}] '{query}' should NOT be deep, got {result.level}"
