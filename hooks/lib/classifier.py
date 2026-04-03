"""Rule-based query classification with pre-compiled regex patterns."""

import re
from dataclasses import dataclass


@dataclass
class ClassificationResult:
    level: str
    confidence: float
    method: str
    signals: dict[str, int]
    matched_languages: list[str]


def compile_patterns(languages: dict) -> dict[str, dict[str, list[re.Pattern]]]:
    """Pre-compile all regex patterns from all language files.

    Returns: {lang_code: {category: [compiled_regex, ...]}}
    Skips invalid patterns silently.
    """
    compiled = {}
    for code, lang_data in languages.items():
        compiled[code] = {}
        patterns = lang_data.get("patterns", {})
        for category, pattern_list in patterns.items():
            if not isinstance(pattern_list, list):
                continue
            compiled[code][category] = []
            for pattern_str in pattern_list:
                if not isinstance(pattern_str, str):
                    continue
                try:
                    compiled[code][category].append(
                        re.compile(pattern_str, re.IGNORECASE | re.UNICODE)
                    )
                except re.error:
                    continue
    return compiled


def _count_signals(
    query: str,
    lang_codes: list[str],
    compiled_patterns: dict,
) -> dict[str, int]:
    """Count pattern matches per category across specified languages."""
    signals: dict[str, int] = {}
    for code in lang_codes:
        if code not in compiled_patterns:
            continue
        for category, patterns in compiled_patterns[code].items():
            for pattern in patterns:
                if pattern.search(query):
                    signals[category] = signals.get(category, 0) + 1
                    break  # one match per category per language is enough
    return signals


def _decide(signals: dict[str, int], config: dict) -> tuple[str, float]:
    """Decision matrix: signals → (level, confidence)."""
    deep = signals.get("deep", 0)
    tool = signals.get("tool_intensive", 0)
    orch = signals.get("orchestration", 0)
    fast = signals.get("fast", 0)

    if deep and (tool or orch):
        return ("deep", 0.95)
    if deep >= 2:
        return ("deep", 0.90)
    if deep == 1:
        return ("deep", 0.70)
    if tool >= 2:
        return ("standard", 0.85)
    if tool == 1:
        return ("standard", 0.70)
    if orch:
        return ("standard", 0.75)
    if fast >= 2:
        return ("fast", 0.90)
    if fast == 1:
        return ("fast", 0.70)

    return (config.get("default_level", "fast"), 0.50)


def classify_query(
    query: str,
    lang_codes: list[str],
    compiled_patterns: dict,
    config: dict,
) -> ClassificationResult:
    """Classify a query using rule-based pattern matching."""
    if not isinstance(query, str) or not query.strip():
        return ClassificationResult(
            level=config.get("default_level", "fast"),
            confidence=0.5,
            method="rules",
            signals={},
            matched_languages=lang_codes,
        )

    signals = _count_signals(query, lang_codes, compiled_patterns)
    level, confidence = _decide(signals, config)

    return ClassificationResult(
        level=level,
        confidence=confidence,
        method="rules",
        signals=signals,
        matched_languages=lang_codes,
    )
