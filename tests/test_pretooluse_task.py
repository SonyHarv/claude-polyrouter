"""v1.8.1: PreToolUse:Task hook tests.

Verifies that pretooluse-task.py projects classify-prompt's routing
decision (last_level/effort_level/requires_advisor) onto the exec_*
session fields when Claude Code dispatches a polyrouter subagent.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import SessionState  # noqa: E402

# Load pretooluse-task.py as a module (filename has a hyphen).
_HOOK_PATH = Path(__file__).parent.parent / "hooks" / "pretooluse-task.py"
_spec = importlib.util.spec_from_file_location("pretooluse_task", _HOOK_PATH)
pretooluse_task = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pretooluse_task)


@pytest.fixture
def session(tmp_path):
    return SessionState(tmp_path / "session.json")


class TestResolveExecEffort:
    """Effort surfacing rule: only deep+high/xhigh gets a suffix."""

    def test_deep_xhigh_surfaces(self):
        assert pretooluse_task._resolve_exec_effort("deep", "xhigh") == "xhigh"

    def test_deep_high_surfaces(self):
        assert pretooluse_task._resolve_exec_effort("deep", "high") == "high"

    def test_deep_medium_omitted(self):
        assert pretooluse_task._resolve_exec_effort("deep", "medium") is None

    def test_deep_low_omitted(self):
        assert pretooluse_task._resolve_exec_effort("deep", "low") is None

    def test_fast_any_effort_omitted(self):
        assert pretooluse_task._resolve_exec_effort("fast", "xhigh") is None
        assert pretooluse_task._resolve_exec_effort("fast", "high") is None
        assert pretooluse_task._resolve_exec_effort("fast", None) is None

    def test_standard_any_effort_omitted(self):
        assert pretooluse_task._resolve_exec_effort("standard", "high") is None
        assert pretooluse_task._resolve_exec_effort("standard", "xhigh") is None

    def test_none_level_omits(self):
        assert pretooluse_task._resolve_exec_effort(None, "xhigh") is None


class TestProcess:
    """_process() applies mark_subagent_active when conditions match."""

    def test_fast_polyrouter_subagent_marks_active(self, session):
        session.update("fast", "en")
        data = {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "polyrouter:fast-executor"},
        }
        pretooluse_task._process(data, session)
        s = session.read()
        assert s["subagent_active"] is True
        assert s["subagent_count"] == 1
        assert s["exec_model"] == "haiku"
        assert s["exec_effort"] is None  # fast tier omits effort
        assert s["exec_advisor"] is False

    def test_standard_polyrouter_subagent(self, session):
        session.update("standard", "es")
        data = {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "polyrouter:standard-executor"},
        }
        pretooluse_task._process(data, session)
        s = session.read()
        assert s["exec_model"] == "sonnet"
        assert s["exec_effort"] is None

    def test_deep_xhigh_with_advisor(self, session):
        session.update("deep", "en", requires_advisor=True)
        session.update_effort("xhigh")
        data = {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "polyrouter:deep-executor"},
        }
        pretooluse_task._process(data, session)
        s = session.read()
        assert s["exec_model"] == "opus"
        assert s["exec_effort"] == "xhigh"
        assert s["exec_advisor"] is True

    def test_deep_medium_effort_omitted(self, session):
        session.update("deep", "en")
        session.update_effort("medium")
        data = {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "polyrouter:deep-executor"},
        }
        pretooluse_task._process(data, session)
        s = session.read()
        assert s["exec_model"] == "opus"
        assert s["exec_effort"] is None  # medium not surfaced

    def test_claude_polyrouter_prefix_also_matched(self, session):
        """Substring match tolerates both 'polyrouter:' and 'claude-polyrouter:'."""
        session.update("fast", "en")
        data = {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "claude-polyrouter:fast-executor"},
        }
        pretooluse_task._process(data, session)
        assert session.read()["subagent_active"] is True

    def test_non_poly_subagent_ignored(self, session):
        session.update("fast", "en")
        data = {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "oh-my-claudecode:executor"},
        }
        pretooluse_task._process(data, session)
        s = session.read()
        assert s["subagent_active"] is False
        assert s["subagent_count"] == 0
        assert s["exec_model"] is None

    def test_non_task_tool_ignored(self, session):
        session.update("fast", "en")
        data = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        }
        pretooluse_task._process(data, session)
        assert session.read()["subagent_active"] is False

    def test_no_last_level_no_op(self, session):
        # First turn — no routing yet, but somehow a Task fires.
        data = {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "polyrouter:fast-executor"},
        }
        pretooluse_task._process(data, session)
        s = session.read()
        assert s["subagent_active"] is False
        assert s["exec_model"] is None

    def test_subagent_count_accumulates_across_tasks(self, session):
        session.update("fast", "en")
        data = {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "polyrouter:fast-executor"},
        }
        pretooluse_task._process(data, session)
        pretooluse_task._process(data, session)
        pretooluse_task._process(data, session)
        assert session.read()["subagent_count"] == 3

    def test_missing_tool_input_no_crash(self, session):
        session.update("fast", "en")
        pretooluse_task._process({"tool_name": "Task"}, session)
        # No subagent_type → ignored.
        assert session.read()["subagent_active"] is False

    def test_empty_dict_no_crash(self, session):
        pretooluse_task._process({}, session)
        assert session.read()["subagent_active"] is False
