import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.learner import get_learned_adjustment


class TestLearner:
    def _write_patterns(self, tmpdir, content):
        learnings_dir = Path(tmpdir) / ".claude-polyrouter" / "learnings"
        learnings_dir.mkdir(parents=True)
        (learnings_dir / "patterns.md").write_text(content)
        (learnings_dir / "quirks.md").write_text("")
        return learnings_dir

    def test_no_adjustment_when_disabled(self):
        config = {"learning": {"informed_routing": False, "max_boost": 0.1}}
        result = get_learned_adjustment("some query about databases", "fast", 0.7, config, None)
        assert result == (0.0, None)

    def test_no_adjustment_when_no_learnings_dir(self):
        config = {"learning": {"informed_routing": True, "max_boost": 0.1}}
        result = get_learned_adjustment("query", "fast", 0.7, config, Path("/nonexistent"))
        assert result == (0.0, None)

    def test_boost_when_keywords_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learnings_dir = self._write_patterns(tmpdir, """
## Pattern: Database queries need deep analysis
- **Keywords:** sql, database, query, migration
- **Confidence:** high
""")
            config = {"learning": {"informed_routing": True, "max_boost": 0.1}}
            boost, reason = get_learned_adjustment(
                "optimize the database query for migration", "fast", 0.7, config, learnings_dir,
            )
            assert boost > 0
            assert boost <= 0.1
            assert reason is not None

    def test_no_boost_with_single_keyword_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learnings_dir = self._write_patterns(tmpdir, """
## Pattern: Database queries need deep analysis
- **Keywords:** sql, database, query, migration
- **Confidence:** high
""")
            config = {"learning": {"informed_routing": True, "max_boost": 0.1}}
            boost, _ = get_learned_adjustment("fix the sql syntax", "fast", 0.7, config, learnings_dir)
            assert boost == 0.0

    def test_never_downgrades_deep(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learnings_dir = self._write_patterns(tmpdir, """
## Pattern: Simple git ops
- **Keywords:** git, status, log, diff
- **Confidence:** high
""")
            config = {"learning": {"informed_routing": True, "max_boost": 0.1}}
            boost, _ = get_learned_adjustment("git status and git log", "deep", 0.7, config, learnings_dir)
            assert boost == 0.0

    def test_max_boost_capped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learnings_dir = self._write_patterns(tmpdir, """
## Pattern: All database ops are complex
- **Keywords:** sql, database, query, migration, index, schema, table, column
- **Confidence:** high
""")
            config = {"learning": {"informed_routing": True, "max_boost": 0.1}}
            boost, _ = get_learned_adjustment(
                "optimize database query migration index schema table", "fast", 0.5, config, learnings_dir,
            )
            assert boost <= 0.1

    def test_empty_query_no_boost(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learnings_dir = self._write_patterns(tmpdir, """
## Pattern: test
- **Keywords:** sql, database
- **Confidence:** high
""")
            config = {"learning": {"informed_routing": True, "max_boost": 0.1}}
            boost, _ = get_learned_adjustment("", "fast", 0.7, config, learnings_dir)
            assert boost == 0.0
