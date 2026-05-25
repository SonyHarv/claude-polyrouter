"""OAuth usage poller for claude-polyrouter (v1.9.1).

Reads the OAuth token from ~/.claude/.credentials.json (maintained by Claude
Code) and calls https://api.anthropic.com/api/oauth/usage at most once per
POLL_INTERVAL_SEC seconds. Result is cached to polyrouter-usage-cache.json.

Returned fields cover what CC's statusLine stdin does NOT expose:
  - sonnet_weekly_pct / sonnet_weekly_resets_at
  - extra_pct / extra_dollars / extra_limit  (Max plan only)

Failure modes (no creds, expired token, network error, malformed response)
all silently return None so the HUD simplifies its display rather than
crashing. This module never raises.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

POLL_INTERVAL_SEC = 60
CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
CACHE_PATH = Path.home() / ".claude" / "polyrouter-usage-cache.json"
USAGE_ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
REQUEST_TIMEOUT_SEC = 5


def _read_oauth_token() -> str | None:
    try:
        if not CREDENTIALS_PATH.exists():
            return None
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    # CC has used several key names across versions; check known shapes.
    for top_key in ("claudeAiOauth", "oauth", "auth"):
        inner = data.get(top_key)
        if isinstance(inner, dict):
            token = (
                inner.get("accessToken")
                or inner.get("access_token")
                or inner.get("oauthToken")
                or inner.get("token")
            )
            if token:
                return str(token)
    token = (
        data.get("oauthToken")
        or data.get("access_token")
        or data.get("token")
    )
    return str(token) if token else None


def _read_cache() -> dict | None:
    try:
        if not CACHE_PATH.exists():
            return None
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    cached_at = data.get("cached_at", 0)
    try:
        if (time.time() - float(cached_at)) > POLL_INTERVAL_SEC:
            return None
    except (TypeError, ValueError):
        return None
    return data


def _write_cache(data: dict) -> None:
    try:
        payload = dict(data)
        payload["cached_at"] = time.time()
        CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


def _fetch_usage(token: str) -> dict | None:
    try:
        req = urllib.request.Request(
            USAGE_ENDPOINT,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "claude-polyrouter/1.9.2",
            },
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
            body = resp.read().decode("utf-8")
    except Exception:
        return None
    try:
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _to_pct(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_epoch(value) -> int | None:
    if not value:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        pass
    try:
        s = str(value).replace("Z", "+00:00")
        return int(datetime.fromisoformat(s).timestamp())
    except Exception:
        return None


def _normalize(raw: dict) -> dict:
    five = raw.get("five_hour") or {}
    seven = raw.get("seven_day") or {}
    seven_sonnet = raw.get("seven_day_sonnet") or {}
    extra = raw.get("extra_usage") or {}
    return {
        "five_hour_pct": _to_pct(five.get("utilization")),
        "five_hour_resets_at": _to_epoch(five.get("resets_at")),
        "weekly_pct": _to_pct(seven.get("utilization")),
        "weekly_resets_at": _to_epoch(seven.get("resets_at")),
        "sonnet_weekly_pct": _to_pct(seven_sonnet.get("utilization")),
        "sonnet_weekly_resets_at": _to_epoch(seven_sonnet.get("resets_at")),
        "extra_pct": _to_pct(extra.get("utilization")),
        "extra_dollars": _to_pct(extra.get("current_usage")),
        "extra_limit": _to_pct(extra.get("monthly_limit")),
        "extra_enabled": extra.get("is_enabled") is True,
    }


def get_usage() -> dict | None:
    """Return cached or freshly-fetched usage snapshot, or None on any failure."""
    cached = _read_cache()
    if cached:
        return cached
    token = _read_oauth_token()
    if not token:
        return None
    raw = _fetch_usage(token)
    if not raw:
        return None
    normalized = _normalize(raw)
    _write_cache(normalized)
    normalized["cached_at"] = time.time()
    return normalized
