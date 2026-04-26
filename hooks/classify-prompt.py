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
import time
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
    maybe_promote_multifile_refactor,
)
from lib.compact import CompactAdvisor, load_compact_state, save_compact_state
from lib.advisor import detect_advisor_category, format_advisor_block
from lib.ctx_usage import get_last_assistant_model, get_last_turn
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

# v1.7: tier → expected model family substring (case-insensitive match
# against the actual model id read from the transcript or stdin).
_TIER_TO_FAMILY = {
    "fast": "haiku",
    "standard": "sonnet",
    "deep": "opus",
}

# v1.7: retry-escalation marker — injected by /polyrouter:retry slash command.
# HTML comment so it's invisible in any rendered view but easy to grep.
_RETRY_MARKER = "<!-- POLY:RETRY:v1 -->"


def _retry_escalate(
    from_tier: str | None,
    from_effort: str | None,
) -> tuple[str, str, bool]:
    """Compute escalation target for a /polyrouter:retry invocation.

    Returns (to_tier, to_effort, at_ceiling).
    at_ceiling=True only when prev was deep/xhigh — same route returned,
    HUD renders ⚠max instead of an arrow.

    Path (v1.7): fast/* → standard/medium → deep/medium → deep/high
                 → deep/xhigh → ceiling.
    """
    if from_tier == "fast":
        return ("standard", "medium", False)
    if from_tier == "standard":
        return ("deep", "medium", False)
    if from_tier == "deep":
        if from_effort == "xhigh":
            return ("deep", "xhigh", True)
        if from_effort == "high":
            return ("deep", "xhigh", False)
        # deep/medium, deep/low, or unknown deep effort → bump to high
        return ("deep", "high", False)
    # No prior tier (first turn, fresh session) — start escalation at standard.
    return ("standard", "medium", False)


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
    advisor_block_override: str | None = None,
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

    body_parts = [
        header,
        f'CRITICAL: Spawn "polyrouter:{agent}" subagent.',
    ]

    # v1.7 SCOPE FIRME #4: Advisor hand-off block.
    # When advisor=True, include a structured [POLY:ADVISOR] block with a
    # category-specific checklist. The advisor_block_override path is used
    # by the /polyrouter:advisor manual command to inject [POLY:ADVISOR-MANUAL].
    if advisor_block_override is not None:
        body_parts.append("")
        body_parts.append(advisor_block_override)
    elif advisor:
        try:
            category = detect_advisor_category(query)
            body_parts.append("")
            body_parts.append(format_advisor_block(category))
        except Exception:
            pass  # Best-effort — never block routing on advisor block failure.

    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(body_parts),
        }
    }


def _apply_effort_override(
    level: str,
    model: str,
    agent: str,
    effort: str,
    session: SessionState,
    config: dict,
) -> tuple[str, str, str, str]:
    """Consume a pending one-shot effort override and apply it to the route.

    Returns possibly-modified (level, model, agent, effort). The override
    is *consumed* (cleared from session) regardless of whether modification
    occurs — single-fire semantics. When the override level is "xhigh" and
    promote_deep is set, the tier is auto-promoted to "deep" so the effort
    budget is meaningful.

    No-op (returns inputs unchanged) when no override is pending or on
    any error reading session state.
    """
    try:
        override = session.consume_effort_override()
    except Exception:
        return level, model, agent, effort
    if not override:
        return level, model, agent, effort

    new_effort = override.get("level") or effort
    if override.get("promote_deep") and level != "deep":
        deep_cfg = (config.get("levels") or {}).get("deep", {})
        new_level = "deep"
        new_model = deep_cfg.get("model", "opus")
        new_agent = deep_cfg.get("agent", "deep-executor")
        return new_level, new_model, new_agent, new_effort
    return level, model, agent, new_effort


def _calculate_savings(level: str, config: dict) -> float:
    """Calculate estimated savings vs routing every query to the most expensive model.

    Uses a conservative per-prompt estimate of 1 000 input tokens + 500 output tokens.
    This is a known approximation; actual token counts vary per query.

    The estimate is scaled by `tokenizer_factor` (default 1.0 if absent), which
    accounts for tokenizer drift between Claude families. The Claude 4.x family
    (haiku-4-5 / sonnet-4-6 / opus-4-7) tokenizes ~1.35× denser than the
    pre-4.x tokenizer used to derive these constants — see DEFAULT_CONFIG.
    """
    # Approximate tokens per prompt (input + output)
    _INPUT_TOKENS_K = 1.0   # 1 000 input tokens
    _OUTPUT_TOKENS_K = 0.5  # 500 output tokens (conservative estimate)

    levels = config.get("levels", {})
    if not levels:
        return 0.0

    try:
        factor = float(config.get("tokenizer_factor", 1.0))
    except (TypeError, ValueError):
        factor = 1.0
    # `not factor > 0` rejects NaN, zero, and negative values in one check.
    if not factor > 0:
        factor = 1.0

    def _coerce(v) -> float:
        # v1.7 (CALIDAD #16): pricing may be null when a new tier is wired
        # up before its public price is finalized — treat as zero-cost.
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _prompt_cost(lv: dict) -> float:
        return (_coerce(lv.get("cost_per_1k_input")) * _INPUT_TOKENS_K * factor
                + _coerce(lv.get("cost_per_1k_output")) * _OUTPUT_TOKENS_K * factor)

    max_cost = max(_prompt_cost(lv) for lv in levels.values())
    actual_cost = _prompt_cost(levels.get(level, {}))
    return max(0.0, max_cost - actual_cost)


# --- Silent model swap detection (v1.7) ---

def _detect_silent_swap(input_data: dict, session: SessionState) -> None:
    """Compare previous turn's tier expectation against the model CC actually used.

    Runs at the start of every UserPromptSubmit hook. Reads the previous
    turn's `last_level` from session state, derives the expected family
    (haiku / sonnet / opus), and looks up the actual model used:
      1. `effective_model` field in the hook stdin (forward-compat with
         future Claude Code versions that may expose this directly).
      2. Last assistant `message.model` from the JSONL transcript.

    If the family does not appear (case-insensitive substring) in the
    actual model id, marks a swap; otherwise clears any prior flag. Never
    raises — silent best-effort detection that must not block routing.
    First-turn (no `last_level` yet) → clear and return.
    """
    try:
        state = session.read()
        last_level = state.get("last_level")
        if not last_level or last_level not in _TIER_TO_FAMILY:
            session.clear_swap()
            return

        expected_family = _TIER_TO_FAMILY[last_level]

        # 1. Try stdin first (forward-compat).
        actual = input_data.get("effective_model") or input_data.get("model")
        # 2. Fall back to transcript.
        if not isinstance(actual, str) or not actual:
            actual = get_last_assistant_model(input_data.get("transcript_path"))

        if not isinstance(actual, str) or not actual:
            # No signal available — leave any prior flag untouched.
            return

        if expected_family in actual.lower():
            session.clear_swap()
        else:
            session.mark_swap(expected_family, actual)
    except Exception:
        # Detection must never crash the hook.
        pass


# --- Retry escalation (v1.7) ---

def _detect_retry(
    query: str,
    session: SessionState,
    config: dict,
    stats: Stats,
) -> dict | None:
    """Detect /polyrouter:retry invocation and force-escalate the tier.

    The retry slash command injects an HTML comment marker (`_RETRY_MARKER`)
    into the prompt. When present, we read the previous turn's tier/effort
    from session state, compute the escalation target (see _retry_escalate),
    persist retry state for the HUD arrow, and emit a forced route output —
    bypassing the normal scoring pipeline.

    Returns the route output dict on retry, or None when no marker is found.
    Always calls clear_retry() on the no-marker path so the arrow vanishes
    on the next normal prompt.
    """
    if not isinstance(query, str) or _RETRY_MARKER not in query:
        try:
            session.clear_retry()
        except Exception:
            pass
        return None

    try:
        state = session.read()
        from_tier = state.get("last_level") if state.get("last_level") in _TIER_TO_FAMILY else None
        from_effort = state.get("effort_level")
        to_tier, to_effort, at_ceiling = _retry_escalate(from_tier, from_effort)

        try:
            session.mark_retry(from_tier, from_effort, to_tier, to_effort, at_ceiling)
        except Exception:
            pass
        try:
            session.inc_retry_invocations()
        except Exception:
            pass

        level_cfg = config.get("levels", {}).get(to_tier, {})
        model = level_cfg.get("model", to_tier)
        agent = level_cfg.get("agent", f"{to_tier}-executor")

        # Persist routing decision so subsequent turns escalate from here.
        try:
            language = state.get("last_language") or "en"
            session.update(to_tier, language)
            session.update_effort(to_effort)
        except Exception:
            pass

        savings = _calculate_savings(to_tier, config)
        try:
            stats.record(
                to_tier, state.get("last_language") or "en", False, savings,
                session_name=state.get("session_name"),
            )
        except Exception:
            pass
        try:
            session.record_route(
                to_tier, to_effort, "retry_escalation",
                state.get("last_language") or "en", savings,
            )
        except Exception:
            pass

        signals = (
            f"retry_ceiling(from={from_tier}/{from_effort})"
            if at_ceiling
            else f"retry_escalate({from_tier}/{from_effort}→{to_tier}/{to_effort})"
        )
        return _route_output(
            level=to_tier,
            model=model,
            agent=agent,
            confidence=1.0,
            method="retry_escalation",
            signals=signals,
            language=state.get("last_language") or "en",
            query=query,
            effort=to_effort,
        )
    except Exception:
        # Retry detection must never crash the hook — fall back to normal pipeline.
        try:
            session.clear_retry()
        except Exception:
            pass
        return None


# --- Advisor manual hand-off (v1.7 SCOPE FIRME #4) ---

_ADVISOR_MARKER = "<!-- POLY:ADVISOR-MANUAL:v1 -->"


def _build_manual_advisor_block(query: str, transcript_path: str | None) -> str:
    """Build the [POLY:ADVISOR-MANUAL] pre-loaded context block.

    Includes: question, project (cwd basename), git branch (best-effort),
    and the last user prompt + assistant response from the transcript
    (truncated to keep the block compact).
    """
    parts = ["[POLY:ADVISOR-MANUAL]"]

    question = query.replace(_ADVISOR_MARKER, "").strip()
    if question:
        q_head = question[:1000].strip()
        parts.append(f"Question: {q_head}")

    try:
        cwd = Path.cwd()
        parts.append(f"Project: {cwd.name}")
    except Exception:
        pass

    try:
        head = Path.cwd() / ".git" / "HEAD"
        if head.exists():
            ref = head.read_text(encoding="utf-8").strip()
            if ref.startswith("ref: refs/heads/"):
                branch = ref.split("refs/heads/", 1)[1]
                parts.append(f"Branch: {branch}")
    except Exception:
        pass

    try:
        turn = get_last_turn(transcript_path)
        if turn:
            user_p = (turn.get("user_prompt") or "")[:200].replace("\n", " ").strip()
            asst_r = (turn.get("assistant_response") or "")[:300].replace("\n", " ").strip()
            if user_p or asst_r:
                parts.append("Last turn:")
                if user_p:
                    parts.append(f"  user: {user_p}")
                if asst_r:
                    parts.append(f"  assistant: {asst_r}")
    except Exception:
        pass

    return "\n".join(parts)


def _detect_advisor_command(
    query: str,
    config: dict,
    stats: Stats,
    session: SessionState,
    transcript_path: str | None,
) -> dict | None:
    """Detect /polyrouter:advisor and force-route to opus-orchestrator.

    Locked target (v1.7): tier=deep, effort=xhigh, agent=opus-orchestrator,
    advisor=True. Skips the normal pipeline entirely. Pre-loads project
    context (cwd basename, git branch, last turn) into the
    [POLY:ADVISOR-MANUAL] block on additionalContext.

    Returns the route output dict on advisor invocation, or None when no
    marker is found (caller continues normal pipeline).
    """
    if not isinstance(query, str) or _ADVISOR_MARKER not in query:
        return None

    try:
        block = _build_manual_advisor_block(query, transcript_path)

        level = "deep"
        effort = "xhigh"
        level_cfg = config.get("levels", {}).get(level, {})
        model = level_cfg.get("model", "opus")
        # Locked agent — opus-orchestrator, not the default deep-executor.
        agent = "opus-orchestrator"

        try:
            language = session.read().get("last_language") or "en"
            session.update(level, language, requires_advisor=True)
            session.update_effort(effort)
            session.set_advisor(True)
        except Exception:
            language = "en"

        savings = _calculate_savings(level, config)
        try:
            stats.record(
                level, language, False, savings,
                session_name=session.read().get("session_name"),
            )
        except Exception:
            pass
        try:
            session.record_route(level, effort, "advisor_manual", language, savings)
        except Exception:
            pass

        return _route_output(
            level=level,
            model=model,
            agent=agent,
            confidence=1.0,
            method="advisor_manual",
            signals="advisor_manual_command",
            language=language,
            query=query,
            effort=effort,
            advisor=True,
            advisor_block_override=block,
        )
    except Exception:
        return None


# --- Effort one-shot override (v1.7 SCOPE FIRME #5) ---

_EFFORT_MARKER = "<!-- POLY:EFFORT:v1 -->"
_VALID_EFFORTS = ("low", "medium", "high", "xhigh")
_EFFORT_TOKEN_RE = re.compile(r"\b(low|medium|high|xhigh)\b", re.IGNORECASE)


def _extract_effort_arg(query: str) -> str | None:
    """Extract a valid effort token from the prompt body.

    Strips the marker first, then scans for the first whitelisted token.
    Returns the lowercase level when found, or None if no valid token
    appears in the visible body.
    """
    if not isinstance(query, str):
        return None
    body = query.replace(_EFFORT_MARKER, " ")
    m = _EFFORT_TOKEN_RE.search(body)
    return m.group(1).lower() if m else None


def _effort_error_output(reason: str) -> dict:
    """Build the [POLY:EFFORT-ERROR] no-op output.

    Used when the user invokes /polyrouter:effort with an invalid or
    missing argument — emits an explanation block but no Spawn directive,
    so Claude Code handles the turn as a normal text reply.
    """
    body = "\n".join((
        "[POLY:EFFORT-ERROR]",
        f"Reason: {reason}",
        "Valid levels: " + ", ".join(_VALID_EFFORTS),
        'Usage: /polyrouter:effort <low|medium|high|xhigh>',
        "No override was stored — your next prompt will route normally.",
    ))
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": body,
        }
    }


def _effort_ack_output(level: str, promote_deep: bool) -> dict:
    """Build the [POLY:EFFORT] acknowledgment output.

    Confirms the override is armed for the next prompt. No Spawn directive
    — the slash-command turn itself is handled by Claude Code's main
    model (the override is a sticky note for the *next* turn).
    """
    lines = [
        "[POLY:EFFORT]",
        f"Override armed: {level} (one-shot, applies to next prompt)",
    ]
    if promote_deep:
        lines.append("Auto-promote: tier will be raised to deep for the next prompt.")
    body = "\n".join(lines)
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": body,
        }
    }


def _detect_effort_command(query: str, session: SessionState) -> dict | None:
    """Detect /polyrouter:effort and store a one-shot override.

    On valid invocation:
        - Persists effort_override_* in session (consumed next turn).
        - Emits a [POLY:EFFORT] acknowledgment block.
        - Returns the output dict (caller short-circuits the pipeline).

    On invalid arg:
        - Emits a [POLY:EFFORT-ERROR] block, does NOT store.
        - Still returns an output so the pipeline short-circuits — the
          slash-command turn is consumed by the explanation, not by
          normal scoring.

    No marker → returns None (caller continues normally).
    """
    if not isinstance(query, str) or _EFFORT_MARKER not in query:
        return None

    level = _extract_effort_arg(query)
    if level is None:
        return _effort_error_output("missing or unrecognised effort level")

    promote_deep = (level == "xhigh")
    try:
        session.set_effort_override(level, promote_deep=promote_deep)
    except Exception:
        return _effort_error_output("internal error storing override")

    return _effort_ack_output(level, promote_deep)


# --- Routing breakdown (v1.7 ADICIONAL #9) ---

_STATS_MARKER = "<!-- POLY:STATS:v1 -->"
_BAR_WIDTH = 20
_BAR_FILL = "█"   # full block
_BAR_EMPTY = "░"  # light shade

_TIER_DISPLAY_ORDER = (
    ("fast",        "fast       "),
    ("standard",    "standard   "),
    ("deep_medium", "deep·medium"),
    ("deep_high",   "deep·high  "),
    ("deep_xhigh",  "deep·xhigh "),
)


def _format_duration(seconds: float) -> str:
    """Render a relative duration as `Xh Ym` / `Xm Ys` / `<1m`."""
    if seconds < 60:
        return "<1m"
    minutes = int(seconds // 60)
    if minutes < 60:
        secs = int(seconds - minutes * 60)
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    hours = minutes // 60
    rem = minutes - hours * 60
    return f"{hours}h {rem}m" if rem else f"{hours}h"


def _format_clock(epoch_seconds: float | None) -> str:
    """Render an epoch timestamp as HH:MM in local time, or '-' if missing."""
    if not epoch_seconds:
        return "-"
    try:
        from datetime import datetime
        return datetime.fromtimestamp(float(epoch_seconds)).strftime("%H:%M")
    except Exception:
        return "-"


def _ascii_bar(fraction: float, width: int = _BAR_WIDTH) -> str:
    """Render a 0..1 fraction as a fixed-width filled/empty bar."""
    if not (0.0 <= fraction <= 1.0):
        fraction = 0.0
    filled = int(round(fraction * width))
    return _BAR_FILL * filled + _BAR_EMPTY * (width - filled)


def _format_top_freq(d: dict[str, int], top_n: int = 3) -> str:
    """Render the top-N entries of a count dict as `key (XX%) · key (YY%)`."""
    if not d:
        return "(none)"
    total = sum(d.values()) or 1
    items = sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    return " · ".join(f"{k} ({(v / total) * 100:.0f}%)" for k, v in items)


_SESSION_NAME_DISPLAY_MAX = 20


def _truncate_session_name(name: str, limit: int = _SESSION_NAME_DISPLAY_MAX) -> str:
    """Truncate a session_name for stats display (CALIDAD #17 Q6).

    Names longer than `limit` chars get the trailing chars replaced with
    a single ellipsis character so the visible string is exactly `limit`.
    Storage keeps the full name; this is a display-only concern.
    """
    if not isinstance(name, str):
        return ""
    if len(name) <= limit:
        return name
    if limit < 1:
        return ""
    return name[: limit - 1] + "…"


def _format_by_session_name(by_name: dict, top_n: int = 5) -> list[str]:
    """Render the per-session-name section for [POLY:STATS] (CALIDAD #17).

    Returns lines (possibly empty list when nothing to show). Sorts by
    query count desc, truncates names to 20 chars + ellipsis. Cap at
    `top_n` to keep the block compact.
    """
    if not isinstance(by_name, dict) or not by_name:
        return []
    items = []
    for name, entry in by_name.items():
        if not isinstance(entry, dict):
            continue
        items.append((name, entry))
    items.sort(key=lambda kv: int(kv[1].get("queries") or 0), reverse=True)
    items = items[:top_n]
    if not items:
        return []
    lines = ["", "By session:"]
    for name, entry in items:
        q = int(entry.get("queries") or 0)
        savings = float(entry.get("savings") or 0.0)
        display = _truncate_session_name(name)
        # Pad name column to limit so the columns stay aligned.
        lines.append(
            f"  {display:<{_SESSION_NAME_DISPLAY_MAX}}  "
            f"{q:>4} routes · ${savings:.2f} saved"
        )
    return lines


def _build_stats_block(session: SessionState, config: dict | None = None) -> str:
    """Render the [POLY:STATS] breakdown for the current session.

    `config` is optional for backward compat with tests that call this
    function directly. When provided, the rendered block surfaces the
    `tokenizer_factor` calibration applied to the savings figure.
    """
    state = session.read()
    counts = state.get("routing_counts") or {}
    total = sum(int(counts.get(k, 0)) for k, _ in _TIER_DISPLAY_ORDER)
    started_at = state.get("routing_started_at")
    age = (time.time() - float(started_at)) if started_at else 0.0
    when = _format_clock(started_at)

    lines = ["[POLY:STATS]"]
    if total == 0:
        lines.append("Session: no routes recorded yet (counters reset on /polyrouter:stats reset or 30m idle).")
        return "\n".join(lines)

    lines.append(f"Session: {total} routes since {when} ({_format_duration(age)} ago)")
    lines.append("")
    lines.append("Tier · effort:")
    for key, label in _TIER_DISPLAY_ORDER:
        n = int(counts.get(key, 0))
        frac = n / total if total else 0.0
        bar = _ascii_bar(frac)
        lines.append(f"  {label} {bar} {frac * 100:5.1f}% ({n})")
    lines.append("")

    methods = state.get("routing_method_counts") or {}
    langs = state.get("routing_lang_counts") or {}
    lines.append(f"Top methods:  {_format_top_freq(methods)}")
    lines.append(f"Languages:    {_format_top_freq(langs)}")

    savings = float(state.get("routing_savings_total") or 0.0)
    lines.append(f"Savings:      ${savings:.2f} vs all-Opus")

    if config is not None:
        try:
            factor = float(config.get("tokenizer_factor", 1.0))
        except (TypeError, ValueError):
            factor = 1.0
        if not factor > 0:
            factor = 1.0
        lines.append(f"Tokenizer:    4.x (×{factor:g} calibrated)")

    retries = int(state.get("retry_invocations") or 0)
    lines.append(f"Retries:      {retries} invocation(s) of /polyrouter:retry")

    # CALIDAD #17: per-session-name breakdown read from the global
    # stats file. Survives /clear because CC v2.1.120+ preserves
    # session_name across the reset.
    try:
        stats_data = Stats(STATS_PATH).read()
        by_name = stats_data.get("by_session_name") or {}
    except Exception:
        by_name = {}
    lines.extend(_format_by_session_name(by_name))

    return "\n".join(lines)


def _stats_meta_output(body: str) -> dict:
    """Wrap a stats block as a no-route additionalContext output.

    Like /polyrouter:effort, the slash-command turn is consumed by the
    explanation — it does NOT emit a Spawn directive.
    """
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": body,
        }
    }


def _detect_stats_command(
    query: str, session: SessionState, config: dict | None = None
) -> dict | None:
    """Detect /polyrouter:stats and emit the breakdown (or reset).

    Recognises an optional `reset` argument anywhere in the prompt body
    after the marker. Returns the route output dict on invocation, or
    None when the marker is absent. `config` is forwarded to
    _build_stats_block to surface the tokenizer calibration line.
    """
    if not isinstance(query, str) or _STATS_MARKER not in query:
        return None
    body = query.replace(_STATS_MARKER, " ").lower()
    if re.search(r"\breset\b", body):
        try:
            session.reset_routing_stats()
        except Exception:
            pass
        return _stats_meta_output(
            "[POLY:STATS]\nReset complete. Routing counters, method/language "
            "frequencies, savings total, and retry invocations are now zero."
        )
    return _stats_meta_output(_build_stats_block(session, config))


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
    tier_order = config.get("tier_order")
    level, confidence = score_to_tier(score, thresholds, tier_order)

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

    # CALIDAD #17: capture CC's session_name (preserved across /clear in
    # CC v2.1.120+). Persisted to session state and forwarded to stats
    # so per-session-name aggregation survives across /clear cycles.
    # Silent when absent — older CC versions and unnamed sessions both
    # land here without warnings.
    session_name = input_data.get("session_name")
    if not isinstance(session_name, str) or not session_name:
        session_name = None

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

    # CALIDAD #17: persist session_name to state once per turn so retry,
    # advisor, cache-hit, and main paths all see it via session.read().
    if session_name is not None:
        try:
            session.update_session_name(session_name)
        except Exception:
            pass

    # --- v1.7: Silent model swap detection (runs even when routing skips) ---
    _detect_silent_swap(input_data, session)

    # --- v1.7: Retry escalation (forces a higher tier; bypasses scoring) ---
    retry_output = _detect_retry(query, session, config, stats)
    if retry_output is not None:
        print(json.dumps(retry_output))
        return

    # --- v1.7: Manual advisor hand-off (forces deep/xhigh + opus-orchestrator) ---
    advisor_output = _detect_advisor_command(
        query, config, stats, session, input_data.get("transcript_path"),
    )
    if advisor_output is not None:
        print(json.dumps(advisor_output))
        return

    # --- v1.7: Effort one-shot override (/polyrouter:effort) ---
    # The slash-command turn arms a sticky note for the *next* prompt;
    # the override itself is consumed inside _route_output below.
    effort_output = _detect_effort_command(query, session)
    if effort_output is not None:
        print(json.dumps(effort_output))
        return

    # --- v1.7: Routing stats breakdown (/polyrouter:stats [reset]) ---
    stats_output = _detect_stats_command(query, session, config)
    if stats_output is not None:
        print(json.dumps(stats_output))
        return

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
                stats.record(
                    level, display_language, False, savings,
                    session_name=session_name,
                )
            except Exception:
                pass
            try:
                session.update(level, display_language)
            except Exception:
                pass
            effort = compute_effort(level)
            level, model, agent, effort = _apply_effort_override(
                level, model, agent, effort, session, config,
            )
            try:
                session.record_route(level, effort, method, display_language, savings)
            except Exception:
                pass
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
                stats.record(
                    level, language, True, savings,
                    session_name=session_name,
                )
            except Exception:
                pass
            try:
                session.update(level, language)
            except Exception:
                pass

            # Replay effort + advisor from cache (backward-compat: use safe defaults)
            effort = cached.get("effort", compute_effort(level))
            cached_advisor = cached.get("advisor", False)
            try:
                session.update_effort(effort)
            except Exception:
                pass
            try:
                session.set_advisor(cached_advisor)
            except Exception:
                pass

            level, model, agent, effort = _apply_effort_override(
                level, model, agent, effort, session, config,
            )
            try:
                session.record_route(level, effort, method, language, savings)
            except Exception:
                pass
            output = _route_output(
                level, model, agent, confidence, method,
                str(signals), language, query,
                effort=effort,
                advisor=cached_advisor,
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
    multifile_promoted = False
    try:
        level, arch_promoted = maybe_promote_to_deep_xhigh(
            level, pattern_signals.signals, query,
            language=language or "en",
        )
        if arch_promoted:
            method = f"{method}+arch"
    except Exception:
        pass

    # --- Stage 6c: Multi-file refactor promotion (standard → deep·high) ---
    # Fires only when arch promotion did NOT fire; xhigh always wins.
    if not arch_promoted:
        try:
            if maybe_promote_multifile_refactor(query, level):
                level = "deep"
                multifile_promoted = True
                method = f"{method}+multifile"
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

    # Cache the result (include effort + advisor so cache hits replay correctly)
    try:
        key = fingerprint(query)
        cache.set(key, {
            "level": level,
            "confidence": confidence,
            "method": method,
            "signals": signals_str,
            "language": display_language,
            "effort": effort,
            "advisor": advisor_flag,
        })
        cache.flush()
    except Exception:
        pass

    # Record stats
    savings = _calculate_savings(level, config)
    try:
        stats.record(
            level, display_language, False, savings,
            session_name=session_name,
        )
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
        elif multifile_promoted:
            # Multi-file refactor promotion → high (not xhigh, no arch scope).
            effort = "high"
        else:
            effort = compute_deep_effort(
                score, pattern_signals.signals, query, pattern_signals.word_count,
                language=language or "en",
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

    # --- v1.7 SCOPE FIRME #5: apply one-shot effort override last ---
    # User intent (from /polyrouter:effort) wins over the classifier's
    # computed effort. xhigh auto-promotes the tier to deep so the
    # effort budget is meaningful.
    pre_override = (level, model, agent, effort)
    level, model, agent, effort = _apply_effort_override(
        level, model, agent, effort, session, config,
    )
    if (level, model, agent, effort) != pre_override:
        # Re-evaluate advisor flag against the post-override effort and
        # persist so the HUD reflects the user's chosen effort.
        advisor_flag = requires_advisor(effort)
        try:
            session.update_effort(effort)
        except Exception:
            pass
        try:
            session.set_advisor(advisor_flag)
        except Exception:
            pass

    # v1.7 ADICIONAL #9: per-session routing breakdown.
    try:
        session.record_route(level, effort, method, display_language, savings)
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
