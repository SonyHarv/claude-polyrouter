"""Dynamic effort mapping: tier + score → effort level.

v1.5: Deep tier supports sub-effort (medium/high/xhigh) derived from
multi-signal complexity analysis. `xhigh` is a polyrouter-only display
label — it normalizes to `high` before being emitted as the Claude Code
`CLAUDE_CODE_EFFORT_LEVEL` env var (upstream only supports low/medium/high).
`xhigh` additionally flags `requires_advisor=true` for the Advisor Strategy.

v1.6: Architectural complexity detection (_ARCH_RE) is now language-aware.
Each language JSON may define `arch_patterns`; English patterns serve as
the universal fallback for unknown languages.

User overrides (via env var or /effort command) always take priority.
"""

import json
import os
import re
from functools import lru_cache
from pathlib import Path

EFFORT_MAP = {
    "fast": "low",
    "standard": "medium",
    "deep": "high",
}

# Env-var-valid efforts (what Claude Code understands)
VALID_EFFORTS = {"low", "medium", "high"}

# Display-valid efforts (what HUD / session / logs can show)
DISPLAY_EFFORTS = {"low", "medium", "high", "xhigh"}


# --- Language-aware architectural-complexity detection (xhigh gate) ---

# Location of language JSON files (resolved relative to this file)
_LANG_DIR = Path(__file__).parent.parent.parent / "languages"

# Hardcoded EN fallback patterns (used when language file is unavailable)
_EN_ARCH_PATTERNS = [
    r"\b(architecture|architect|architectural|system\s+design)\b",
    r"\b(redesign\w*|overhaul|re-?architect)\b",
    r"\b(major\s+refactor|strategic\s+refactor|critical\s+refactor|design\s+decision|migration\s+strategy|extraction\s+plan)\b",
    r"\b(distributed|multi-?region|zero-?downtime|microservices|monolithic|event-?driven)\b",
    r"\b(bounded\s+context|modular\s+monolith|monolith\s+to\s+microservices|ADR|architectural\s+decision)\b",
]

_FALLBACK_ARCH_RE = re.compile(
    "|".join(_EN_ARCH_PATTERNS),
    re.IGNORECASE,
)


@lru_cache(maxsize=32)
def _load_arch_re(language: str) -> re.Pattern:
    """Load and compile arch_patterns for a given language code.

    Falls back to the EN fallback regex for unknown/missing language files.
    Result is cached per language code.
    """
    lang_file = _LANG_DIR / f"{language}.json"
    try:
        with open(lang_file, encoding="utf-8") as f:
            data = json.load(f)
        patterns = data.get("arch_patterns")
        if patterns and isinstance(patterns, list) and len(patterns) > 0:
            return re.compile("|".join(patterns), re.IGNORECASE)
    except (OSError, json.JSONDecodeError, re.error):
        pass
    return _FALLBACK_ARCH_RE


# Keep a module-level alias for callers that don't pass language
# (compute_deep_effort internal use, backward compat)
def _arch_re(language: str = "en") -> re.Pattern:
    return _load_arch_re(language)


# Mirrors scorer.py — kept local to avoid circular import
_FILE_EXT_RE = re.compile(
    r"(?:[\s(]|^)(?:/[\w./-]+|\w+\.(?:py|js|ts|tsx|go|rs|java|rb|php|c|cpp|h|css|html|sql|yaml|yml|json|toml|md|sh)\b)"
)

_CODE_BLOCK_RE = re.compile(r"```")


# --- Feature #5: Multi-file refactor promotion ---

_REFACTOR_VERB_RE = re.compile(
    r"\b(refactor|restructure|rewrite|"
    r"refactoriza|reestructura|reescrib[ea]|"       # ES
    r"refactoriser|restructurer|r[eé][eé]crire|"   # FR
    r"umstrukturieren|refaktorieren|umschreiben|"   # DE
    r"refatorar|reestruturar|reescrever)\b",         # PT
    re.IGNORECASE,
)

_FILE_EXT_MULTIFILE_RE = re.compile(
    r"\b[\w/\-.]+\.(py|js|ts|tsx|jsx|go|rs|java|kt|cpp|c|h|hpp|cs|rb|php|swift|scala|sh|yaml|yml|json|sql|md|html|css|scss)\b",
    re.IGNORECASE,
)

_MULTI_FILE_QUALIFIER_RE = re.compile(
    r"\b(across|multiple|throughout|all)\s+(\d+\s+)?(files?|modules?|components?|services?)\b|"
    r"\b(these|those|several|some|\d+)\s+(\w+\s+)?(files?|modules?|components?|services?)\b|"
    r"\b(a\s+trav[eé]s\s+de|varios|todos\s+los)\s+(\d+\s+)?(archivos?|m[oó]dulos?|componentes?)\b|"
    r"\b(quer\s+durch|mehrere|alle)\s+(\d+\s+)?(Dateien?|Module|Komponenten)\b|"
    r"\b(à\s+travers|plusieurs|tous\s+les)\s+(\d+\s+)?(fichiers?|modules?|composants?)\b|"
    r"\b(em\s+v[aá]rios|diversos|todos\s+os)\s+(\d+\s+)?(arquivos?|m[oó]dulos?|componentes?)\b",
    re.IGNORECASE,
)


def maybe_promote_multifile_refactor(query: str, tier: str) -> bool:
    """Return True if prompt has a refactor-family verb and either ≥2 file
    references or a multi-file qualifier phrase.

    Only promotes standard → deep. Requires ≥6 words to avoid false positives.
    """
    if tier != "standard":
        return False
    words = query.split()
    if len(words) < 6:
        return False
    if not _REFACTOR_VERB_RE.search(query):
        return False
    # Count distinct file references (dedupe on matched text)
    file_refs = set(m.group(0).lower() for m in _FILE_EXT_MULTIFILE_RE.finditer(query))
    has_qualifier = bool(_MULTI_FILE_QUALIFIER_RE.search(query))
    return len(file_refs) >= 2 or has_qualifier


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
    language: str = "en",
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

    arch_re = _arch_re(language)
    arch_hit = bool(arch_re.search(query))
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
    language: str = "en",
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

    arch_re = _arch_re(language)
    if not arch_re.search(query):
        return tier, False

    combo = (
        int(signals.get("standard", 0) or 0)
        + int(signals.get("tool_intensive", 0) or 0)
        + int(signals.get("orchestration", 0) or 0)
    )
    if combo >= 1:
        return "deep", True
    return tier, False
