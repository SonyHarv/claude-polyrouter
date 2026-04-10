"""Dynamic effort mapping: tier + score → effort level.

Maps routing tiers to Claude Code effort levels. User overrides
(via env var or /effort command) always take priority.
"""

import os

EFFORT_MAP = {
    "fast": "low",
    "standard": "medium",
    "deep": "high",
}

VALID_EFFORTS = {"low", "medium", "high"}


def compute_effort(tier: str, user_override: str | None = None) -> str:
    """Derive effort level from routing tier.

    Priority: user_override > env var > tier mapping.
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
