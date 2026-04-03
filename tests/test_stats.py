import json
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.stats import Stats


class TestStats:
    def _make_stats(self, tmpdir):
        path = Path(tmpdir) / "stats.json"
        return Stats(path)

    def test_empty_stats_on_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            data = stats.read()
            assert data["total_queries"] == 0
            assert data["routes"]["fast"] == 0

    def test_record_increments_counters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            stats.record(level="fast", language="en", cache_hit=False, savings=0.044)
            data = stats.read()
            assert data["total_queries"] == 1
            assert data["routes"]["fast"] == 1
            assert data["languages_detected"]["en"] == 1
            assert data["cache_hits"] == 0

    def test_cache_hit_increments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            stats.record(level="fast", language="en", cache_hit=True, savings=0.044)
            data = stats.read()
            assert data["cache_hits"] == 1

    def test_multiple_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            stats.record(level="fast", language="en", cache_hit=False, savings=0.044)
            stats.record(level="deep", language="es", cache_hit=False, savings=0.0)
            stats.record(level="fast", language="en", cache_hit=True, savings=0.044)
            data = stats.read()
            assert data["total_queries"] == 3
            assert data["routes"]["fast"] == 2
            assert data["routes"]["deep"] == 1
            assert data["languages_detected"]["en"] == 2
            assert data["languages_detected"]["es"] == 1
            assert data["cache_hits"] == 1

    def test_session_created_for_today(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            stats.record(level="fast", language="en", cache_hit=False, savings=0.044)
            data = stats.read()
            today = date.today().isoformat()
            session = next(s for s in data["sessions"] if s["date"] == today)
            assert session["queries"] == 1

    def test_sessions_pruned_to_30_days(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            data = stats.read()
            for i in range(35):
                data["sessions"].append({"date": f"2025-01-{i+1:02d}", "queries": 1, "routes": {"fast": 1}, "cache_hits": 0, "savings": 0.0})
            stats._write(data)
            stats.record(level="fast", language="en", cache_hit=False, savings=0.044)
            data = stats.read()
            assert len(data["sessions"]) <= 30

    def test_corrupted_file_resets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stats.json"
            path.write_text("CORRUPT DATA")
            stats = Stats(path)
            data = stats.read()
            assert data["total_queries"] == 0

    def test_invalid_level_still_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = self._make_stats(tmpdir)
            stats.record(level="ultra", language="en", cache_hit=False, savings=0.0)
            data = stats.read()
            assert data["routes"]["ultra"] == 1
