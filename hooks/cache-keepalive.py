"""PostToolUse hook: invisible cache keep-alive ping.

Pattern: KAIROS SleepTool from Claude Code source.

Keeps the Anthropic API prompt cache alive (60min TTL) by emitting
a minimal additionalContext when the cache is about to expire.
Does NOT generate visible turns or API calls — it only signals
to Claude that a keep-alive window is approaching.

Since this is a PostToolUse hook, if it fires a tool just completed,
meaning the session IS active. The idle_cutoff guards against stale
session files from a previous run, not against active tool chains.

Logic:
1. Read session state
2. Stale session guard: if last_query_time > idle_cutoff → skip
   (protects against warming cache for dead sessions)
3. Compute last API-warming timestamp = max(last_query, last_keepalive)
4. If now - last_api > threshold → emit keepalive + update timestamp
5. Otherwise: no-op
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.config import DEFAULT_CONFIG, load_config

SESSION_PATH = Path.home() / ".claude" / "polyrouter-session.json"

DEFAULT_KEEPALIVE = {
    "enabled": True,
    "threshold_minutes": 50,
    "idle_cutoff_minutes": 120,
}


def _read_session() -> dict:
    """Read session state, return empty dict on any error."""
    try:
        if SESSION_PATH.exists():
            data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _write_session(data: dict) -> None:
    """Write session state atomically."""
    try:
        SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SESSION_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(SESSION_PATH)
    except Exception:
        pass


def _empty_output() -> dict:
    """No-op hook output."""
    return {}


def _keepalive_output() -> dict:
    """Minimal hook output that keeps the session warm."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "[polyrouter:keepalive] cache-warm",
        }
    }


def main() -> None:
    try:
        config = load_config()
    except Exception:
        config = dict(DEFAULT_CONFIG)

    ka_cfg = config.get("keepalive", DEFAULT_KEEPALIVE)

    if not ka_cfg.get("enabled", True):
        print(json.dumps(_empty_output()))
        return

    threshold_sec = max(0, ka_cfg.get("threshold_minutes", 50)) * 60
    idle_cutoff_sec = max(0, ka_cfg.get("idle_cutoff_minutes", 120)) * 60

    now = time.time()
    session = _read_session()

    last_query_time = session.get("last_query_time")
    last_keepalive = session.get("last_keepalive_time")

    # No session activity at all → skip
    if not last_query_time or not isinstance(last_query_time, (int, float)):
        print(json.dumps(_empty_output()))
        return

    # Stale session guard: if user's last prompt was very long ago,
    # this is likely a leftover session file — don't warm cache.
    if now - last_query_time > idle_cutoff_sec:
        print(json.dumps(_empty_output()))
        return

    # Determine last cache-warming event (most recent of query or keepalive)
    last_api_time = last_query_time
    if last_keepalive and isinstance(last_keepalive, (int, float)):
        last_api_time = max(last_api_time, last_keepalive)

    time_since_api = now - last_api_time

    # Cache still fresh → no action needed
    if time_since_api < threshold_sec:
        print(json.dumps(_empty_output()))
        return

    # Cache about to expire → emit keep-alive and update timestamp
    session["last_keepalive_time"] = now
    _write_session(session)

    print(json.dumps(_keepalive_output()))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps(_empty_output()))
