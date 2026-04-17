"""Tests for ctx_usage module — get_context_percent()."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.ctx_usage import get_context_percent, _CONTEXT_WINDOW


def _write_jsonl(path: Path, messages: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for msg in messages:
            fh.write(json.dumps(msg) + "\n")


class TestGetContextPercent:
    def test_none_path_returns_none(self):
        assert get_context_percent(None) is None

    def test_missing_file_returns_none(self):
        assert get_context_percent("/tmp/nonexistent_poly_test_12345.jsonl") is None

    def test_empty_file_returns_none(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        f.write_text("")
        assert get_context_percent(str(f)) is None

    def test_no_assistant_messages_returns_none(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        _write_jsonl(f, [
            {"message": {"role": "user", "content": "hello", "usage": {"input_tokens": 50}}},
        ])
        assert get_context_percent(str(f)) is None

    def test_basic_pct_calculation(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        # 20_000 tokens = 10% of 200k
        _write_jsonl(f, [
            {"message": {"role": "assistant", "usage": {"input_tokens": 20000, "output_tokens": 0}}},
        ])
        pct = get_context_percent(str(f))
        assert pct == 10

    def test_all_token_types_summed(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        # 10k + 5k + 5k + 2k = 22k  → 11%
        _write_jsonl(f, [
            {"message": {"role": "assistant", "usage": {
                "input_tokens": 10000,
                "output_tokens": 5000,
                "cache_read_input_tokens": 5000,
                "cache_creation_input_tokens": 2000,
            }}},
        ])
        pct = get_context_percent(str(f))
        assert pct == 11

    def test_returns_max_across_multiple_turns(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        _write_jsonl(f, [
            {"message": {"role": "assistant", "usage": {"input_tokens": 10000, "output_tokens": 0}}},
            {"message": {"role": "user", "content": "ok"}},
            {"message": {"role": "assistant", "usage": {"input_tokens": 50000, "output_tokens": 0}}},
        ])
        pct = get_context_percent(str(f))
        assert pct == 25  # 50000/200000 = 25%

    def test_caps_at_100(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        _write_jsonl(f, [
            {"message": {"role": "assistant", "usage": {"input_tokens": 300000, "output_tokens": 0}}},
        ])
        pct = get_context_percent(str(f))
        assert pct == 100

    def test_mtime_cache_used_on_second_call(self, tmp_path, monkeypatch):
        """Second call with same mtime should return cached value without re-parsing."""
        f = tmp_path / "transcript.jsonl"
        _write_jsonl(f, [
            {"message": {"role": "assistant", "usage": {"input_tokens": 40000, "output_tokens": 0}}},
        ])

        # Override cache file path to temp dir
        import lib.ctx_usage as cu
        cache_file = tmp_path / "ctx-cache.json"
        monkeypatch.setattr(cu, "_CACHE_FILE", cache_file)

        pct1 = get_context_percent(str(f))
        assert pct1 == 20

        # Corrupt the file AND force mtime to advance (filesystems can have 1s resolution)
        f.write_text("CORRUPT")
        import os
        st = f.stat()
        os.utime(str(f), (st.st_atime, st.st_mtime + 2))
        pct2 = get_context_percent(str(f))
        # mtime changed → re-parse → None (corrupt file)
        # This tests that mtime change invalidates cache
        assert pct2 is None

    def test_corrupt_jsonl_handled(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        f.write_text("NOT JSON\n{invalid}\n")
        # Should not raise, returns None
        result = get_context_percent(str(f))
        assert result is None

    def test_missing_usage_field_skipped(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        _write_jsonl(f, [
            {"message": {"role": "assistant", "content": "hello"}},  # no usage
            {"message": {"role": "assistant", "usage": {"input_tokens": 10000, "output_tokens": 0}}},
        ])
        pct = get_context_percent(str(f))
        assert pct == 5  # 10000/200000
