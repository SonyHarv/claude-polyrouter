"""CALIDAD #12: Pattern parity invariants across all supported languages.

EN/ES set the upper bound for deep_pattern coverage (26 patterns each).
Other languages must reach the same count so that architectural prompts
in non-English/Spanish text route to the deep tier with comparable
sensitivity. Drift below 26 indicates either a forgotten cluster or a
deletion that should have been compensated.
"""

import json
import re
from pathlib import Path

import pytest

LANG_DIR = Path(__file__).parent.parent / "languages"
SUPPORTED = ("ar", "de", "en", "es", "fr", "ja", "ko", "pt", "ru", "zh")
DEEP_PATTERN_TARGET = 26


def _load(lc: str) -> dict:
    return json.loads((LANG_DIR / f"{lc}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("lang", SUPPORTED)
def test_deep_pattern_count_matches_target(lang):
    """Every supported language must hit the parity target of 26 deep patterns."""
    data = _load(lang)
    deep = data["patterns"]["deep"]
    assert len(deep) == DEEP_PATTERN_TARGET, (
        f"{lang} has {len(deep)} deep patterns; expected {DEEP_PATTERN_TARGET}. "
        f"Add the missing architectural cluster (distributed / failures / perf / "
        f"architect compose / ADR) or update the target if EN/ES grew."
    )


@pytest.mark.parametrize("lang", SUPPORTED)
def test_all_deep_patterns_compile(lang):
    """A bad regex would crash the scorer at runtime — fail fast in CI."""
    data = _load(lang)
    for i, pattern in enumerate(data["patterns"]["deep"]):
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            pytest.fail(f"{lang} deep[{i}] does not compile: {exc}\n  pattern: {pattern}")


@pytest.mark.parametrize("lang", SUPPORTED)
def test_advanced_clusters_present(lang):
    """The 6 advanced clusters (#21-#26 in EN) must appear at least once.

    Keyword anchors (case-insensitive substring of the raw pattern source):
      - distributed_or_event_driven
      - failover_or_cascading
      - memory_or_p99_or_race
      - architect_compose_verbs
      - adr_or_modular_monolith
    """
    data = _load(lang)
    blob = "|".join(data["patterns"]["deep"]).lower()

    anchors = {
        # "distribu" matches distribut / distribuid / distribué / distribuído
        # "driven" matches event-driven / event-?driven across all langs.
        "distributed_or_event_driven": (
            "distribu", "driven", "イベント駆動", "분산", "分布式",
            "распределён", "распределенн", "verteilt", "موزعة",
        ),
        "failover_or_cascading": (
            "failover", "cascading", "cascade", "kaskaden",
            "カスケード", "級联", "级联", "캐스케이딩", "каскад", "متتالية",
        ),
        "memory_or_p99_or_race": (
            "memory leak", "p99", "race condition", "speicherleck",
            "fuite mémoire", "vazamento", "メモリリーク", "메모리",
            "内存泄漏", "утечка", "تسرب ذاكرة",
        ),
        "architect_compose_verbs": (
            "entwirf", "conçois", "projete", "architect", "arquitect",
            "アーキテクト", "아키텍팅", "架构", "архитектируй", "هندس",
            "decompose", "decompon", "分解",
        ),
        "adr_or_modular_monolith": (
            "adr", "modular monolith", "monolith", "モノリス", "모놀리스",
            "单体", "монолит", "مونوليث", "monolithe", "monolito",
        ),
    }
    for cluster, needles in anchors.items():
        assert any(n.lower() in blob for n in needles), (
            f"{lang}: missing cluster {cluster!r}; expected one of {needles!r} "
            f"to appear somewhere in deep patterns."
        )
