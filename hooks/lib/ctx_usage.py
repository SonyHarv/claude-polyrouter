"""Context-window usage estimation from JSONL transcript files.

Reads the latest assistant turn in a Claude Code JSONL transcript and
computes what percentage of a 200k-token context window is used.

Results are mtime-cached in ~/.claude/polyrouter-ctx-cache.json to avoid
redundant JSONL parses on every hook invocation.
"""

import json
import os
import time
from pathlib import Path

_CACHE_FILE = Path.home() / ".claude" / "polyrouter-ctx-cache.json"
_CONTEXT_WINDOW = 200_000


def _load_cache() -> dict:
    try:
        if _CACHE_FILE.exists():
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass


def get_context_percent(transcript_path: str | None) -> int | None:
    """Return context-window usage as an integer percentage (0-100), or None.

    Args:
        transcript_path: Path to a Claude Code JSONL transcript file, or None.

    Returns:
        Integer percentage of the 200k-token context used by the most recent
        assistant turn, or None if the value cannot be determined.
    """
    if not transcript_path:
        return None
    try:
        p = Path(transcript_path)
        if not p.exists():
            return None

        mtime = p.stat().st_mtime
        cache_key = str(p)

        cache = _load_cache()
        entry = cache.get(cache_key)
        if entry and entry.get("mtime") == mtime:
            return entry.get("pct")

        # Parse JSONL: find the last assistant message with usage data
        max_tokens = 0
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                # JSONL may be wrapped in a message envelope
                msg = obj.get("message", obj)
                if not isinstance(msg, dict):
                    continue
                if msg.get("role") != "assistant":
                    continue
                usage = msg.get("usage", {})
                if not isinstance(usage, dict):
                    continue
                total = (
                    usage.get("input_tokens", 0)
                    + usage.get("output_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0)
                )
                if total > max_tokens:
                    max_tokens = total

        if max_tokens == 0:
            return None

        pct = min(100, int(max_tokens * 100 / _CONTEXT_WINDOW))
        cache[cache_key] = {"mtime": mtime, "pct": pct}
        _save_cache(cache)
        return pct

    except Exception:
        return None
