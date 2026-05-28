"""Tests for v1.9.6 context-aware complexity enhancer + real exec_model.

Covers two features:

1. classify-prompt's detect_implementation_complexity() — analyses a raw
   prompt for implementation/complexity signals and returns a minimum tier
   floor ("standard" / "deep") or None. The floor is enforced in the Build
   output so a verbose implementation request never routes below it.

2. subagent-stop's exec_model_real update — after a subagent finishes, the
   real model Claude Code used is read from the transcript and overwrites
   poly's predicted exec_model in session state.
"""

import json
import sys
import importlib.util
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.context import SessionState


def _load_hook_module(name: str, filename: str):
    """Load a hyphenated hook script as an importable module."""
    path = Path(__file__).parent.parent / "hooks" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


classify_prompt = _load_hook_module("classify_prompt", "classify-prompt.py")
subagent_stop = _load_hook_module("subagent_stop", "subagent-stop.py")

detect = classify_prompt.detect_implementation_complexity


# --- Feature 1: complexity enhancer ---------------------------------------

class TestDetectImplementationComplexity:

    def test_long_implementation_prompt_reaches_deep(self):
        # >100 words with >=2 implementation signals → deep floor.
        body = " ".join(["please"] * 100)
        query = (
            f"I need you to implement a complete authentication system for "
            f"our platform. {body} The api integration must be robust."
        )
        assert len(query.split()) > 100
        assert detect(query) == "deep"

    def test_short_simple_prompt_stays_haiku(self):
        # Trivial conversational prompt → no floor (None → stays fast/haiku).
        assert detect("hola, ¿cómo estás?") is None
        assert detect("what time is it?") is None
        assert detect("") is None

    def test_implementation_signals_floor_to_standard(self):
        # >=3 implementation signals + >30 words, but <=100 words → standard.
        query = (
            "Please implement a new module that exposes an api endpoint and "
            "wires it into the service layer so the frontend can read and "
            "write records through a clean interface that the team maintains "
            "going forward without breaking the existing contracts at all."
        )
        wc = len(query.split())
        assert 30 < wc <= 100
        assert detect(query) == "standard"

    def test_word_count_threshold(self):
        # Same dense signals but <=30 words must NOT floor (gate is word_count).
        short = "implement a module with an api endpoint and a service layer"
        assert len(short.split()) <= 30
        assert detect(short) is None

        # Padding the same request past 30 words flips it to the standard floor.
        padded = short + " " + " ".join(["carefully"] * 25)
        assert len(padded.split()) > 30
        assert detect(padded) == "standard"

    def test_two_impl_plus_complexity_signal_floors_standard(self):
        # 2 impl signals + 1 complexity signal + >30 words → standard.
        query = (
            "Please implement the complete module described in the ticket and "
            "make sure every single piece is covered end to end so nothing at "
            "all is left out when the reviewer finally looks at the change set."
        )
        assert len(query.split()) > 30
        assert detect(query) == "standard"


# --- Feature 1b: floor enforcement in the routing pipeline ----------------

class TestComplexityFloorEnforcement:

    def _run(self, prompt, tmp_path, monkeypatch, force_level=None):
        """Run classify-prompt.main() and return the routing context.

        force_level pins the scoring stage so the floor can be exercised
        independently of the keyword scorer (which shares signal words with
        the enhancer and would otherwise mask the floor's effect).
        """
        session_file = tmp_path / "session.json"
        monkeypatch.setattr(classify_prompt, "SESSION_PATH", session_file)
        if force_level is not None:
            monkeypatch.setattr(
                classify_prompt, "_stage_scoring",
                lambda *a, **k: (force_level, 0.9, "scoring", 0.5),
            )
        captured = {}
        monkeypatch.setattr("builtins.print", lambda s: captured.update(out=json.loads(s)))
        monkeypatch.setattr(sys, "stdin", mock.Mock(read=lambda: json.dumps({"prompt": prompt})))
        for var in ("CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_EFFORT"):
            monkeypatch.delenv(var, raising=False)
        classify_prompt.main()
        self._session_file = session_file
        return captured["out"].get("hookSpecificOutput", {}).get("additionalContext", "")

    def _routed_methods(self):
        """Return the method-name keys recorded for this run's session."""
        state = SessionState(self._session_file).read()
        return state.get("routing_method_counts", {})

    def test_floor_promotes_below_floor_routing(self, tmp_path, monkeypatch):
        # Scorer pinned to fast, but a long implementation prompt floors to deep.
        # Only Stage 8d can lift fast→deep (arch/multifile/verifiability all
        # require a standard starting tier), so this proves the floor fired.
        body = " ".join(["please"] * 100)
        prompt = (
            f"implement a complete authentication system for the platform. "
            f"{body} the api integration and database layer must be robust."
        )
        ctx = self._run(prompt, tmp_path, monkeypatch, force_level="fast")
        assert "Route: deep" in ctx
        assert "Model: opus" in ctx
        # method tag is surfaced via session routing counts, not the directive.
        assert any("complexity_floor" in m for m in self._routed_methods())

    def test_floor_does_not_downgrade_higher_routing(self, tmp_path, monkeypatch):
        # Scorer at deep, enhancer floor is standard → floor must NOT downgrade.
        prompt = (
            "create the complete component and the service module "
            + " ".join(["please"] * 26)
        )
        assert classify_prompt.detect_implementation_complexity(prompt) == "standard"
        ctx = self._run(prompt, tmp_path, monkeypatch, force_level="deep")
        assert "Route: deep" in ctx
        assert "complexity_floor" not in ctx

    def test_no_floor_for_simple_prompt(self, tmp_path, monkeypatch):
        # No signals → no floor; fast routing is preserved.
        ctx = self._run("hola", tmp_path, monkeypatch, force_level="fast")
        assert "Route: fast" in ctx
        assert "complexity_floor" not in ctx


# --- Feature 2: real exec_model from transcript ---------------------------

class TestUpdateExecModelReal:

    def test_unit_normalizes_family_and_stores_full_id(self, tmp_path):
        session = SessionState(tmp_path / "session.json")
        session.update_exec_model_real("claude-opus-4-8")
        state = session.read()
        assert state["exec_model"] == "opus"
        assert state["exec_model_full"] == "claude-opus-4-8"

    def test_unit_ignores_empty_model(self, tmp_path):
        session = SessionState(tmp_path / "session.json")
        session.update_exec_model_real("")
        assert session.read()["exec_model_full"] is None

    def test_exec_model_real_updated_on_subagent_stop(self, tmp_path, monkeypatch):
        # Build a transcript whose last assistant turn used opus.
        transcript = tmp_path / "transcript.jsonl"
        with transcript.open("w", encoding="utf-8") as f:
            for m in ("claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8"):
                f.write(json.dumps({
                    "type": "assistant",
                    "message": {"role": "assistant", "model": m},
                }) + "\n")

        session_file = tmp_path / "session.json"
        monkeypatch.setattr(subagent_stop, "SESSION_PATH", session_file)

        captured = {}
        monkeypatch.setattr("builtins.print", lambda s: captured.update(out=s))
        monkeypatch.setattr(
            sys, "stdin",
            mock.Mock(read=lambda: json.dumps({"transcript_path": str(transcript)})),
        )

        subagent_stop.main()

        state = SessionState(session_file).read()
        assert state["exec_model"] == "opus"
        assert state["exec_model_full"] == "claude-opus-4-8"
        assert captured["out"] == "{}"
