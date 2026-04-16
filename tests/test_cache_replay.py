"""E2E test: cache hit must replay effort_level and requires_advisor correctly.

Regression test for the v1.5 bug where Stage 3 cache hits early-returned
before Stage 6b/6c, leaving effort_level at base and requires_advisor=False.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HOOK_SCRIPT = Path(__file__).parent.parent / "hooks" / "classify-prompt.py"

# Architectural prompt that triggers deep tier + arch promotion → xhigh + advisor
ARCH_PROMPT = (
    "Design the architecture for a distributed event-driven microservices system "
    "with CQRS, saga orchestration, and multi-region failover. Include data "
    "consistency strategies, service boundaries, and deployment topology."
)


def run_hook(query: str, home_dir: str) -> dict:
    """Run the hook script with an isolated HOME so session/cache are scoped."""
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(Path(__file__).parent.parent)
    env["HOME"] = home_dir
    # Ensure no env effort override interferes
    env.pop("CLAUDE_CODE_EFFORT_LEVEL", None)

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
        pytest.fail(f"Hook failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")
    return json.loads(result.stdout)


def read_session(home_dir: str) -> dict:
    session_path = Path(home_dir) / ".claude" / "polyrouter-session.json"
    if not session_path.exists():
        return {}
    return json.loads(session_path.read_text(encoding="utf-8"))


def wipe_session(home_dir: str) -> None:
    """Delete session file to reset state (keep cache intact)."""
    session_path = Path(home_dir) / ".claude" / "polyrouter-session.json"
    if session_path.exists():
        session_path.unlink()


class TestCacheReplay:
    def test_xhigh_and_advisor_survive_cache_hit(self):
        """Cache hit must replay effort=xhigh and requires_advisor=True."""
        with tempfile.TemporaryDirectory() as tmp:
            # --- Run 1: cold cache, full pipeline ---
            run_hook(ARCH_PROMPT, tmp)
            state1 = read_session(tmp)

            assert state1.get("effort_level") == "xhigh", (
                f"Run 1: expected effort_level='xhigh', got {state1.get('effort_level')!r}\n"
                f"Full state: {state1}"
            )
            assert state1.get("requires_advisor") is True, (
                f"Run 1: expected requires_advisor=True, got {state1.get('requires_advisor')!r}\n"
                f"Full state: {state1}"
            )

            # --- Reset session state (but keep cache file) ---
            wipe_session(tmp)

            # --- Run 2: should hit Stage 3 cache ---
            run_hook(ARCH_PROMPT, tmp)
            state2 = read_session(tmp)

            assert state2.get("effort_level") == "xhigh", (
                f"Run 2 (cache hit): expected effort_level='xhigh', got {state2.get('effort_level')!r}\n"
                f"Full state: {state2}"
            )
            assert state2.get("requires_advisor") is True, (
                f"Run 2 (cache hit): expected requires_advisor=True, got {state2.get('requires_advisor')!r}\n"
                f"Full state: {state2}"
            )

    def test_fast_route_cache_hit_has_no_advisor(self):
        """Simple fast-tier query: cache hit must NOT set advisor."""
        with tempfile.TemporaryDirectory() as tmp:
            simple = "what is a variable in python"
            run_hook(simple, tmp)
            wipe_session(tmp)
            run_hook(simple, tmp)
            state = read_session(tmp)
            assert state.get("requires_advisor") is False, (
                f"Fast route cache hit should not set advisor. State: {state}"
            )

    def test_old_cache_entry_missing_effort_uses_default(self, tmp_path):
        """Pre-v1.5 cache entries without 'effort'/'advisor' fields must not crash."""
        home_dir = str(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)

        # Write a minimal legacy cache entry (no effort/advisor fields)
        from lib.cache import fingerprint  # noqa: PLC0415
        import sys as _sys
        hooks_dir = str(Path(__file__).parent.parent / "hooks")
        if hooks_dir not in _sys.path:
            _sys.path.insert(0, hooks_dir)
        from lib.cache import Cache, fingerprint as fp  # noqa: PLC0415

        cache = Cache(
            memory_size=50,
            file_size=100,
            ttl_days=30,
            cache_file=claude_dir / "polyrouter-cache.json",
        )
        key = fp(ARCH_PROMPT)
        # Legacy payload — no effort, no advisor
        cache.set(key, {
            "level": "deep",
            "confidence": 0.9,
            "method": "rules",
            "signals": "deep=2",
            "language": "en",
        })
        cache.flush()

        # Should not crash; effort defaults to compute_effort("deep") = "medium"
        output = run_hook(ARCH_PROMPT, home_dir)
        assert "hookSpecificOutput" in output
        state = read_session(home_dir)
        # effort_level should be some valid value (not crash / not missing)
        assert state.get("effort_level") in ("low", "medium", "high", "xhigh"), (
            f"Unexpected effort_level after legacy cache hit: {state}"
        )
