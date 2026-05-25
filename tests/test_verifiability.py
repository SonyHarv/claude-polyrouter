"""Unit tests for detect_verifiability() and SessionState.update_verifiability() (v1.9.1).

Karpathy verifiability routing: queries are classified as verifiable
(code/tests/math — promote to deep) or non_verifiable (design/writing/opinion —
keep on standard). Classification requires ≥2 distinct pattern hits; otherwise
returns ("unknown", 0.5).
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import DEFAULT_SESSION, SessionState  # noqa: E402


def _classify_module():
    """Lazy-load classify-prompt.py (hyphen prevents normal import)."""
    spec = importlib.util.spec_from_file_location(
        "classify_prompt",
        Path(__file__).parent.parent / "hooks" / "classify-prompt.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def detect_verifiability():
    return _classify_module().detect_verifiability


class TestDetectVerifiability:
    def test_code_task_is_verifiable(self, detect_verifiability):
        # hits: "tests" + "fix bug" (no "the" — regex demands fix\s+(el\s+)?bug)
        vtype, conf = detect_verifiability("fix bug in authentication tests")
        assert vtype == "verifiable"
        assert conf >= 0.7

    def test_design_task_is_non_verifiable(self, detect_verifiability):
        # hits: "diseña"/"mockup" + "describe" → 2 patterns
        vtype, conf = detect_verifiability(
            "diseña un mockup para el dashboard y describe el flujo"
        )
        assert vtype == "non_verifiable"
        assert conf >= 0.7

    def test_ambiguous_is_unknown(self, detect_verifiability):
        vtype, conf = detect_verifiability("hola")
        assert vtype == "unknown"
        assert conf == 0.5

    def test_spanish_verifiable(self, detect_verifiability):
        # hits: "corrige...bug" + "función" + "tests" → 3 patterns
        vtype, conf = detect_verifiability(
            "corrige el bug en la función de autenticación y agrega tests"
        )
        assert vtype == "verifiable"

    def test_english_non_verifiable(self, detect_verifiability):
        # hits: "design" + "write" → 2 patterns (use exact base forms, \b is strict)
        vtype, conf = detect_verifiability(
            "design a mockup and write the spec for the homepage"
        )
        assert vtype == "non_verifiable"

    def test_confidence_bounded(self, detect_verifiability):
        # hits: "tests" + "verify" → 2 patterns
        vtype, conf = detect_verifiability(
            "implement test suite for payment module and verify edge cases"
        )
        assert 0.0 <= conf <= 1.0

    def test_empty_query_is_unknown(self, detect_verifiability):
        vtype, conf = detect_verifiability("")
        assert vtype == "unknown"
        assert conf == 0.5

    def test_non_string_is_unknown(self, detect_verifiability):
        vtype, conf = detect_verifiability(None)
        assert vtype == "unknown"

    def test_single_hit_returns_unknown(self, detect_verifiability):
        # only one pattern hit → below threshold
        vtype, _ = detect_verifiability("agrega tests")
        assert vtype == "unknown"


class TestUpdateVerifiability:
    def _new_session(self):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(dict(DEFAULT_SESSION), f)
        f.close()
        return Path(f.name)

    def test_update_verifiable(self):
        path = self._new_session()
        try:
            session = SessionState(path)
            session.update_verifiability("verifiable")
            assert session.read()["verifiability_type"] == "verifiable"
        finally:
            path.unlink(missing_ok=True)

    def test_update_non_verifiable(self):
        path = self._new_session()
        try:
            session = SessionState(path)
            session.update_verifiability("non_verifiable")
            assert session.read()["verifiability_type"] == "non_verifiable"
        finally:
            path.unlink(missing_ok=True)

    def test_update_unknown(self):
        path = self._new_session()
        try:
            session = SessionState(path)
            session.update_verifiability("unknown")
            assert session.read()["verifiability_type"] == "unknown"
        finally:
            path.unlink(missing_ok=True)

    def test_update_none_clears_field(self):
        path = self._new_session()
        try:
            session = SessionState(path)
            session.update_verifiability("verifiable")
            session.update_verifiability(None)
            assert session.read()["verifiability_type"] is None
        finally:
            path.unlink(missing_ok=True)

    def test_invalid_value_silently_ignored(self):
        path = self._new_session()
        try:
            session = SessionState(path)
            session.update_verifiability("verifiable")
            session.update_verifiability("garbage")  # not in allow-list
            # value stays at last valid
            assert session.read()["verifiability_type"] == "verifiable"
        finally:
            path.unlink(missing_ok=True)
