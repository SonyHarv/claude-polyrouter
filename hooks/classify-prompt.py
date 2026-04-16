"""Pipeline orchestrator for Claude Polyrouter UserPromptSubmit hook.

Eight-stage classification pipeline (v1.4):
1. Exception check (slash commands, meta-queries, empty input, continuations)
2. Intent override (natural language model forcing)
3. Cache lookup (fingerprint -> L1/L2 cache)
4. Language detection (stopword scoring)
5. Pattern extraction (raw signal counting, no tier decision)
6. Multi-signal scoring (patterns + structural + context → score → tier)
7. Context boost (follow-up detection → confidence boost)
8. Learned adjustments (keyword matching from project learnings)
"""

import json
import os
import re
import sys
from pathlib import Path

# Add hooks dir to path so lib package is importable
sys.path.insert(0, str(Path(__file__).parent))

from lib.cache import Cache, fingerprint
from lib.classifier import ClassificationResult, extract_signals, compile_patterns
from lib.config import DEFAULT_CONFIG, load_config
from lib.context import SessionState
from lib.detector import detect_language, load_languages
from lib.intent_override import detect_intent_override
from lib.learner import get_learned_adjustment
from lib.effort import (
    compute_effort,
    compute_deep_effort,
    normalize_effort_for_env,
    requires_advisor,
    maybe_promote_to_deep_xhigh,
)
from lib.compact import CompactAdvisor, load_compact_state, save_compact_state
from lib.scorer import compute_score, score_to_tier
from lib.stats import Stats

# --- Constants ---

PLUGIN_ROOT = Path(
    os.environ.get("CLAUDE_PLUGIN_ROOT", str(Path(__file__).parent.parent))
)
LANG_DIR = PLUGIN_ROOT / "languages"
STATS_PATH = Path.home() / ".claude" / "polyrouter-stats.json"
SESSION_PATH = Path.home() / ".claude" / "polyrouter-session.json"
CACHE_PATH = Path.home() / ".claude" / "polyrouter-cache.json"

CONTINUATION_TOKENS = {
    "y", "sí", "si", "ok", "okay", "yes", "go", "sure", "right",
    "dale", "va", "bien", "listo", "perfecto", "continúa", "continua",
    "sigue", "prosigue", "avanza", "adelante", "next", "continue",
    "proceed", "go ahead", "got it", "sounds good", "great", "perfect",
}

META_KEYWORDS = {"polyrouter", "routing", "router"}


# --- Output helpers ---

def _skip_output(reason: str) -> dict:
    """Build skip-routing output."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "[Claude Polyrouter] ROUTING SKIPPED\n"
                f"Reason: {reason}\n\n"
                "Respond to the user directly. Do not spawn a subagent."
            ),
        }
    }


def _route_output(
    level: str,
    model: str,
    agent: str,
    confidence: float,
    method: str,
    signals: str,
    language: str,
    query: str,
    effort: str = "medium",
    advisor: bool = False,
) -> dict:
    """Build minimal routing directive output (~50 tokens).

    Display info (confidence, method, signals, language) lives in the
    statusLine via polyrouter-hud.mjs — zero token cost there.
    additionalContext carries the routing directive + effort level and
    (when xhigh) an Advisor flag for Point 5 consumers.
    """
    header = f"[Claude Polyrouter] Route: {level} | Model: {model}"
    if effort and effort != "medium":
        header += f" | Effort: {effort}"
    if advisor:
        header += " | Advisor: required"
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                f"{header}\n"
                f'CRITICAL: Spawn "polyrouter:{agent}" subagent.'
            ),
        }
    }


def _calculate_savings(level: str, config: dict) -> float:
    """Calculate estimated savings compared to most expensive model."""
    levels = config.get("levels", {})
    if not levels:
        return 0.0
    max_cost = max(
        (lv.get("cost_per_1k_input", 0) + 2 * lv.get("cost_per_1k_output", 0))
        for lv in levels.values()
    )
    actual = levels.get(level, {})
    actual_cost = actual.get("cost_per_1k_input", 0) + 2 * actual.get("cost_per_1k_output", 0)
    return max(0.0, max_cost - actual_cost)


# --- Stage functions ---

def _stage_exception_check(query: str, session: SessionState) -> dict | None:
    """Stage 1: Check for exceptions that skip routing entirely.

    Returns a skip output dict if routing should be skipped, None otherwise.
    """
    # Empty or whitespace-only input
    if not query or not query.strip():
        return _skip_output("empty_input")

    stripped = query.strip()

    # Slash commands
    if stripped.startswith("/"):
        return _skip_output("slash_command")

    # Meta-queries about the router itself
    query_lower = stripped.lower()
    for keyword in META_KEYWORDS:
        if keyword in query_lower:
            return _skip_output("meta_query")

    # Continuation tokens: reuse last route
    if query_lower in CONTINUATION_TOKENS:
        state = session.read()
        last_level = state.get("last_level")
        if last_level:
            return None  # Will be handled as follow-up with cached route
        return _skip_output("continuation_no_history")

    return None


def _stage_cache_lookup(query: str, cache: Cache) -> dict | None:
    """Stage 2: Check cache for previously classified query.

    Returns cached route dict if found, None otherwise.
    """
    key = fingerprint(query)
    return cache.get(key)


def _stage_language_detection(
    query: str, languages: dict, session: SessionState
) -> tuple[str | None, bool, list[str]]:
    """Stage 3: Detect language of the query.

    Returns: (language, multi_eval, lang_codes_to_use)
    """
    state = session.read()
    last_language = state.get("last_language")

    result = detect_language(query, languages, last_language=last_language)

    if result.multi_eval:
        lang_codes = list(languages.keys())
    elif result.language:
        lang_codes = [result.language]
    else:
        lang_codes = list(languages.keys())

    return result.language, result.multi_eval, lang_codes


def _stage_extract_signals(
    query: str,
    lang_codes: list[str],
    compiled_patterns: dict,
):
    """Stage 5: Extract raw pattern signals without making a tier decision."""
    return extract_signals(query, lang_codes, compiled_patterns)


def _stage_scoring(
    query: str,
    pattern_signals,
    session: SessionState,
    config: dict,
) -> tuple[str, float, str, float]:
    """Stage 6: Multi-signal scoring → (level, confidence, method, score).

    Combines pattern signals with structural analysis and session context
    to produce a composite complexity score, then maps to tier. The raw
    score is returned so downstream stages (e.g., dynamic deep effort)
    can reuse it without recomputing.
    """
    context = session.get_scorer_context()

    # Pick up effort from env if not already tracked in session
    env_effort = os.environ.get("CLAUDE_CODE_EFFORT_LEVEL", "")
    if env_effort in ("low", "medium", "high"):
        context["effort_level"] = env_effort
    elif env_effort == "max":
        context["effort_level"] = "high"

    score, method = compute_score(
        query, pattern_signals.signals, pattern_signals.word_count, context,
    )
    thresholds = config.get("scoring", {}).get("thresholds", None)
    level, confidence = score_to_tier(score, thresholds)

    # Preserve backward-compatible confidence for length fast-track
    if method == "length":
        if pattern_signals.word_count < 4:
            confidence = 0.85
        else:
            confidence = 0.70

    return level, confidence, method, score


def _stage_context_boost(
    query: str,
    level: str,
    confidence: float,
    matched_languages: list[str],
    session: SessionState,
    compiled_patterns: dict,
    languages: dict,
) -> float:
    """Stage 7: Apply context boost for follow-up queries.

    Returns the adjusted confidence.
    """

    # Compile follow-up patterns from all relevant languages
    follow_up_patterns = []
    for code in matched_languages:
        lang_data = languages.get(code, {})
        for pattern_str in lang_data.get("follow_up_patterns", []):
            if isinstance(pattern_str, str):
                try:
                    follow_up_patterns.append(
                        re.compile(pattern_str, re.IGNORECASE | re.UNICODE)
                    )
                except re.error:
                    continue

    if session.is_follow_up(query, follow_up_patterns):
        boost = session.get_confidence_boost()
        confidence = min(1.0, confidence + boost)

    return confidence


def _stage_learned_adjustments(
    query: str,
    level: str,
    confidence: float,
    config: dict,
) -> tuple[float, str | None]:
    """Stage 8: Apply learned adjustments from project knowledge base."""
    learnings_dir = PLUGIN_ROOT / "learnings"
    boost, reason = get_learned_adjustment(
        query, level, confidence, config, learnings_dir
    )
    return min(1.0, confidence + boost), reason


# --- Main pipeline ---

def main() -> None:
    """Run the six-stage classification pipeline."""
    # Read input from stdin
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps(_skip_output("invalid_input")))
        return

    # Claude Code sends user prompt as "prompt"; fall back to "query" for tests
    query = input_data.get("prompt", "") or input_data.get("query", "")
    if not isinstance(query, str):
        print(json.dumps(_skip_output("invalid_query")))
        return

    # Load configuration and resources
    try:
        config = load_config()
    except Exception:
        config = dict(DEFAULT_CONFIG)

    try:
        languages = load_languages(LANG_DIR)
    except Exception:
        languages = {}

    try:
        compiled_patterns = compile_patterns(languages)
    except Exception:
        compiled_patterns = {}

    cache_cfg = config.get("cache", {})
    cache = Cache(
        memory_size=cache_cfg.get("memory_size", 50),
        file_size=cache_cfg.get("file_size", 100),
        ttl_days=cache_cfg.get("ttl_days", 30),
        cache_file=CACHE_PATH,
    )

    session = SessionState(
        SESSION_PATH,
        timeout_minutes=config.get("session_timeout_minutes", 30),
    )

    stats = Stats(STATS_PATH)

    # --- Stage 1: Exception check ---
    try:
        skip_result = _stage_exception_check(query, session)
        if skip_result is not None:
            print(json.dumps(skip_result))
            return
    except Exception:
        pass  # Continue pipeline on error

    # --- Stage 2: Intent Override (always max priority) ---
    try:
        override = detect_intent_override(query)
        if override.level is not None:
            level = override.level
            level_cfg = config.get("levels", {}).get(level, {})
            model = level_cfg.get("model", level)
            agent = level_cfg.get("agent", f"{level}-executor")
            confidence = override.confidence
            method = "intent_override"
            try:
                lang_result = detect_language(
                    query, languages,
                    last_language=session.read().get("last_language"),
                )
                display_language = lang_result.language or "multi"
            except Exception:
                display_language = "multi"
            savings = _calculate_savings(level, config)
            try:
                stats.record(level, display_language, False, savings)
            except Exception:
                pass
            try:
                session.update(level, display_language)
            except Exception:
                pass
            effort = compute_effort(level)
            output = _route_output(
                level, model, agent, confidence, method,
                f"override={override.reason}", display_language, query,
                effort=effort,
            )
            print(json.dumps(output))
            return
    except Exception:
        pass  # Continue pipeline on error

    # --- Stage 3: Cache lookup ---
    try:
        cached = _stage_cache_lookup(query, cache)
        if cached is not None:
            level = cached.get("level", config.get("default_level", "fast"))
            level_cfg = config.get("levels", {}).get(level, {})
            model = level_cfg.get("model", level)
            agent = level_cfg.get("agent", f"{level}-executor")
            language = cached.get("language", "en")
            confidence = cached.get("confidence", 0.5)
            method = f"cache({cached.get('method', 'rules')})"
            signals = cached.get("signals", "cached")

            savings = _calculate_savings(level, config)
            try:
                stats.record(level, language, True, savings)
            except Exception:
                pass
            try:
                session.update(level, language)
            except Exception:
                pass

            effort = compute_effort(level)
            output = _route_output(
                level, model, agent, confidence, method,
                str(signals), language, query,
                effort=effort,
            )
            print(json.dumps(output))
            return
    except Exception:
        pass  # Continue to full classification on cache error

    # --- Stage 4: Language detection ---
    try:
        language, multi_eval, lang_codes = _stage_language_detection(
            query, languages, session
        )
    except Exception:
        language = None
        multi_eval = True
        lang_codes = list(languages.keys()) if languages else []

    # --- Stage 5: Pattern extraction (raw signals, no tier decision) ---
    try:
        pattern_signals = _stage_extract_signals(
            query, lang_codes, compiled_patterns
        )
    except Exception:
        from lib.classifier import PatternSignals
        pattern_signals = PatternSignals(
            signals={}, word_count=0, matched_languages=lang_codes,
        )

    # --- Stage 6: Multi-signal scoring → tier ---
    try:
        level, confidence, method, score = _stage_scoring(
            query, pattern_signals, session, config
        )
    except Exception:
        level = config.get("default_level", "fast")
        confidence = 0.5
        method = "scoring"
        score = 0.0

    # --- Stage 6b: Architectural promotion (standard → deep+xhigh) ---
    # When an arch keyword (architecture, major refactor, rediseño…) appears
    # with ≥1 standard/tool/orch signal, promote tier so downstream stages
    # see the escalated routing. Env override still wins later for effort.
    arch_promoted = False
    try:
        level, arch_promoted = maybe_promote_to_deep_xhigh(
            level, pattern_signals.signals, query,
        )
        if arch_promoted:
            method = f"{method}+arch"
    except Exception:
        pass

    # --- Stage 7: Context boost ---
    try:
        confidence = _stage_context_boost(
            query, level, confidence,
            pattern_signals.matched_languages,
            session, compiled_patterns, languages,
        )
    except Exception:
        pass  # Keep existing confidence

    # --- Stage 8: Learned adjustments ---
    learned_reason = None
    try:
        confidence, learned_reason = _stage_learned_adjustments(
            query, level, confidence, config
        )
    except Exception:
        pass  # Keep existing confidence

    # --- Sync effort from env into session (user override path) ---
    try:
        env_effort = os.environ.get("CLAUDE_CODE_EFFORT_LEVEL", "")
        normalized_effort = "high" if env_effort == "max" else env_effort
        if normalized_effort in ("low", "medium", "high"):
            session.update_effort(normalized_effort)
    except Exception:
        pass

    # --- Build output ---
    level_cfg = config.get("levels", {}).get(level, {})
    model = level_cfg.get("model", level)
    agent = level_cfg.get("agent", f"{level}-executor")
    display_language = language or "multi"
    if learned_reason:
        method = f"{method}+learned"

    signals_str = ", ".join(
        f"{k}={v}" for k, v in pattern_signals.signals.items()
    ) if pattern_signals.signals else "none"

    # Cache the result
    try:
        key = fingerprint(query)
        cache.set(key, {
            "level": level,
            "confidence": confidence,
            "method": method,
            "signals": signals_str,
            "language": display_language,
        })
        cache.flush()
    except Exception:
        pass

    # Record stats
    savings = _calculate_savings(level, config)
    try:
        stats.record(level, display_language, False, savings)
    except Exception:
        pass

    # Update session
    try:
        session.update(level, display_language)
    except Exception:
        pass

    # --- Dynamic effort: deep tier gets sub-classification ---
    # User override (env var) wins over dynamic; compute_effort already honors it.
    env_effort_present = os.environ.get("CLAUDE_CODE_EFFORT_LEVEL", "") in (
        "low", "medium", "high", "max",
    )
    effort = compute_effort(level)
    advisor_flag = False
    if level == "deep" and not env_effort_present:
        if arch_promoted:
            # Promotion already identified arch scope → xhigh directly.
            effort = "xhigh"
        else:
            effort = compute_deep_effort(
                score, pattern_signals.signals, query, pattern_signals.word_count,
            )
        advisor_flag = requires_advisor(effort)
        # Persist the display label (supports "xhigh") and advisor flag
        try:
            session.update_effort(effort)
        except Exception:
            pass
        try:
            session.set_advisor(advisor_flag)
        except Exception:
            pass

    output = _route_output(
        level, model, agent, confidence, method,
        signals_str, display_language, query,
        effort=effort,
        advisor=advisor_flag,
    )

    # --- Compact advisory (append to output if warranted) ---
    try:
        compact_advisor = CompactAdvisor(config)
        compact_state = load_compact_state()
        advisory = compact_advisor.get_advisory(compact_state)
        if advisory:
            ctx = output.get("hookSpecificOutput", {}).get("additionalContext", "")
            output["hookSpecificOutput"]["additionalContext"] = ctx + "\n\n" + advisory
            save_compact_state(compact_state)
    except Exception:
        pass  # Never block routing on compact failure

    print(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "[Claude Polyrouter] ROUTING SKIPPED\n"
                    "Reason: internal_error\n\n"
                    "Respond to the user directly. Do not spawn a subagent."
                ),
            }
        }))
