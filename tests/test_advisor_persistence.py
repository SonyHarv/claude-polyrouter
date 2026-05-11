"""v1.8: verify requires_advisor survives mark_subagent_stopped (bug B fix)."""
import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
from lib.context import SessionState


def test_requires_advisor_persists_after_subagent_stop(tmp_path):
    state_path = tmp_path / "session.json"
    s = SessionState(state_path)
    s.update("deep", "en", requires_advisor=True)
    s.update_effort("xhigh")
    s.set_advisor(True)
    s.mark_subagent_active(exec_model="opus", exec_effort="xhigh", exec_advisor=True)

    # Simulate SubagentStop firing
    s.mark_subagent_stopped()

    state = json.loads(state_path.read_text())
    assert state["subagent_active"] is False
    assert state["requires_advisor"] is True, "v1.8 bug B fix: should not be wiped"
    assert state["effort_level"] == "xhigh"
    assert state["exec_advisor"] is True


def test_requires_advisor_clears_on_next_update(tmp_path):
    """Confirm normal turn boundary clears requires_advisor via update() default."""
    state_path = tmp_path / "session.json"
    s = SessionState(state_path)
    s.set_advisor(True)
    assert json.loads(state_path.read_text())["requires_advisor"] is True

    # Normal next turn — no advisor
    s.update("fast", "en")
    assert json.loads(state_path.read_text())["requires_advisor"] is False
