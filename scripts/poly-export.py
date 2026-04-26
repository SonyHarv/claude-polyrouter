#!/usr/bin/env python3
"""Export polyrouter stats as CSV or JSON for external analysis.

Reads ``~/.claude/polyrouter-stats.json`` and writes the transformed
output to either a default ``/tmp/polyrouter-export-{ts}.{ext}`` path or
a user-supplied path. The transformation logic lives in
``hooks/lib/export.py`` so the same functions are exercised by the unit
tests and by this CLI wrapper.

Usage:
    python3 scripts/poly-export.py csv [output_path]
    python3 scripts/poly-export.py json [output_path]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
STATS_PATH = Path.home() / ".claude" / "polyrouter-stats.json"

sys.path.insert(0, str(HOOKS_DIR))

from lib import export  # noqa: E402


def _default_path(fmt: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("/tmp") / f"polyrouter-export-{ts}.{fmt}"


def _load_stats() -> dict:
    if not STATS_PATH.exists():
        print(
            f"error: {STATS_PATH} not found — route some queries first",
            file=sys.stderr,
        )
        sys.exit(2)
    return json.loads(STATS_PATH.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export polyrouter stats")
    parser.add_argument("format", choices=("csv", "json"))
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Output path (default: /tmp/polyrouter-export-{timestamp}.{ext})",
    )
    args = parser.parse_args(argv)

    stats = _load_stats()
    payload = export.to_csv(stats) if args.format == "csv" else export.to_json(stats)

    out_path = Path(args.output) if args.output else _default_path(args.format)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload, encoding="utf-8")

    print(f"Wrote {out_path} ({len(payload):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
