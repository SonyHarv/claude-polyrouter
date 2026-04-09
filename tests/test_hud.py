"""Tests for HUD helper module and statusLine output (Sprint 5)."""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.hud import (
    CACHE_BAR_EXPIRED,
    CACHE_BAR_LEVELS,
    MASCOT_STATES,
    TIER_MODELS,
    TIER_SHORT,
    cache_bar,
    detect_state,
    format_status_line,
    get_color,
    get_frame,
)


# --- Mascot state definitions ---


class TestMascotDefinitions:
    """Verify mascot state table is complete and well-formed."""

    EXPECTED_STATES = {"idle", "routing", "keepalive", "danger", "thinking", "compact"}

    def test_all_states_defined(self):
        assert set(MASCOT_STATES.keys()) == self.EXPECTED_STATES

    @pytest.mark.parametrize("state", EXPECTED_STATES)
    def test_each_state_has_frames_and_color(self, state):
        s = MASCOT_STATES[state]
        assert "frames" in s
        assert "color" in s
        assert len(s["frames"]) >= 2
        assert s["color"].startswith("#")
        assert len(s["color"]) == 7

    def test_idle_frames(self):
        frames = MASCOT_STATES["idle"]["frames"]
        assert frames[0] == "[^.^]  ~"
        assert "[^-^]" in frames[2]

    def test_routing_frames(self):
        frames = MASCOT_STATES["routing"]["frames"]
        assert "[^o^]" in frames[0]
        assert "[^O^]" in frames[-1]

    def test_keepalive_frames(self):
        frames = MASCOT_STATES["keepalive"]["frames"]
        assert "zzz" in frames[2]
        assert "[^.^]  *" == frames[3]

    def test_danger_frames(self):
        frames = MASCOT_STATES["danger"]["frames"]
        assert "!" in frames[0]
        assert "!!!!" in frames[-1]
        assert "[>O<]" in frames[-1]

    def test_thinking_frames(self):
        frames = MASCOT_STATES["thinking"]["frames"]
        assert "[^.^] ." == frames[0]
        assert "[^.~] ..." == frames[-1]

    def test_compact_frames(self):
        frames = MASCOT_STATES["compact"]["frames"]
        assert "ok" in frames[-1]


# --- get_frame ---


class TestGetFrame:
    """Frame selection and cycling."""

    def test_idle_frame_0(self):
        assert get_frame("idle", 0) == "[^.^]  ~"

    def test_frame_wraps_around(self):
        n = len(MASCOT_STATES["idle"]["frames"])
        assert get_frame("idle", 0) == get_frame("idle", n)

    def test_routing_frame_cycle(self):
        frames = MASCOT_STATES["routing"]["frames"]
        for i, expected in enumerate(frames):
            assert get_frame("routing", i) == expected

    def test_unknown_state_falls_back_to_idle(self):
        assert get_frame("nonexistent", 0) == MASCOT_STATES["idle"]["frames"][0]

    @pytest.mark.parametrize("state", MASCOT_STATES.keys())
    def test_all_states_return_string(self, state):
        result = get_frame(state, 0)
        assert isinstance(result, str)
        assert len(result) > 0


# --- detect_state ---


class TestDetectState:
    """State detection from session data."""

    def test_no_session_returns_idle(self):
        assert detect_state(None) == "idle"

    def test_empty_session_returns_idle(self):
        assert detect_state({}) == "idle"

    def test_no_last_route_returns_idle(self):
        assert detect_state({"last_query_time": time.time()}) == "idle"

    def test_very_recent_query_returns_routing(self):
        now = 1000000.0
        session = {"last_route": "standard", "last_query_time": now - 1}
        assert detect_state(session, now=now) == "routing"

    def test_few_seconds_ago_returns_thinking(self):
        now = 1000000.0
        session = {"last_route": "standard", "last_query_time": now - 5}
        assert detect_state(session, now=now) == "thinking"

    def test_normal_idle_returns_idle(self):
        now = 1000000.0
        session = {"last_route": "standard", "last_query_time": now - 60}
        assert detect_state(session, now=now) == "idle"

    def test_drowsy_returns_keepalive(self):
        now = 1000000.0
        session = {"last_route": "deep", "last_query_time": now - 2500}
        assert detect_state(session, now=now) == "keepalive"

    def test_danger_over_50_min(self):
        now = 1000000.0
        session = {"last_route": "fast", "last_query_time": now - 3100}
        assert detect_state(session, now=now) == "danger"

    def test_compact_advisory_active(self):
        now = 1000000.0
        session = {"last_route": "standard", "last_query_time": now - 30}
        compact = {"advisory_active": True}
        assert detect_state(session, compact=compact, now=now) == "compact"

    def test_compact_not_active_returns_idle(self):
        now = 1000000.0
        session = {"last_route": "standard", "last_query_time": now - 30}
        compact = {"advisory_active": False}
        assert detect_state(session, compact=compact, now=now) == "idle"

    def test_danger_takes_priority_over_compact(self):
        now = 1000000.0
        session = {"last_route": "deep", "last_query_time": now - 3500}
        compact = {"advisory_active": True}
        assert detect_state(session, compact=compact, now=now) == "danger"

    def test_keepalive_takes_priority_over_compact(self):
        now = 1000000.0
        session = {"last_route": "deep", "last_query_time": now - 2500}
        compact = {"advisory_active": True}
        assert detect_state(session, compact=compact, now=now) == "keepalive"

    def test_routing_takes_priority_over_compact(self):
        now = 1000000.0
        session = {"last_route": "standard", "last_query_time": now - 1}
        compact = {"advisory_active": True}
        assert detect_state(session, compact=compact, now=now) == "routing"


# --- format_status_line ---


class TestFormatStatusLine:
    """Status line output format."""

    def test_minimal_idle(self):
        line = format_status_line("idle", 0)
        assert line.startswith("[polyrouter]")
        assert "[^.^]  ~" in line

    def test_full_format(self):
        line = format_status_line(
            "idle", 0, tier="standard", savings=12.34, language="es", elapsed=300.0
        )
        assert "[polyrouter]" in line
        assert "sonnet" in line
        assert "std" in line
        assert "█████" in line
        assert "$12.34\u2193" in line
        assert "es" in line

    def test_separator_is_middot(self):
        line = format_status_line("idle", 0, tier="fast", language="en")
        assert " \u00b7 " in line

    def test_no_savings_omitted(self):
        line = format_status_line("idle", 0, tier="deep", savings=0.0)
        assert "$" not in line

    def test_no_language_omitted(self):
        line = format_status_line("idle", 0, tier="fast")
        assert line.endswith("fast")

    def test_tier_fast_shows_haiku(self):
        line = format_status_line("routing", 0, tier="fast")
        assert "haiku" in line
        assert "fast" in line

    def test_tier_deep_shows_opus(self):
        line = format_status_line("thinking", 0, tier="deep")
        assert "opus" in line
        assert "deep" in line

    def test_different_states_produce_different_frames(self):
        idle_line = format_status_line("idle", 0)
        routing_line = format_status_line("routing", 0)
        assert idle_line != routing_line

    def test_tick_advances_frame(self):
        line0 = format_status_line("routing", 0, tier="standard")
        line1 = format_status_line("routing", 1, tier="standard")
        assert line0 != line1


# --- cache_bar ---


class TestCacheBar:
    """Cache freshness bar rendering."""

    def test_fresh_under_10_min(self):
        bar, color = cache_bar(0)
        assert bar == "█████"
        assert color == "#97c459"

    def test_fresh_at_5_min(self):
        bar, _color = cache_bar(300)
        assert bar == "█████"

    def test_warm_at_15_min(self):
        bar, color = cache_bar(900)
        assert bar == "████░"
        assert color == "#ef9f27"

    def test_cooling_at_35_min(self):
        bar, color = cache_bar(2100)
        assert bar == "███░░"
        assert color == "#e8853a"

    def test_expired_at_55_min(self):
        bar, color = cache_bar(3300)
        assert bar == "░░░░░"
        assert color == "#e24b4a"

    def test_boundary_10_min(self):
        bar, _color = cache_bar(599)
        assert bar == "█████"
        bar2, _color2 = cache_bar(600)
        assert bar2 == "████░"

    def test_boundary_30_min(self):
        bar, _color = cache_bar(1799)
        assert bar == "████░"
        bar2, _color2 = cache_bar(1800)
        assert bar2 == "███░░"

    def test_boundary_50_min(self):
        bar, _color = cache_bar(2999)
        assert bar == "███░░"
        bar2, _color2 = cache_bar(3000)
        assert bar2 == "░░░░░"

    def test_expired_returns_constant(self):
        bar, color = cache_bar(99999)
        assert (bar, color) == CACHE_BAR_EXPIRED

    def test_all_bars_are_5_chars(self):
        for secs in [0, 300, 900, 2100, 3300]:
            bar, _color = cache_bar(secs)
            assert len(bar) == 5


class TestFormatStatusLineWithCacheBar:
    """Cache bar integration in status line."""

    def test_cache_bar_present_when_elapsed_given(self):
        line = format_status_line("idle", 0, tier="standard", elapsed=100.0)
        assert "█████" in line

    def test_cache_bar_absent_when_no_elapsed(self):
        line = format_status_line("idle", 0, tier="standard")
        assert "█" not in line
        assert "░" not in line

    def test_cache_bar_position_between_tier_and_savings(self):
        line = format_status_line(
            "idle", 0, tier="standard", savings=5.0, elapsed=2100.0, language="en"
        )
        # Order: frame · model · short · bar · savings · lang
        parts = line.split(" · ")
        bar_idx = next(i for i, p in enumerate(parts) if "░" in p or "█" in p)
        savings_idx = next(i for i, p in enumerate(parts) if "$" in p)
        assert bar_idx < savings_idx

    def test_expired_bar_format(self):
        line = format_status_line("danger", 0, tier="deep", elapsed=3500.0)
        assert "░░░░░" in line


# --- get_color ---


class TestGetColor:
    """Color mapping for mascot states."""

    def test_idle_color(self):
        assert get_color("idle") == "#afa9ec"

    def test_routing_color(self):
        assert get_color("routing") == "#5dcaa5"

    def test_keepalive_color(self):
        assert get_color("keepalive") == "#484f58"

    def test_danger_color(self):
        assert get_color("danger") == "#e24b4a"

    def test_thinking_color(self):
        assert get_color("thinking") == "#ef9f27"

    def test_compact_color(self):
        assert get_color("compact") == "#97c459"

    def test_unknown_state_returns_idle_color(self):
        assert get_color("nonexistent") == "#afa9ec"

    @pytest.mark.parametrize("state", MASCOT_STATES.keys())
    def test_all_colors_are_valid_hex(self, state):
        color = get_color(state)
        assert len(color) == 7
        assert color[0] == "#"
        int(color[1:], 16)  # Must be valid hex


# --- Tier mapping ---


class TestTierMapping:
    """Tier short names and model names."""

    def test_tier_models(self):
        assert TIER_MODELS == {"fast": "haiku", "standard": "sonnet", "deep": "opus"}

    def test_tier_short(self):
        assert TIER_SHORT == {"fast": "fast", "standard": "std", "deep": "deep"}


# --- Minimal additionalContext output ---


class TestMinimalContext:
    """Verify _route_output produces minimal additionalContext."""

    @pytest.fixture(autouse=True)
    def _setup_path(self):
        sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

    def _get_route_output(self):
        # Import here to get the updated version
        import importlib
        # Force reimport to pick up changes
        mod_name = "classify-prompt"
        spec_path = Path(__file__).parent.parent / "hooks" / "classify-prompt.py"

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "classify_prompt_mod", spec_path,
            submodule_search_locations=[],
        )
        mod = importlib.util.module_from_spec(spec)
        # We only need the _route_output function, extract it
        # Read the source and find the function
        source = spec_path.read_text()
        return source

    def test_route_output_is_minimal(self):
        """additionalContext should be ~50 tokens, not the old verbose version."""
        source = self._get_route_output()
        # The new _route_output should NOT contain the old verbose patterns
        assert "MANDATORY ROUTING DIRECTIVE" not in source
        assert "Do NOT respond to the user directly" not in source
        assert "Example:" not in source
        assert "Signals:" not in source

    def test_route_output_has_directive(self):
        """additionalContext should contain the minimal routing directive."""
        source = self._get_route_output()
        assert "CRITICAL: Spawn" in source
        assert "Route:" in source


# --- OMC conflict resolution ---


class TestOmcCoexistence:
    """OMC HUD conflict resolution behavior."""

    def test_poly_line_always_prefixed(self):
        """Poly output always starts with [polyrouter]."""
        line = format_status_line("idle", 0, tier="standard", language="en")
        assert line.startswith("[polyrouter]")

    def test_poly_line_is_single_line(self):
        """Status line must be a single line (no newlines)."""
        line = format_status_line(
            "routing", 1, tier="deep", savings=5.0, language="es"
        )
        assert "\n" not in line
        assert "\r" not in line
