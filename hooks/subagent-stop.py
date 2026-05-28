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
from lib.config import SESSION_PATH  # noqa: E402
from lib.ctx_usage import get_last_assistant_model  # noqa: E402


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    try:
        session = SessionState(SESSION_PATH)
        session.mark_subagent_stopped()

        # Leer modelo real que CC usó para el subagente y sobrescribir la
        # predicción de poly con el modelo efectivo (read from transcript).
        transcript_path = data.get("transcript_path")
        if transcript_path:
            real_model = get_last_assistant_model(transcript_path)
            if real_model:
                session.update_exec_model_real(real_model)
    except Exception:
        pass

    print(json.dumps({}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({}))
