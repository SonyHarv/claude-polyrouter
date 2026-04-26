"""Multi-signal scoring engine for query complexity assessment.

Replaces the discrete decision matrix (v1.3) with a continuous 0.0-1.0+
complexity score derived from weighted signals. Tier boundaries are
configurable via config.json.

Signal contributions (max per group):
  patterns:   0.70  (primary driver — deep combos, single deep, standard, tool)
  structural: 0.25  (code_blocks, errors, file paths, prompt length)
  universal:  0.20  (tech_symbols, code_identifiers — language-agnostic)
  context:    0.10  (tool_result, depth, effort)

Tier thresholds (default):
  fast:     score < 0.35
  standard: 0.35 <= score < 0.65
  deep:     score >= 0.65

v1.7 (CALIDAD #16): score_to_tier walks `tier_order` so adding a tier
(e.g. "ultra") only requires updating config.json — no scorer edits.
"""

import re

DEFAULT_TIER_ORDER = ["fast", "standard", "deep"]
DEFAULT_THRESHOLDS = {
    "fast_max": 0.35,
    "standard_max": 0.65,
}


# --- Individual signal extractors ---

def _signal_patterns(signals: dict[str, int]) -> float:
    """Pattern match signals → 0.0-0.70 contribution.

    Scaled to match plan thresholds (fast_max=0.35, standard_max=0.65).
    A single deep signal alone reaches deep tier; single standard
    reaches standard tier; combinations reinforce.
    """
    deep = signals.get("deep", 0)
    std = signals.get("standard", 0)
    tool = signals.get("tool_intensive", 0)
    orch = signals.get("orchestration", 0)
    fast = signals.get("fast", 0)

    if deep and (tool or orch or std):
        return 0.70
    if deep >= 2:
        return 0.70
    if deep == 1:
        return 0.65
    if std >= 2:
        return 0.50
    if std == 1 and (tool or orch):
        return 0.45
    if std == 1:
        return 0.38
    if tool >= 2:
        return 0.45
    if tool == 1:
        return 0.36
    if orch >= 1:
        return 0.38
    if fast >= 1:
        return 0.05
    return 0.0


_ERROR_RE = re.compile(
    r"(?:traceback|stack\s*trace|error:|exception:|panic:|fatal:)", re.IGNORECASE
)
_FILE_EXT_RE = re.compile(
    r"(?:[\s(]|^)(?:/[\w./-]+|\w+\.(?:py|js|ts|tsx|go|rs|java|rb|php|c|cpp|h|css|html|sql|yaml|yml|json|toml|md|sh)\b)"
)


def _signal_structural(query: str) -> float:
    """Code blocks, error traces, file paths, prompt length → 0.0-0.25."""
    score = 0.0

    # Code blocks (``` pairs)
    code_blocks = len(re.findall(r"```", query)) // 2
    score += min(0.10, code_blocks * 0.05)

    # Error / stack trace markers
    if _ERROR_RE.search(query):
        score += 0.07

    # File path references
    file_paths = len(_FILE_EXT_RE.findall(query))
    score += min(0.05, file_paths * 0.025)

    # Prompt length (longer prompts tend to be more complex)
    score += min(0.03, len(query) / 2000 * 0.03)

    return score


# --- Universal signals (language-agnostic) ---

_TECH_SYMBOLS_RE = re.compile(
    r"(?:=>|->|::|&&|\|\||[{}\[\]()]|[!=<>]=|<<|>>|\.\.\.|@\w)"
)

_CAMEL_CASE_RE = re.compile(r"[a-z][A-Z][a-zA-Z]")
_SNAKE_CASE_RE = re.compile(r"[a-z]+_[a-z]+")
_FUNC_CALL_RE = re.compile(r"[a-zA-Z_]\w*\(")
_DOT_ACCESS_RE = re.compile(r"\w\.\w")


def _signal_universal(query: str) -> float:
    """Language-agnostic technical signals → 0.0-0.20.

    Detects code-like tokens that indicate complexity regardless of
    the natural language used in the prompt.
    """
    score = 0.0

    # Technical symbols: =>, ->, ::, {}, [], (), &&, ||, etc.
    tech_hits = len(_TECH_SYMBOLS_RE.findall(query))
    score += min(0.10, tech_hits * 0.025)

    # Code identifiers: camelCase, snake_case, function(), obj.method
    ident_hits = (
        len(_CAMEL_CASE_RE.findall(query))
        + len(_SNAKE_CASE_RE.findall(query))
        + len(_FUNC_CALL_RE.findall(query))
        + len(_DOT_ACCESS_RE.findall(query))
    )
    score += min(0.10, ident_hits * 0.02)

    return score


def _signal_context(context: dict | None) -> float:
    """Session context signals → 0.0-0.10."""
    if not context or not isinstance(context, dict):
        return 0.0

    score = 0.0

    # Previous tool result length (large results suggest complex work)
    trl = context.get("last_tool_result_len", 0)
    if isinstance(trl, (int, float)) and trl > 0:
        score += min(0.04, trl / 50000 * 0.04)

    # Conversation depth (deeper conversations tend to be more complex)
    depth = context.get("conversation_depth", 0)
    if isinstance(depth, (int, float)) and depth > 0:
        score += min(0.03, depth / 10 * 0.03)

    # User effort level preference (xhigh = polyrouter display label for
    # architecturally-complex deep tasks; treated like high with a slight bump)
    effort = context.get("effort_level", "medium")
    effort_scores = {"low": 0.0, "medium": 0.01, "high": 0.03, "xhigh": 0.04}
    score += effort_scores.get(effort, 0.01)

    return score


# --- Public API ---

def compute_score(
    query: str,
    signals: dict[str, int],
    word_count: int,
    context: dict | None = None,
) -> tuple[float, str]:
    """Compute composite complexity score from multi-signal analysis.

    Returns: (score, method) where method is 'length' for short-query
    fast-track or 'scoring' for full multi-signal path.
    """
    has_deep = signals.get("deep", 0) > 0
    has_std = signals.get("standard", 0) > 0
    has_tool = signals.get("tool_intensive", 0) > 0
    has_orch = signals.get("orchestration", 0) > 0

    # Short-query fast-track: preserves v1.3 length-based pre-classification.
    # Only triggers when no standard/deep/tool/orch signals are present.
    if not has_deep and not has_std and not has_tool and not has_orch:
        if word_count < 4:
            return (0.05, "length")
        if word_count <= 10:
            return (0.10, "length")

    # Full multi-signal scoring
    score = (
        _signal_patterns(signals)
        + _signal_structural(query)
        + _signal_universal(query)
        + _signal_context(context)
    )

    return (min(1.0, max(0.0, score)), "scoring")


def score_to_tier(
    score: float,
    thresholds: dict | None = None,
    tier_order: list[str] | None = None,
) -> tuple[str, float]:
    """Map complexity score to (tier, confidence).

    Walks `tier_order` and routes to the first tier whose `<tier>_max`
    boundary is greater than the score. The last tier is the unbounded
    catch-all and gets a higher confidence floor (reaching the top tier
    is itself a strong signal).

    Confidence is higher when the score is far from tier boundaries.
    """
    order = tier_order or DEFAULT_TIER_ORDER
    t = thresholds or DEFAULT_THRESHOLDS

    if not order:
        return ("fast", 0.5)

    # Walk all tiers except the last (catch-all). Each non-terminal tier
    # has a `<tier>_max` boundary; missing values fall back to legacy
    # defaults so partial configs degrade gracefully.
    prev_boundary = 0.0
    for i, tier in enumerate(order[:-1]):
        key = f"{tier}_max"
        try:
            boundary = float(t.get(key, DEFAULT_THRESHOLDS.get(key, 1.0)))
        except (TypeError, ValueError):
            boundary = float(DEFAULT_THRESHOLDS.get(key, 1.0))

        if score < boundary:
            if i == 0:
                # First tier: distance to upper boundary only
                distance = boundary - score
            else:
                # Middle tier: distance to nearest boundary
                distance = min(score - prev_boundary, boundary - score)
            confidence = min(0.95, 0.65 + distance * 3.0)
            return (tier, round(confidence, 2))
        prev_boundary = boundary

    # Catch-all (last) tier: higher base confidence (0.80 floor)
    last_tier = order[-1]
    distance = max(0.0, score - prev_boundary)
    confidence = min(0.95, 0.80 + distance * 1.5)
    return (last_tier, round(confidence, 2))
