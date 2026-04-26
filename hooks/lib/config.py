"""Configuration loading with three-layer merge: defaults -> global -> project.

v1.7 (CALIDAD #16): Tier infrastructure is now data-driven.

  - `tier_order` is the canonical escalation order. To add a new tier
    (e.g. "ultra"), append it here AND under `levels`. No code changes
    are required in scorer.py / effort.py — they read from config.
  - `scoring.thresholds` defines `<tier>_max` boundaries for every tier
    except the last (which is the catch-all). With N tiers there are
    N-1 thresholds.
  - Each `levels[<tier>]` entry carries `default_effort`, removing the
    hardcoded EFFORT_MAP coupling in effort.py.
  - `cost_per_1k_input` / `cost_per_1k_output` may be `null`, in which
    case savings calculations treat the tier as zero-cost (useful when
    a new tier is wired up before its public pricing is finalized).

See `docs/ADDING-A-TIER.md` for the runbook.
"""

import copy
import json
import os
import sys
from pathlib import Path

GLOBAL_CONFIG_PATH = Path.home() / ".claude" / "polyrouter" / "config.json"

DEFAULT_CONFIG = {
    "version": "1.4.0",
    # Canonical tier escalation order. Routing scores ascend through
    # this list. The last entry is the unbounded catch-all tier.
    "tier_order": ["fast", "standard", "deep"],
    "levels": {
        "fast": {
            "model": "haiku",
            "model_id": "claude-haiku-4-5",
            "agent": "fast-executor",
            "default_effort": "low",
            "cost_per_1k_input": 0.001,
            "cost_per_1k_output": 0.005,
        },
        "standard": {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-6",
            "agent": "standard-executor",
            "default_effort": "medium",
            "cost_per_1k_input": 0.003,
            "cost_per_1k_output": 0.015,
        },
        "deep": {
            "model": "opus",
            "model_id": "claude-opus-4-7",
            "agent": "deep-executor",
            "default_effort": "high",
            "cost_per_1k_input": 0.015,
            "cost_per_1k_output": 0.075,
        },
    },
    "default_level": "fast",
    "confidence_threshold": 0.7,
    # Score → tier boundaries. With tier_order = [t0, t1, ..., tn], expect
    # `<tier>_max` for every tier except the last; thresholds must be
    # monotonically increasing. Missing thresholds fall back to the
    # 0.35 / 0.65 defaults preserved from v1.4.
    "scoring": {
        "thresholds": {
            "fast_max": 0.35,
            "standard_max": 0.65,
        },
    },
    # Tokenizer calibration: Claude 4.x family produces ~1.35× the tokens
    # of the pre-4.x tokenizer used to derive the per-prompt token estimates
    # in _calculate_savings. Applied uniformly across all tiers because
    # haiku-4-5 / sonnet-4-6 / opus-4-7 share the same tokenizer family.
    # Set to 1.0 to recover pre-calibration behavior; bump if a future model
    # family changes the ratio again.
    "tokenizer_factor": 1.35,
    "session_timeout_minutes": 30,
    "cache": {"memory_size": 50, "file_size": 100, "ttl_days": 30},
    "learning": {"enabled": False, "informed_routing": False, "max_boost": 0.1},
    "keepalive": {"enabled": True, "threshold_minutes": 50, "idle_cutoff_minutes": 120},
    "compact": {"enabled": True, "keep_last_n": 5, "circuit_breaker_max": 3},
    "hud": {"mascot_enabled": True, "statusline_native": True, "minimal_context": True},
    "updates": {"check_on_start": True, "repo": "sonyharv/claude-polyrouter"},
}


def _merge_config(base: dict, override: dict) -> dict:
    """Shallow merge: dict values are merged one level, scalars are replaced."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = {**result[key], **value}
        else:
            result[key] = value
    return result


def find_project_config() -> Path | None:
    """Search from CWD upward for .claude-polyrouter/config.json.

    Security: stops at .git boundary or home directory to prevent
    path traversal outside the project.
    """
    current = Path.cwd().resolve()
    home = Path.home().resolve()
    while current != current.parent and current != home:
        candidate = current / ".claude-polyrouter" / "config.json"
        if candidate.exists():
            # Verify resolved path is under current dir (no symlink traversal)
            try:
                resolved = candidate.resolve()
                current_prefix = str(current) + os.sep
                if str(resolved).startswith(current_prefix) or resolved == current:
                    return candidate
            except (OSError, ValueError):
                pass
            return None
        if (current / ".git").exists():
            break
        current = current.parent
    return None


def _read_json_safe(path: Path) -> dict | None:
    """Read and parse JSON file, return None on any error or non-dict."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def validate_config(config: dict) -> list[str]:
    """Lenient post-merge validation. Returns list of warning strings.

    Warnings are emitted to stderr but never raise — bad config falls back
    to defaults so the hook never blocks user input.

    Checks:
      - tier_order entries all exist in levels (and vice-versa)
      - one `<tier>_max` threshold per non-terminal tier
      - thresholds are monotonically increasing
      - each level has a default_effort that is in the env-valid set
    """
    warnings: list[str] = []
    tier_order = config.get("tier_order") or []
    levels = config.get("levels") or {}

    if not isinstance(tier_order, list) or not tier_order:
        warnings.append("tier_order missing or invalid; routing will use levels keys")
        return warnings

    # Tier_order ↔ levels parity
    extra_in_order = [t for t in tier_order if t not in levels]
    extra_in_levels = [t for t in levels if t not in tier_order]
    for t in extra_in_order:
        warnings.append(f"tier_order references '{t}' which has no levels.{t} entry")
    for t in extra_in_levels:
        warnings.append(f"levels.{t} defined but missing from tier_order")

    # Thresholds
    thresholds = (config.get("scoring") or {}).get("thresholds") or {}
    expected_keys = [f"{t}_max" for t in tier_order[:-1]]
    last = -float("inf")
    for key in expected_keys:
        if key not in thresholds:
            warnings.append(f"scoring.thresholds.{key} missing; defaulting to legacy value")
            continue
        try:
            v = float(thresholds[key])
        except (TypeError, ValueError):
            warnings.append(f"scoring.thresholds.{key} is not numeric")
            continue
        if v <= last:
            warnings.append(
                f"scoring.thresholds.{key}={v} not greater than previous boundary"
            )
        last = v

    # Per-level default_effort
    valid_efforts = {"low", "medium", "high", "xhigh"}
    for tier, lv in levels.items():
        eff = lv.get("default_effort")
        if eff is not None and eff not in valid_efforts:
            warnings.append(
                f"levels.{tier}.default_effort='{eff}' not in {sorted(valid_efforts)}"
            )

    return warnings


def load_config(*, emit_warnings: bool = True) -> dict:
    """Load config with three-layer merge: defaults -> global -> project.

    When `emit_warnings` is True, validation warnings are printed to stderr
    so the user sees misconfiguration without the hook blocking.
    """
    config = copy.deepcopy(DEFAULT_CONFIG)

    global_cfg = _read_json_safe(GLOBAL_CONFIG_PATH)
    if global_cfg:
        config = _merge_config(config, global_cfg)

    project_path = find_project_config()
    if project_path:
        project_cfg = _read_json_safe(project_path)
        if project_cfg:
            config = _merge_config(config, project_cfg)

    if emit_warnings:
        for w in validate_config(config):
            print(f"[polyrouter] config warning: {w}", file=sys.stderr)

    return config
