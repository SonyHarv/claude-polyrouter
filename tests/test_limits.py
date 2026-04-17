"""Tests for limits module — get_limits() with ccusage integration."""

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import lib.limits as limits_mod
from lib.limits import get_limits, _parse_ccusage_output, _TTL_SECONDS


SAMPLE_CCUSAGE_JSON = {
    "five_hour": {"used_pct": 45, "reset_in_seconds": 3720},
    "weekly": {"used_pct": 9, "reset_in_seconds": 596340},
    "sonnet_weekly": {"used_pct": 3, "reset_in_seconds": 596340},
}


class TestParseCcusageOutput:
    def test_parses_standard_schema(self):
        result = _parse_ccusage_output(SAMPLE_CCUSAGE_JSON)
        assert result["five_hour_pct"] == 45
        assert result["five_hour_remaining_sec"] == 3720
        assert result["weekly_pct"] == 9
        assert result["weekly_remaining_sec"] == 596340
        assert result["sonnet_weekly_pct"] == 3
        assert result["sonnet_weekly_remaining_sec"] == 596340
        assert "updated_at" in result

    def test_handles_empty_dict(self):
        result = _parse_ccusage_output({})
        assert result["five_hour_pct"] is None
        assert result["weekly_pct"] is None
        assert result["sonnet_weekly_pct"] is None

    def test_handles_camelCase_keys(self):
        data = {
            "fiveHour": {"used_pct": 20, "reset_in_seconds": 100},
            "week": {"used_pct": 5, "reset_in_seconds": 200},
            "sonnetWeekly": {"used_pct": 1, "reset_in_seconds": 300},
        }
        result = _parse_ccusage_output(data)
        assert result["five_hour_pct"] == 20
        assert result["weekly_pct"] == 5
        assert result["sonnet_weekly_pct"] == 1

    def test_handles_alternate_field_names(self):
        data = {
            "five_hour": {"percent": 30, "remaining_seconds": 500},
        }
        result = _parse_ccusage_output(data)
        assert result["five_hour_pct"] == 30
        assert result["five_hour_remaining_sec"] == 500

    def test_none_block_produces_none(self):
        result = _parse_ccusage_output({"five_hour": None})
        assert result["five_hour_pct"] is None


class TestGetLimits:
    def _fresh_cache(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "limits-cache.json"
        monkeypatch.setattr(limits_mod, "_CACHE_FILE", cache_file)
        return cache_file

    def test_returns_none_when_ccusage_not_installed(self, tmp_path, monkeypatch):
        self._fresh_cache(tmp_path, monkeypatch)
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = get_limits()
        assert result is None

    def test_returns_none_on_subprocess_error(self, tmp_path, monkeypatch):
        self._fresh_cache(tmp_path, monkeypatch)
        mock = MagicMock()
        mock.returncode = 1
        mock.stdout = ""
        with patch("subprocess.run", return_value=mock):
            result = get_limits()
        assert result is None

    def test_returns_parsed_data_on_success(self, tmp_path, monkeypatch):
        self._fresh_cache(tmp_path, monkeypatch)
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = json.dumps(SAMPLE_CCUSAGE_JSON)
        with patch("subprocess.run", return_value=mock):
            result = get_limits()
        assert result is not None
        assert result["five_hour_pct"] == 45
        assert result["weekly_pct"] == 9

    def test_cache_hit_within_ttl(self, tmp_path, monkeypatch):
        cache_file = self._fresh_cache(tmp_path, monkeypatch)
        parsed = _parse_ccusage_output(SAMPLE_CCUSAGE_JSON)
        # Write a fresh cache entry
        cache_data = {"data": parsed, "updated_at": time.time()}
        cache_file.write_text(json.dumps(cache_data))

        call_count = 0
        def counting_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            m.returncode = 0
            m.stdout = json.dumps(SAMPLE_CCUSAGE_JSON)
            return m

        with patch("subprocess.run", side_effect=counting_run):
            result = get_limits()

        assert call_count == 0  # cache hit, no subprocess call
        assert result["five_hour_pct"] == 45

    def test_cache_miss_after_ttl(self, tmp_path, monkeypatch):
        cache_file = self._fresh_cache(tmp_path, monkeypatch)
        parsed = _parse_ccusage_output(SAMPLE_CCUSAGE_JSON)
        # Write an expired cache entry
        old_time = time.time() - _TTL_SECONDS - 10
        cache_data = {"data": parsed, "updated_at": old_time}
        cache_file.write_text(json.dumps(cache_data))

        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = json.dumps(SAMPLE_CCUSAGE_JSON)
        with patch("subprocess.run", return_value=mock) as mock_run:
            result = get_limits()

        assert mock_run.called  # cache expired, subprocess called
        assert result is not None

    def test_handles_exception_gracefully(self, tmp_path, monkeypatch):
        self._fresh_cache(tmp_path, monkeypatch)
        with patch("subprocess.run", side_effect=RuntimeError("unexpected")):
            result = get_limits()
        assert result is None
