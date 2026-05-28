#!/usr/bin/env python3
"""PreToolUse:Task hook (v1.8.1) — populate exec_* session fields for HUD.

Fires when Claude Code dispatches a polyrouter subagent via the Task tool.
Reads the routing decision (last_level / effort_level / requires_advisor)
that classify-prompt already persisted to session state and projects it
onto exec_model / exec_effort / exec_advisor + increments subagent_count
so the HUD can render:

    [poly v1.8] [^.^]~ prompt:haiku·fast ⚙ exec:haiku │ 🤖1 cache:████░ ...

Pure rule-based: no model calls, no extra tokens. Reads/writes JSON state
on disk only. Filters by substring "polyrouter" in subagent_type so
non-poly subagents (OMC, ECC, generic) don't pollute exec_*/subagent_count.

exec_effort projection:
  - level == "deep" and effort in ("high", "xhigh") → surface effort
  - all other tiers → omit effort (tier-short already conveys it)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.context import SessionState  # noqa: E402
from lib.config import SESSION_PATH  # noqa: E402

_TIER_TO_MODEL = {"fast": "haiku", "standard": "sonnet", "deep": "opus"}


def _resolve_exec_effort(level: str | None, effort: str | None) -> str | None:
    """Only surface effort on deep+high/xhigh; fast/standard omit it."""
    if level == "deep" and effort in ("high", "xhigh"):
        return effort
    return None


def _process(data: dict, session: SessionState) -> None:
    """Apply mark_subagent_active when the Task call is for a poly subagent."""
    tool_name = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}
    subagent_type = tool_input.get("subagent_type") or ""

    # Only act on poly's own Task invocations. Substring match tolerates
    # both "polyrouter:fast-executor" and "claude-polyrouter:fast-executor".
    if tool_name not in ("Task", "Agent") or "polyrouter" not in subagent_type:
        return

    state = session.read()
    level = state.get("last_level")
    exec_model = _TIER_TO_MODEL.get(level)
    if not exec_model:
        return

    exec_effort = _resolve_exec_effort(level, state.get("effort_level"))
    exec_advisor = bool(state.get("requires_advisor"))

    session.mark_subagent_active(
        subagent_name=subagent_type,
        exec_model=exec_model,
        exec_effort=exec_effort,
        exec_advisor=exec_advisor,
    )


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw else {}
    except Exception:
        print("{}")
        return

    try:
        session = SessionState(SESSION_PATH)
        _process(data, session)
    except Exception:
        # Hook must never block the Task dispatch.
        pass

    print("{}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("{}")
