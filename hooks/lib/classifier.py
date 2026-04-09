"""Rule-based query classification with pre-compiled regex patterns.

v1.4: Pattern extraction separated from tier decision. The discrete
decision matrix (_decide) is replaced by the multi-signal scorer.
classify_query() remains backward-compatible for existing consumers.
"""

import re
from dataclasses import dataclass

from lib.scorer import compute_score, score_to_tier


@dataclass
class ClassificationResult:
    level: str
    confidence: float
    method: str
    signals: dict[str, int]
    matched_languages: list[str]


@dataclass
class PatternSignals:
    """Raw pattern match results before tier decision."""
    signals: dict[str, int]
    word_count: int
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


def _word_count(query: str) -> int:
    """Count words in a query, handling CJK characters as individual tokens."""
    cjk_chars = len(re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', query))
    ascii_words = len(re.findall(r'[a-zA-Z0-9\u00c0-\u024f\u0400-\u04ff\u0600-\u06ff]+', query))
    return ascii_words + cjk_chars


def extract_signals(
    query: str,
    lang_codes: list[str],
    compiled_patterns: dict,
) -> PatternSignals:
    """Extract raw pattern signals without making a tier decision.

    This is the v1.4 entry point for the pipeline: extract signals first,
    then pass them to the scorer along with context data.
    """
    if not isinstance(query, str) or not query.strip():
        return PatternSignals(signals={}, word_count=0, matched_languages=lang_codes)

    signals = _count_signals(query, lang_codes, compiled_patterns)
    words = _word_count(query)

    return PatternSignals(
        signals=signals,
        word_count=words,
        matched_languages=lang_codes,
    )


def classify_query(
    query: str,
    lang_codes: list[str],
    compiled_patterns: dict,
    config: dict,
    context: dict | None = None,
) -> ClassificationResult:
    """Classify a query using multi-signal scoring.

    Backward-compatible wrapper: extracts pattern signals, runs the
    scorer with optional context, and returns a ClassificationResult.
    """
    if not isinstance(query, str) or not query.strip():
        return ClassificationResult(
            level=config.get("default_level", "fast"),
            confidence=0.5,
            method="rules",
            signals={},
            matched_languages=lang_codes,
        )

    ps = extract_signals(query, lang_codes, compiled_patterns)
    thresholds = config.get("scoring", {}).get("thresholds", None)

    score, method = compute_score(query, ps.signals, ps.word_count, context)
    level, confidence = score_to_tier(score, thresholds)

    # Preserve backward-compatible confidence for length fast-track
    if method == "length":
        if ps.word_count < 4:
            confidence = 0.85
        else:
            confidence = 0.70

    return ClassificationResult(
        level=level,
        confidence=confidence,
        method=method,
        signals=ps.signals,
        matched_languages=lang_codes,
    )
