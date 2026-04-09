"""HUD helper — Poly mascot state and frame selection for statusLine.

This module is used by tests and can be imported by the Python pipeline
to determine mascot state without running Node. The canonical HUD output
is produced by hud/polyrouter-hud.mjs (StatusLine hook).
"""

import time

# --- Mascot definitions (must stay in sync with polyrouter-hud.mjs) ---

MASCOT_STATES = {
    "idle": {
        "frames": ["[^.^]  ~", "[^.^]  ~", "[^-^]   ", "[^.^]  ~"],
        "color": "#afa9ec",
    },
    "routing": {
        "frames": ["[^o^] \u00bb", "[^o^] \u00bb\u00bb", "[^O^] \u00bb\u00bb\u00bb"],
        "color": "#5dcaa5",
    },
    "keepalive": {
        "frames": ["[^.^] z", "[~.~] zz", "[~_~] zzz", "[^.^]  *"],
        "color": "#484f58",
    },
    "danger": {
        "frames": ["[\u00b0O\u00b0] !", "[\u00b0O\u00b0] !!", "[>O<] !!!", "[>O<] !!!!"],
        "color": "#e24b4a",
    },
    "thinking": {
        "frames": ["[^.^] .", "[^.^] ..", "[^.^] ...", "[^.~] ..."],
        "color": "#ef9f27",
    },
    "compact": {
        "frames": ["[^.^] ~", "[^.^] ~~", "[^.^] ~~~", "[^.^] ok"],
        "color": "#97c459",
    },
}

TIER_SHORT = {"fast": "fast", "standard": "std", "deep": "deep"}
TIER_MODELS = {"fast": "haiku", "standard": "sonnet", "deep": "opus"}


def get_frame(state: str, tick: int) -> str:
    """Return the animation frame for the given state and tick."""
    s = MASCOT_STATES.get(state, MASCOT_STATES["idle"])
    frames = s["frames"]
    return frames[tick % len(frames)]


def detect_state(
    session: dict | None,
    compact: dict | None = None,
    now: float | None = None,
) -> str:
    """Determine Poly's current mascot state from session data.

    Args:
        session: polyrouter-session.json contents (or None).
        compact: polyrouter-compact.json contents (or None).
        now: current timestamp (defaults to time.time()).

    Returns:
        One of: idle, routing, keepalive, danger, compact, thinking.
    """
    if not session or not session.get("last_route"):
        return "idle"

    if now is None:
        now = time.time()

    last = session.get("last_query_time", 0)
    elapsed = now - last

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
) -> str:
    """Build the full [polyrouter] status line string.

    Format: [polyrouter] [^.^] ~ · sonnet · std · $12.34↓ · es
    """
    frame = get_frame(state, tick)
    parts = [frame]

    if tier:
        model = TIER_MODELS.get(tier, tier)
        short = TIER_SHORT.get(tier, tier)
        parts.append(model)
        parts.append(short)

    if savings > 0:
        parts.append(f"${savings:.2f}\u2193")

    if language:
        parts.append(language)

    return f"[polyrouter] {' \u00b7 '.join(parts)}"


def get_color(state: str) -> str:
    """Return the hex color for a mascot state."""
    return MASCOT_STATES.get(state, MASCOT_STATES["idle"])["color"]
