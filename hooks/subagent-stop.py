#!/usr/bin/env python3
"""SubagentStop hook — clear subagent_active flag when subagent finishes.

Signals the HUD that the polyrouter subagent is no longer running so the
"(subagente)" tag is removed from the status line.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.context import SessionState  # noqa: E402

SESSION_PATH = Path.home() / ".claude" / "polyrouter-session.json"


def main() -> None:
    try:
        session = SessionState(SESSION_PATH)
        session.mark_subagent_stopped()
    except Exception:
        pass
    print(json.dumps({}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({}))
