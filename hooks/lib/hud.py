"""HUD helper — Poly mascot state and frame selection for statusLine.

This module is used by tests and can be imported by the Python pipeline
to determine mascot state without running Node. The canonical HUD output
is produced by hud/polyrouter-hud.mjs (StatusLine hook).

v1.6: New format with version prefix, ctx%, limits group, subagent counter,
      unabbreviated model names, │ separators, and new mascot states.
"""

import time

# --- Mascot definitions (must stay in sync with polyrouter-hud.mjs) ---

MASCOT_STATES = {
    "idle": {
        "frames": ["[^.^]~", "[^.^]~", "[^-^]", "[^.^]~"],
        "color": "#afa9ec",
    },
    "routing": {
        "frames": ["[^o^]\u00bb", "[^o^]\u00bb\u00bb", "[^O^]\u00bb\u00bb\u00bb"],
        "color": "#5dcaa5",
    },
    "keepalive": {
        "frames": ["[^.^]z", "[~.~]zz", "[~_~]zzz", "[^.^]*"],
        "color": "#484f58",
    },
    "danger": {
        "frames": ["[\u00b0O\u00b0]!", "[\u00b0O\u00b0]!!", "[>O<]!!!", "[>O<]!!!!"],
        "color": "#e24b4a",
    },
    "thinking": {
        "frames": ["[^.^].", "[^.^]..", "[^.^]...", "[^.~]..."],
        "color": "#ef9f27",
    },
    "compact": {
        "frames": ["[^.^]~", "[^.^]~~", "[^.^]~~~", "[^.^]ok"],
        "color": "#97c459",
    },
    # v1.6 new states
    "ctx_high": {
        "frames": ["[>.^]", "[>.^]~", "[>.^]!", "[>.^]~"],
        "color": "#e8853a",
    },
    "critical": {
        "frames": ["[x.x]", "[x.x]!", "[x.x]!!", "[x.x]"],
        "color": "#e24b4a",
    },
}

TIER_SHORT = {"fast": "fast", "standard": "std", "deep": "deep"}
TIER_MODELS = {"fast": "haiku", "standard": "sonnet", "deep": "opus"}

# Subagent name → exec model
SUBAGENT_MODELS = {
    "deep-executor": "opus",
    "standard-executor": "sonnet",
    "fast-executor": "haiku",
    "opus-orchestrator": "opus",
}


def get_frame(state: str, tick: int) -> str:
    """Return the animation frame for the given state and tick."""
    s = MASCOT_STATES.get(state, MASCOT_STATES["idle"])
    frames = s["frames"]
    return frames[tick % len(frames)]


# --- Cache freshness bar ---

CACHE_BAR_LEVELS = [
    (600,  "cache:\u2588\u2588\u2588\u2588\u2588", "#97c459"),         # 0-10 min: fresh, green
    (1800, "cache:\u2588\u2588\u2588\u2588\u2591", "#ef9f27"),         # 10-30 min: warm, yellow
    (3000, "cache:\u2588\u2588\u2588\u2591\u2591 !", "#e8853a"),       # 30-50 min: warning, orange
]
CACHE_BAR_EXPIRED = ("cache:\u2591\u2591\u2591\u2591\u2591 exp", "#e24b4a")  # 50+ min: expired, red


def cache_bar(elapsed_seconds: float) -> tuple[str, str]:
    """Return (bar_string, hex_color) based on cache age.

    Args:
        elapsed_seconds: seconds since last API query.

    Returns:
        Tuple of (bar like '████░', color like '#ef9f27').
    """
    for threshold, bar, color in CACHE_BAR_LEVELS:
        if elapsed_seconds < threshold:
            return bar, color
    return CACHE_BAR_EXPIRED


def _format_seconds(sec: int | float | None) -> str | None:
    """Format seconds as 'XhYm' or 'XdYh' depending on magnitude."""
    if sec is None:
        return None
    sec = int(sec)
    if sec < 0:
        return None
    if sec < 3600 * 24:
        h = sec // 3600
        m = (sec % 3600) // 60
        return f"{h}h{m}m"
    d = sec // 86400
    h = (sec % 86400) // 3600
    return f"{d}d{h}h"


def detect_state(
    session: dict | None,
    compact: dict | None = None,
    now: float | None = None,
) -> str:
    """Determine Poly's current mascot state from session data.

    v1.6 precedence (highest first):
      critical  → any limit ≥ 90% OR ctx ≥ 90%
      ctx_high  → ctx ≥ 70%
      danger    → cache > 50 min stale
      keepalive → cache > 40 min stale
      compact   → compact advisory active
      routing   → last query < 3s ago
      thinking  → last query < 10s ago
      idle      → default

    Args:
        session: polyrouter-session.json contents (or None).
        compact: polyrouter-compact.json contents (or None).
        now: current timestamp (defaults to time.time()).

    Returns:
        One of the MASCOT_STATES keys.
    """
    if not session or not session.get("last_route"):
        return "idle"

    if now is None:
        now = time.time()

    last = session.get("last_query_time", 0)
    elapsed = now - last

    ctx_pct = session.get("ctx_tokens", 0) or 0
    # ctx_tokens may be raw tokens or already a percentage — treat as pct if ≤ 100
    # classify-prompt writes percentage directly into ctx_tokens via update_ctx_tokens
    ctx_pct_val = int(ctx_pct) if isinstance(ctx_pct, (int, float)) else 0

    limits = session.get("limits") or {}

    # Check any limit ≥ 90% for critical
    def _any_limit_critical() -> bool:
        if not limits:
            return False
        for key in ("five_hour_pct", "weekly_pct", "sonnet_weekly_pct"):
            v = limits.get(key)
            if v is not None and v >= 90:
                return True
        return False

    if ctx_pct_val >= 90 or _any_limit_critical():
        return "critical"

    if ctx_pct_val >= 70:
        return "ctx_high"

    if elapsed > 3000:
        return "danger"
    if elapsed > 2400:
        return "keepalive"
    if elapsed < 3:
        return "routing"
    if elapsed < 10:
        return "thinking"
    if compact and compact.get("advisory_active"):
        return "compact"

    return "idle"


def format_status_line(
    state: str,
    tick: int,
    tier: str | None = None,
    savings: float = 0.0,
    language: str | None = None,
    elapsed: float | None = None,
    effort: str | None = None,
    subagent_active: bool = False,
    requires_advisor: bool = False,
    subagent_count: int = 0,
    exec_model: str | None = None,
    exec_effort: str | None = None,
    exec_advisor: bool = False,
    ctx_pct: int | None = None,
    limits: dict | None = None,
    swap_detected: bool = False,
    swap_expected: str | None = None,
    swap_actual: str | None = None,
    retry_active: bool = False,
    retry_from_tier: str | None = None,
    retry_from_effort: str | None = None,
    retry_to_tier: str | None = None,
    retry_to_effort: str | None = None,
    retry_at_ceiling: bool = False,
) -> str:
    """Build the full [poly v1.6] status line string.

    Format (no subagent):
      [poly v1.6] [^.^]~ haiku·fast │ cache:████░ ctx:8% │ 5h:45%(1h2m) wk:9%(6d19h) snt:3%(6d19h) │ $0.03↓ es

    Format (with subagent):
      [poly v1.6] [^.^]~ prompt:haiku·fast ⚙ exec:opus·xhigh·adv │ 🤖1 cache:████░ ctx:15% │ ... │ $9.50↓ es

    Format (high ctx):
      [poly v1.6] [^.^]~ haiku·fast ⚠compact │ cache:████░ ctx:78% │ ... │ $0.03↓ es
    """
    SEP = " \u2502 "  # ' │ '

    frame = get_frame(state, tick)

    # --- Model segment ---
    model_seg = ""
    if tier:
        # v1.7: retry-escalation arrow replaces the base model·route segment.
        # When at_ceiling, retry is active but no escalation occurred — we
        # render the normal segment plus a ⚠max glyph (handled below).
        if (
            retry_active
            and not retry_at_ceiling
            and retry_from_tier
            and retry_to_tier
        ):
            from_model = TIER_MODELS.get(retry_from_tier, retry_from_tier)
            from_route = TIER_SHORT.get(retry_from_tier, retry_from_tier)
            to_model = TIER_MODELS.get(retry_to_tier, retry_to_tier)
            to_route = TIER_SHORT.get(retry_to_tier, retry_to_tier)
            from_eff = ""
            if retry_from_tier == "deep" and retry_from_effort in ("high", "xhigh"):
                from_eff = f"\u00b7{retry_from_effort}"
            to_eff = ""
            if retry_to_tier == "deep" and retry_to_effort in ("high", "xhigh"):
                to_eff = f"\u00b7{retry_to_effort}"
            base = (
                f"{from_model}\u00b7{from_route}{from_eff}"
                f" \u2192 {to_model}\u00b7{to_route}{to_eff}"
            )
        else:
            model = TIER_MODELS.get(tier, tier)
            route = TIER_SHORT.get(tier, tier)
            effort_suffix = ""
            if tier == "deep" and effort in ("high", "xhigh"):
                effort_suffix = f"\u00b7{effort}"
            base = f"{model}\u00b7{route}{effort_suffix}"

        if subagent_active:
            model_seg = f"prompt:{base}"
        else:
            model_seg = base

        # Advisor tag (non-subagent path, on the main model segment)
        if requires_advisor and not subagent_active:
            model_seg += "\u00b7adv"

        # ctx ≥ 70%: append ⚠compact
        if ctx_pct is not None and ctx_pct >= 70:
            model_seg += " \u26a0compact"

        # v1.7: silent model swap (CC used a different family than poly routed)
        if swap_detected:
            model_seg += " \u26a0swap"

        # v1.7: retry at ceiling (deep/xhigh) — no escalation possible
        if retry_active and retry_at_ceiling:
            model_seg += " \u26a0max"

    # --- Exec segment (only when subagent active) ---
    exec_seg = ""
    if subagent_active and exec_model:
        exec_parts = [exec_model]
        if exec_effort:
            exec_parts.append(exec_effort)
        if exec_advisor:
            exec_parts.append("adv")
        exec_seg = " \u2699 exec:" + "\u00b7".join(exec_parts)

    # Build first group: mascot + model + exec
    # exec segment only renders when there is a prompt model segment to anchor it
    group1_parts = [f"[poly v1.6] {frame}"]
    if model_seg:
        group1_parts.append(model_seg + exec_seg)
    group1 = " ".join(group1_parts)

    # --- Middle group: 🤖N cache ctx ---
    middle_parts = []
    if subagent_count > 0:
        middle_parts.append(f"\U0001f916{subagent_count}")
    if elapsed is not None:
        bar, _color = cache_bar(elapsed)
        middle_parts.append(bar)
    if ctx_pct is not None:
        middle_parts.append(f"ctx:{ctx_pct}%")

    # --- Limits group ---
    limits_parts = []
    if limits:
        fh_pct = limits.get("five_hour_pct")
        fh_rem = limits.get("five_hour_remaining_sec")
        wk_pct = limits.get("weekly_pct")
        wk_rem = limits.get("weekly_remaining_sec")
        snt_pct = limits.get("sonnet_weekly_pct")
        snt_rem = limits.get("sonnet_weekly_remaining_sec")

        if fh_pct is not None:
            rem_str = _format_seconds(fh_rem)
            limits_parts.append(f"5h:{fh_pct}%({rem_str})" if rem_str else f"5h:{fh_pct}%")
        if wk_pct is not None:
            rem_str = _format_seconds(wk_rem)
            limits_parts.append(f"wk:{wk_pct}%({rem_str})" if rem_str else f"wk:{wk_pct}%")
        if snt_pct is not None:
            rem_str = _format_seconds(snt_rem)
            limits_parts.append(f"snt:{snt_pct}%({rem_str})" if rem_str else f"snt:{snt_pct}%")

    # --- Tail: savings + language ---
    tail_parts = []
    if savings > 0:
        tail_parts.append(f"${savings:.2f}\u2193")
    if language:
        tail_parts.append(language)

    # --- Assemble ---
    segments = [group1]
    if middle_parts:
        segments.append(" ".join(middle_parts))
    if limits_parts:
        segments.append(" ".join(limits_parts))
    if tail_parts:
        segments.append(" ".join(tail_parts))

    return SEP.join(segments)


def get_color(state: str) -> str:
    """Return the hex color for a mascot state."""
    return MASCOT_STATES.get(state, MASCOT_STATES["idle"])["color"]
