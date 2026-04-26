"""Unit tests for hooks/lib/export.py — CALIDAD #13.

Covers:
  - CSV header + per-dimension blocks (summary, routes, languages, session)
  - CSV escaping (commas, quotes inside language codes)
  - CSV with sparse input (missing optional fields)
  - JSON record-array shape (pandas/jq compatibility)
  - JSON unicode safety (ensure_ascii=False)
  - JSON heterogeneous-session guard (DataFrame requires homogeneous keys)
"""

import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib import export  # noqa: E402


SAMPLE = {
    "version": "1.0",
    "total_queries": 1702,
    "routes": {"fast": 935, "standard": 257, "deep": 510},
    "cache_hits": 699,
    "languages_detected": {"en": 269, "es": 1192, "multi": 50},
    "estimated_savings": 50.2533,
    "sessions": [
        {
            "date": "2026-04-02",
            "queries": 24,
            "routes": {"fast": 16, "standard": 0, "deep": 8},
            "cache_hits": 18,
            "savings": 0.704,
        },
        {
            "date": "2026-04-26",
            "queries": 151,
            "routes": {"fast": 111, "standard": 4, "deep": 36},
            "cache_hits": 119,
            "savings": 5.8821,
        },
    ],
    "last_updated": "2026-04-26T07:42:39.932770",
}


def _csv_rows(payload: dict) -> list[list[str]]:
    return list(csv.reader(io.StringIO(export.to_csv(payload))))


# ----------------------------- CSV -----------------------------


class TestCsvHeader:
    def test_header_is_three_columns(self):
        rows = _csv_rows(SAMPLE)
        assert rows[0] == ["dimension", "key", "value"]


class TestCsvSummaryBlock:
    def test_summary_scalars_present(self):
        summary = {r[1]: r[2] for r in _csv_rows(SAMPLE) if r[0] == "summary"}
        assert summary["total_queries"] == "1702"
        assert summary["cache_hits"] == "699"
        assert summary["estimated_savings"] == "50.2533"
        assert summary["version"] == "1.0"
        assert summary["last_updated"].startswith("2026-04-26")

    def test_summary_order_is_deterministic(self):
        rows = _csv_rows(SAMPLE)
        keys = [r[1] for r in rows if r[0] == "summary"]
        assert keys == [
            "version",
            "total_queries",
            "cache_hits",
            "estimated_savings",
            "last_updated",
        ]


class TestCsvRoutesBlock:
    def test_each_tier_emitted(self):
        routes = {r[1]: int(r[2]) for r in _csv_rows(SAMPLE) if r[0] == "routes"}
        assert routes == {"fast": 935, "standard": 257, "deep": 510}


class TestCsvLanguagesBlock:
    def test_each_language_emitted(self):
        langs = {r[1]: int(r[2]) for r in _csv_rows(SAMPLE) if r[0] == "languages"}
        assert langs == {"en": 269, "es": 1192, "multi": 50}


class TestCsvSessionBlock:
    def test_session_fields_use_date_prefix(self):
        sess = {r[1]: r[2] for r in _csv_rows(SAMPLE) if r[0] == "session"}
        assert sess["2026-04-02.queries"] == "24"
        assert sess["2026-04-02.cache_hits"] == "18"
        assert sess["2026-04-02.savings"] == "0.704"

    def test_session_routes_nested_keys(self):
        sess = {r[1]: r[2] for r in _csv_rows(SAMPLE) if r[0] == "session"}
        assert sess["2026-04-02.routes.fast"] == "16"
        assert sess["2026-04-02.routes.deep"] == "8"
        assert sess["2026-04-26.routes.deep"] == "36"


class TestCsvSparseInput:
    def test_missing_routes_dict_yields_no_routes_rows(self):
        rows = _csv_rows({"version": "1.0", "total_queries": 0})
        assert rows[0] == ["dimension", "key", "value"]
        assert all(r[0] == "summary" for r in rows[1:])

    def test_missing_session_routes_does_not_crash(self):
        payload = {"sessions": [{"date": "2026-01-01", "queries": 1}]}
        rows = _csv_rows(payload)
        sess = {r[1] for r in rows if r[0] == "session"}
        assert "2026-01-01.queries" in sess

    def test_session_without_date_uses_unknown_marker(self):
        payload = {"sessions": [{"queries": 5}]}
        rows = _csv_rows(payload)
        sess = {r[1]: r[2] for r in rows if r[0] == "session"}
        assert sess.get("unknown.queries") == "5"


class TestCsvEscaping:
    def test_comma_in_language_code(self):
        weird = {"version": "1.0", "languages_detected": {"a,b": 1}}
        out = export.to_csv(weird)
        assert '"a,b"' in out
        rows = list(csv.reader(io.StringIO(out)))
        langs = {r[1]: int(r[2]) for r in rows if r[0] == "languages"}
        assert langs == {"a,b": 1}

    def test_quote_in_language_code(self):
        weird = {"version": "1.0", "languages_detected": {'q"x': 2}}
        rows = list(csv.reader(io.StringIO(export.to_csv(weird))))
        langs = {r[1]: int(r[2]) for r in rows if r[0] == "languages"}
        assert langs == {'q"x': 2}


# ----------------------------- JSON -----------------------------


class TestJsonSummary:
    def test_summary_keys_present(self):
        out = json.loads(export.to_json(SAMPLE))
        assert out["summary"]["version"] == "1.0"
        assert out["summary"]["total_queries"] == 1702
        assert out["summary"]["cache_hits"] == 699
        assert out["summary"]["estimated_savings"] == 50.2533


class TestJsonRoutes:
    def test_routes_are_record_array(self):
        out = json.loads(export.to_json(SAMPLE))
        assert isinstance(out["routes"], list)
        assert {"tier": "fast", "count": 935} in out["routes"]
        assert {"tier": "deep", "count": 510} in out["routes"]


class TestJsonLanguages:
    def test_languages_are_record_array(self):
        out = json.loads(export.to_json(SAMPLE))
        assert isinstance(out["languages"], list)
        by_lang = {r["language"]: r["count"] for r in out["languages"]}
        assert by_lang == {"en": 269, "es": 1192, "multi": 50}


class TestJsonSessions:
    def test_sessions_flatten_nested_routes(self):
        out = json.loads(export.to_json(SAMPLE))
        s0 = out["sessions"][0]
        assert s0["date"] == "2026-04-02"
        assert s0["queries"] == 24
        assert s0["routes_fast"] == 16
        assert s0["routes_deep"] == 8

    def test_sessions_nested_routes_dict_removed(self):
        out = json.loads(export.to_json(SAMPLE))
        for s in out["sessions"]:
            assert "routes" not in s, "nested dict should be flattened to routes_<tier>"

    def test_sessions_have_homogeneous_keys(self):
        """DataFrame compatibility: every record must share the same key set."""
        out = json.loads(export.to_json(SAMPLE))
        keysets = {tuple(sorted(s.keys())) for s in out["sessions"]}
        assert len(keysets) == 1, f"Heterogeneous session shapes: {keysets}"


class TestJsonSparseInput:
    def test_missing_optional_collections_yield_empty_arrays(self):
        out = json.loads(export.to_json({"version": "1.0"}))
        assert out["routes"] == []
        assert out["languages"] == []
        assert out["sessions"] == []
        assert out["summary"]["version"] == "1.0"

    def test_full_empty_dict_is_safe(self):
        out = json.loads(export.to_json({}))
        assert out == {"summary": {}, "routes": [], "languages": [], "sessions": []}


class TestJsonUnicode:
    def test_non_ascii_language_codes_round_trip(self):
        weird = {"languages_detected": {"中文": 5, "日本語": 3}}
        raw = export.to_json(weird)
        # ensure_ascii=False keeps glyphs literal (no \u escapes)
        assert "中文" in raw
        assert "日本語" in raw
        parsed = json.loads(raw)
        by_lang = {r["language"]: r["count"] for r in parsed["languages"]}
        assert by_lang == {"中文": 5, "日本語": 3}
