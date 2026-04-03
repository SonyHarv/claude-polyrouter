"""End-to-end integration tests for the pipeline orchestrator."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_SCRIPT = Path(__file__).parent.parent / "hooks" / "classify-prompt.py"


def run_hook(query: str) -> dict:
    """Run the hook script as a subprocess and return parsed output."""
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(Path(__file__).parent.parent)
    input_data = json.dumps({"hookEventName": "UserPromptSubmit", "query": query})
    result = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=input_data,
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    if result.returncode != 0:
        pytest.fail(f"Hook failed: {result.stderr}")
    return json.loads(result.stdout)


class TestPipelineEndToEnd:
    def test_english_simple_query_routes_fast(self):
        output = run_hook("what is a variable in python")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "MANDATORY ROUTING DIRECTIVE" in ctx
        assert "Route: fast" in ctx

    def test_spanish_architecture_routes_deep(self):
        output = run_hook(
            "diseña la arquitectura de un sistema distribuido escalable"
        )
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "MANDATORY ROUTING DIRECTIVE" in ctx
        assert "Route: deep" in ctx

    def test_slash_command_skips_routing(self):
        output = run_hook("/polyrouter:stats")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "ROUTING SKIPPED" in ctx

    def test_empty_query_skips_routing(self):
        output = run_hook("   ")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "ROUTING SKIPPED" in ctx

    def test_router_meta_query_skips(self):
        output = run_hook("how does the polyrouter work?")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "ROUTING SKIPPED" in ctx

    def test_output_has_correct_structure(self):
        output = run_hook("explain closures in javascript")
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"

    def test_git_command_routes_fast(self):
        output = run_hook("git status")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "Route: fast" in ctx

    def test_security_audit_routes_deep(self):
        output = run_hook("audit the security vulnerabilities across all files")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "Route: deep" in ctx

    def test_spanish_simple_routes_fast(self):
        output = run_hook("qué es una variable en python")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "Route: fast" in ctx

    def test_invalid_json_input_skips(self):
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(Path(__file__).parent.parent)
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input="NOT JSON",
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        output = json.loads(result.stdout)
        assert "ROUTING SKIPPED" in output["hookSpecificOutput"]["additionalContext"]
