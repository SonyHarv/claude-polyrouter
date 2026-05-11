#!/usr/bin/env python3
"""SessionStart hook — reset subagent tracking fields (v1.8.3).

Safety net so 🤖N counter and subagent_active flag don't persist stale
from a prior session that crashed before SubagentStop fired. Idempotent
and silent: never blocks session start, swallows all errors.
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
        session.reset_subagent_state()
    except Exception:
        pass
    print(json.dumps({}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({}))
