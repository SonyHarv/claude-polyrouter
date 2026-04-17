"""Rate-limit integration via ccusage CLI.

# Optional dependency: this module gracefully no-ops (returns None) when ccusage is absent.
# Install ccusage for 5h/weekly/sonnet limit display in the HUD:
#   npm install -g ccusage   (or: pip install ccusage)

Calls `ccusage --json` (if installed) and returns structured limit data.
Results are cached for 30 seconds in ~/.claude/polyrouter-limits-cache.json.

If ccusage is not installed or the output cannot be parsed, all functions
return None gracefully — callers must handle None.

Expected ccusage JSON schema (best-effort; actual output may vary):
{
  "five_hour": {"used_pct": 45, "reset_in_seconds": 3720},
  "weekly": {"used_pct": 9, "reset_in_seconds": 596340},
  "sonnet_weekly": {"used_pct": 3, "reset_in_seconds": 596340}
}
"""

import json
import subprocess
import time
from pathlib import Path

_CACHE_FILE = Path.home() / ".claude" / "polyrouter-limits-cache.json"
_TTL_SECONDS = 30


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


def _parse_ccusage_output(data: dict) -> dict:
    """Normalise ccusage JSON into the limits schema.

    Handles both the expected schema and common variations.
    Returns a dict with keys: five_hour_pct, five_hour_remaining_sec,
    weekly_pct, weekly_remaining_sec, sonnet_weekly_pct,
    sonnet_weekly_remaining_sec, updated_at.
    """
    def _extract(block: dict | None) -> tuple[int | None, int | None]:
        if not block or not isinstance(block, dict):
            return None, None
        pct = block.get("used_pct") or block.get("percent") or block.get("pct")
        rem = (
            block.get("reset_in_seconds")
            or block.get("remaining_seconds")
            or block.get("resets_in")
        )
        return (int(pct) if pct is not None else None,
                int(rem) if rem is not None else None)

    fh_pct, fh_rem = _extract(data.get("five_hour") or data.get("5hour") or data.get("fiveHour"))
    wk_pct, wk_rem = _extract(data.get("weekly") or data.get("week"))
    snt_pct, snt_rem = _extract(data.get("sonnet_weekly") or data.get("sonnetWeekly") or data.get("sonnet"))

    return {
        "five_hour_pct": fh_pct,
        "five_hour_remaining_sec": fh_rem,
        "weekly_pct": wk_pct,
        "weekly_remaining_sec": wk_rem,
        "sonnet_weekly_pct": snt_pct,
        "sonnet_weekly_remaining_sec": snt_rem,
        "updated_at": time.time(),
    }


def get_limits() -> dict | None:
    """Return current rate-limit stats from ccusage, or None.

    Results are cached for 30s to avoid hammering the CLI.
    """
    cache = _load_cache()
    cached = cache.get("data")
    cached_at = cache.get("updated_at", 0)
    if cached and (time.time() - cached_at) < _TTL_SECONDS:
        return cached

    try:
        result = subprocess.run(
            ["ccusage", "--json"],
            timeout=2,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        raw = json.loads(result.stdout)
        limits = _parse_ccusage_output(raw)
        cache["data"] = limits
        cache["updated_at"] = time.time()
        _save_cache(cache)
        return limits
    except FileNotFoundError:
        # ccusage not installed — degrade gracefully
        return None
    except Exception:
        return None
