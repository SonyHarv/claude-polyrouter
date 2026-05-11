"""v1.8: CC v2.1.122+ effort.level passthrough + skew detection."""
import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
from lib.context import SessionState


def test_update_cc_effort_persists(tmp_path):
    s = SessionState(tmp_path / "session.json")
    s.update_cc_effort("xhigh")
    state = json.loads((tmp_path / "session.json").read_text())
    assert state["cc_effort_level"] == "xhigh"


def test_update_cc_effort_normalizes_max_to_high(tmp_path):
    s = SessionState(tmp_path / "session.json")
    s.update_cc_effort("max")
    state = json.loads((tmp_path / "session.json").read_text())
    assert state["cc_effort_level"] == "high"


def test_effort_skew_when_poly_and_cc_differ(tmp_path):
    s = SessionState(tmp_path / "session.json")
    s.update_effort("xhigh")     # poly decided xhigh
    s.update_cc_effort("medium")  # CC executed medium
    state = json.loads((tmp_path / "session.json").read_text())
    assert state["effort_skew_detected"] is True


def test_no_skew_when_aligned(tmp_path):
    s = SessionState(tmp_path / "session.json")
    s.update_effort("high")
    s.update_cc_effort("high")
    state = json.loads((tmp_path / "session.json").read_text())
    assert state["effort_skew_detected"] is False


def test_no_skew_when_cc_unknown(tmp_path):
    s = SessionState(tmp_path / "session.json")
    s.update_effort("high")
    s.update_cc_effort(None)
    state = json.loads((tmp_path / "session.json").read_text())
    assert state["effort_skew_detected"] is False


def test_update_cc_effort_rejects_invalid(tmp_path):
    s = SessionState(tmp_path / "session.json")
    # Seed state so the file exists without touching cc_effort_level
    s.update_effort("medium")
    s.update_cc_effort("bogus")  # silently ignored
    state = json.loads((tmp_path / "session.json").read_text())
    # No cc_effort_level write — either absent or still None
    assert state.get("cc_effort_level") is None
