"""Language detection via stopword scoring."""

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DetectionResult:
    language: str | None
    confidence: float
    multi_eval: bool
    scores: dict[str, float]


def load_languages(lang_dir: Path) -> dict:
    """Auto-discover and load all language JSON files.

    Validates each file has required fields before accepting.
    Skips invalid files silently.
    """
    languages = {}
    if not lang_dir.is_dir():
        return languages
    for path in sorted(lang_dir.glob("*.json")):
        if path.name == "schema.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Validate required fields
            if not isinstance(data, dict):
                continue
            if not all(k in data for k in ("code", "stopwords", "patterns", "follow_up_patterns")):
                continue
            if not isinstance(data["stopwords"], list) or len(data["stopwords"]) < 5:
                continue
            if not isinstance(data["patterns"], dict):
                continue
            code = data["code"]
            if not isinstance(code, str) or len(code) != 2:
                continue
            languages[code] = data
        except Exception:
            continue
    return languages


def _tokenize(query: str) -> list[str]:
    """Split query into lowercase word tokens."""
    return re.findall(r"\w+", query.lower())


def detect_language(
    query: str,
    languages: dict,
    last_language: str | None = None,
) -> DetectionResult:
    """Detect the language of a query using stopword scoring.

    Returns a DetectionResult with the detected language, confidence,
    and whether multi-language evaluation is needed.
    """
    tokens = _tokenize(query)

    # Short queries: can't reliably detect language
    if len(tokens) < 4:
        return DetectionResult(
            language=last_language,
            confidence=0.0,
            multi_eval=True,
            scores={},
        )

    scores: dict[str, float] = {}
    token_set = set(tokens)

    for code, lang_data in languages.items():
        stopwords = set(lang_data.get("stopwords", []))
        matches = token_set & stopwords
        scores[code] = len(matches) / len(tokens) if tokens else 0.0

    if not scores:
        return DetectionResult(language=None, confidence=0.0, multi_eval=True, scores={})

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_code, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0

    # Spanglish: both en and es score high, neither dominates
    en_score = scores.get("en", 0.0)
    es_score = scores.get("es", 0.0)
    if en_score > 0.08 and es_score > 0.08 and abs(en_score - es_score) < 0.05:
        return DetectionResult(
            language=None,
            confidence=max(en_score, es_score),
            multi_eval=True,
            scores=scores,
        )

    # High confidence: clear winner
    if top_score > 0.15 and (top_score - second_score) > 0.05:
        return DetectionResult(
            language=top_code,
            confidence=top_score,
            multi_eval=False,
            scores=scores,
        )

    # Ambiguous
    return DetectionResult(
        language=top_code if top_score > 0 else last_language,
        confidence=top_score,
        multi_eval=True,
        scores=scores,
    )
