"""Knowledge-based routing adjustments from project learnings."""

import re
from pathlib import Path


def _extract_keywords(content: str) -> list[set[str]]:
    """Extract keyword sets from markdown learning entries."""
    keyword_sets = []
    for match in re.finditer(r"\*\*Keywords:\*\*\s*(.+)", content):
        keywords = {k.strip().lower() for k in match.group(1).split(",")}
        keywords.discard("")
        if keywords:
            keyword_sets.append(keywords)
    return keyword_sets


def _read_learnings(learnings_dir: Path) -> list[set[str]]:
    """Read all keyword sets from patterns.md and quirks.md."""
    keyword_sets = []
    for filename in ("patterns.md", "quirks.md"):
        path = learnings_dir / filename
        if path.exists() and path.is_file():
            try:
                content = path.read_text(encoding="utf-8")
                keyword_sets.extend(_extract_keywords(content))
            except Exception:
                continue
    return keyword_sets


def get_learned_adjustment(
    query: str,
    current_level: str,
    current_confidence: float,
    config: dict,
    learnings_dir: Path | None,
) -> tuple[float, str | None]:
    """Calculate learned confidence boost from project knowledge base.

    Returns: (boost_amount, reason_string_or_None)
    """
    learning_config = config.get("learning", {})

    if not learning_config.get("informed_routing", False):
        return (0.0, None)

    if not learnings_dir or not learnings_dir.exists() or not learnings_dir.is_dir():
        return (0.0, None)

    if current_level == "deep":
        return (0.0, None)

    if not isinstance(query, str) or not query.strip():
        return (0.0, None)

    max_boost = min(float(learning_config.get("max_boost", 0.1)), 0.2)
    query_words = set(re.findall(r"\w+", query.lower()))

    keyword_sets = _read_learnings(learnings_dir)
    if not keyword_sets:
        return (0.0, None)

    best_match_count = 0
    for keywords in keyword_sets:
        match_count = len(query_words & keywords)
        best_match_count = max(best_match_count, match_count)

    if best_match_count < 2:
        return (0.0, None)

    boost = min(best_match_count * 0.03, max_boost)
    return (boost, f"{best_match_count} keyword matches from learnings")
