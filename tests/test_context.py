import json
import re
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import SessionState


class TestSessionState:
    def _make_session(self, tmpdir, timeout_minutes=30):
        path = Path(tmpdir) / "session.json"
        return SessionState(path, timeout_minutes=timeout_minutes)

    def test_new_session_has_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            state = session.read()
            assert state["last_route"] is None
            assert state["conversation_depth"] == 0

    def test_update_persists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            session.update(level="deep", language="es")
            state = session.read()
            assert state["last_route"] == "deep"
            assert state["last_level"] == "deep"
            assert state["last_language"] == "es"
            assert state["conversation_depth"] == 1

    def test_conversation_depth_increments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            session.update(level="fast", language="en")
            session.update(level="standard", language="en")
            session.update(level="deep", language="en")
            state = session.read()
            assert state["conversation_depth"] == 3

    def test_expired_session_resets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.json"
            old_time = time.time() - (31 * 60)
            data = {"last_route": "deep", "last_level": "deep", "conversation_depth": 10, "last_query_time": old_time, "last_language": "es"}
            path.write_text(json.dumps(data))
            session = SessionState(path, timeout_minutes=30)
            state = session.read()
            assert state["last_route"] is None
            assert state["conversation_depth"] == 0

    def test_is_follow_up_with_patterns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            session.update(level="deep", language="en")
            compiled = [re.compile(r"^(and |but |also )", re.IGNORECASE)]
            assert session.is_follow_up("and also fix this", compiled) is True
            assert session.is_follow_up("design a new system", compiled) is False

    def test_is_follow_up_no_previous_route(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            compiled = [re.compile(r"^(and )", re.IGNORECASE)]
            assert session.is_follow_up("and fix this", compiled) is False

    def test_context_boost_for_complex(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            session.update(level="deep", language="en")
            assert session.get_confidence_boost() == 0.1

    def test_no_boost_for_fast(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir)
            session.update(level="fast", language="en")
            assert session.get_confidence_boost() == 0.0

    def test_corrupted_file_handled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.json"
            path.write_text("CORRUPT")
            session = SessionState(path, timeout_minutes=30)
            state = session.read()
            assert state["conversation_depth"] == 0
