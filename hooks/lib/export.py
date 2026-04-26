"""Export polyrouter stats as CSV (long-format summary) or JSON (record arrays).

Pure transformation functions — no file I/O, no CLI. The slash command
(``/polyrouter:export``) and the runner script (``scripts/poly-export.py``)
read ``~/.claude/polyrouter-stats.json``, call into here, and write the
result. Keeping the logic pure makes it unit-testable without touching disk.

CSV layout (Q2(c) "summary una fila por dimensión"): three columns —
``dimension``, ``key``, ``value`` — covering ``summary`` scalars, per-tier
``routes``, per-language counts, and ``session`` rows with date-prefixed
keys. The long format means new dimensions or extra tiers do not change
the column header, so consumers (Excel, sed/awk, pandas long→wide) keep
working when the polyrouter schema grows.

JSON layout (Q3(b) "reformateado a arrays de registros"): the dict-of-dicts
in ``polyrouter-stats.json`` is reshaped into record arrays so
``pandas.DataFrame(payload['sessions'])`` and ``jq '.routes[]'`` both work
without further unwrapping.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

# Scalar fields that belong in the "summary" block. Order matters for CSV
# determinism; tests assert on the row sequence so consumers can rely on
# stable diffs.
_SUMMARY_KEYS = (
    "version",
    "total_queries",
    "cache_hits",
    "estimated_savings",
    "last_updated",
)


def to_csv(stats: dict[str, Any]) -> str:
    """Serialize ``stats`` into long-format CSV with header.

    Output columns: ``dimension`` ∈ {summary, routes, languages, session},
    ``key``, ``value``. Sessions emit one row per (date, field) pair plus
    one row per (date, tier) for nested route counts.
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["dimension", "key", "value"])

    for k in _SUMMARY_KEYS:
        if k in stats:
            w.writerow(["summary", k, stats[k]])

    for tier, count in (stats.get("routes") or {}).items():
        w.writerow(["routes", tier, count])

    for lang, count in (stats.get("languages_detected") or {}).items():
        w.writerow(["languages", lang, count])

    for session in stats.get("sessions") or []:
        date = session.get("date", "unknown")
        for field in ("queries", "cache_hits", "savings"):
            if field in session:
                w.writerow(["session", f"{date}.{field}", session[field]])
        for tier, count in (session.get("routes") or {}).items():
            w.writerow(["session", f"{date}.routes.{tier}", count])

    return buf.getvalue()


def to_json(stats: dict[str, Any]) -> str:
    """Serialize ``stats`` into a pandas/jq-friendly record-array shape.

    Always emits the four top-level keys (``summary``, ``routes``,
    ``languages``, ``sessions``) even if the source dict is sparse, so
    downstream code can rely on the schema. Sessions are flattened —
    nested ``routes`` dicts become ``routes_<tier>`` columns — to preserve
    DataFrame compatibility (one record = one row, homogeneous keys).
    """
    summary = {k: stats.get(k) for k in _SUMMARY_KEYS if k in stats}

    routes = [
        {"tier": t, "count": c}
        for t, c in (stats.get("routes") or {}).items()
    ]
    languages = [
        {"language": lang, "count": c}
        for lang, c in (stats.get("languages_detected") or {}).items()
    ]

    sessions = []
    for s in stats.get("sessions") or []:
        flat: dict[str, Any] = {
            "date": s.get("date"),
            "queries": s.get("queries"),
            "cache_hits": s.get("cache_hits"),
            "savings": s.get("savings"),
        }
        for tier, count in (s.get("routes") or {}).items():
            flat[f"routes_{tier}"] = count
        sessions.append(flat)

    return json.dumps(
        {
            "summary": summary,
            "routes": routes,
            "languages": languages,
            "sessions": sessions,
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"
