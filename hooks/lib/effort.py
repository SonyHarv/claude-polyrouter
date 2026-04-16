"""Dynamic effort mapping: tier + score → effort level.

v1.5: Deep tier supports sub-effort (medium/high/xhigh) derived from
multi-signal complexity analysis. `xhigh` is a polyrouter-only display
label — it normalizes to `high` before being emitted as the Claude Code
`CLAUDE_CODE_EFFORT_LEVEL` env var (upstream only supports low/medium/high).
`xhigh` additionally flags `requires_advisor=true` for the Advisor Strategy.

User overrides (via env var or /effort command) always take priority.
"""

import os
import re

EFFORT_MAP = {
    "fast": "low",
    "standard": "medium",
    "deep": "high",
}

# Env-var-valid efforts (what Claude Code understands)
VALID_EFFORTS = {"low", "medium", "high"}

# Display-valid efforts (what HUD / session / logs can show)
DISPLAY_EFFORTS = {"low", "medium", "high", "xhigh"}


# --- Architectural-complexity detection (xhigh gate) ---

_ARCH_RE = re.compile(
    r"\b("
    # English
    r"architecture|architect|architectural|system\s+design|redesign\w*|overhaul|"
    r"major\s+refactor|strategic\s+refactor|design\s+decision|migration\s+strategy|"
    r"breaking\s+change|re-?architect|"
    # Spanish
    r"arquitectura|arquitect[oó]nic[oa]|dise[ñn]o\s+de\s+sistema|redise[ñn]\w*|"
    r"refactor\s+cr[ií]tico|refactor\s+mayor|decisi[oó]n\s+arquitect[oó]nica|"
    r"estrategia\s+de\s+migraci[oó]n|cambio\s+incompatible"
    r")\b",
    re.IGNORECASE,
)

# Mirrors scorer.py — kept local to avoid circular import
_FILE_EXT_RE = re.compile(
    r"(?:[\s(]|^)(?:/[\w./-]+|\w+\.(?:py|js|ts|tsx|go|rs|java|rb|php|c|cpp|h|css|html|sql|yaml|yml|json|toml|md|sh)\b)"
)

_CODE_BLOCK_RE = re.compile(r"```")


def compute_effort(tier: str, user_override: str | None = None) -> str:
    """Derive base effort level from routing tier.

    Priority: user_override > env var > tier mapping.
    For deep tier with dynamic sub-effort, call compute_deep_effort() after.
    """
    # Explicit user override always wins
    if user_override:
        normalized = "high" if user_override == "max" else user_override
        if normalized in VALID_EFFORTS:
            return normalized

    # Environment variable is next priority
    env_effort = os.environ.get("CLAUDE_CODE_EFFORT_LEVEL", "")
    normalized_env = "high" if env_effort == "max" else env_effort
    if normalized_env in VALID_EFFORTS:
        return normalized_env

    return EFFORT_MAP.get(tier, "medium")


def compute_deep_effort(
    score: float,
    signals: dict[str, int],
    query: str,
    word_count: int,
) -> str:
    """Classify deep-tier complexity into medium / high / xhigh.

    Only call when the routing tier is 'deep'. Returns a display label —
    use normalize_effort_for_env() before setting CLAUDE_CODE_EFFORT_LEVEL.
    """
    if not isinstance(query, str):
        query = ""
    if not isinstance(signals, dict):
        signals = {}

    deep = int(signals.get("deep", 0) or 0)
    std = int(signals.get("standard", 0) or 0)
    tool = int(signals.get("tool_intensive", 0) or 0)
    orch = int(signals.get("orchestration", 0) or 0)

    arch_hit = bool(_ARCH_RE.search(query))
    files = _FILE_EXT_RE.findall(query)
    blocks = len(_CODE_BLOCK_RE.findall(query)) // 2

    # --- xhigh gates: architectural / critical work ---
    if arch_hit and (deep >= 1 or orch >= 1):
        return "xhigh"
    if orch >= 1 and deep >= 1 and len(files) >= 3:
        return "xhigh"
    if score >= 0.85 and word_count >= 80:
        return "xhigh"

    # --- high gates: complex multi-signal deep ---
    if deep >= 1 and (std + tool + orch) >= 1:
        return "high"
    if deep >= 2:
        return "high"
    if score >= 0.80:
        return "high"
    if len(files) >= 2 and deep >= 1:
        return "high"
    if blocks >= 2 and deep >= 1:
        return "high"

    return "medium"


def normalize_effort_for_env(effort: str) -> str:
    """Map display effort label to a Claude-Code-valid env value.

    xhigh → high (upstream has no xhigh); unknown → medium.
    """
    if effort == "xhigh":
        return "high"
    return effort if effort in VALID_EFFORTS else "medium"


def requires_advisor(effort_label: str) -> bool:
    """Return True if this effort level should engage the Advisor (Point 5)."""
    return effort_label == "xhigh"


def maybe_promote_to_deep_xhigh(
    tier: str,
    signals: dict[str, int] | None,
    query: str,
) -> tuple[str, bool]:
    """Promote non-deep tier → deep when an architectural keyword appears
    alongside at least one standard/tool/orch signal.

    Rationale: queries like "plan a major refactor across microservices" or
    "refactor auth.py login.py session.py" register as standard under the
    pattern files, but the architectural scope warrants deep+xhigh routing.

    Returns: (possibly_promoted_tier, promoted_bool).
    Only promotes; never demotes. Safe to call unconditionally.
    """
    if tier == "deep":
        return tier, False
    if not isinstance(query, str):
        return tier, False
    if not isinstance(signals, dict):
        return tier, False

    if not _ARCH_RE.search(query):
        return tier, False

    combo = (
        int(signals.get("standard", 0) or 0)
        + int(signals.get("tool_intensive", 0) or 0)
        + int(signals.get("orchestration", 0) or 0)
    )
    if combo >= 1:
        return "deep", True
    return tier, False
