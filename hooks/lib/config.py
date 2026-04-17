"""Configuration loading with three-layer merge: defaults -> global -> project."""

import copy
import json
import os
from pathlib import Path

GLOBAL_CONFIG_PATH = Path.home() / ".claude" / "polyrouter" / "config.json"

DEFAULT_CONFIG = {
    "version": "1.4.0",
    "levels": {
        "fast": {
            "model": "haiku",
            "model_id": "claude-haiku-4-5",
            "agent": "fast-executor",
            "cost_per_1k_input": 0.001,
            "cost_per_1k_output": 0.005,
        },
        "standard": {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-6",
            "agent": "standard-executor",
            "cost_per_1k_input": 0.003,
            "cost_per_1k_output": 0.015,
        },
        "deep": {
            "model": "opus",
            "model_id": "claude-opus-4-7",
            "agent": "deep-executor",
            "cost_per_1k_input": 0.015,
            "cost_per_1k_output": 0.075,
        },
    },
    "default_level": "fast",
    "confidence_threshold": 0.7,
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


def load_config() -> dict:
    """Load config with three-layer merge: defaults -> global -> project."""
    config = copy.deepcopy(DEFAULT_CONFIG)

    global_cfg = _read_json_safe(GLOBAL_CONFIG_PATH)
    if global_cfg:
        config = _merge_config(config, global_cfg)

    project_path = find_project_config()
    if project_path:
        project_cfg = _read_json_safe(project_path)
        if project_cfg:
            config = _merge_config(config, project_cfg)

    return config
