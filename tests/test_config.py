import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.config import DEFAULT_CONFIG, load_config, find_project_config


class TestDefaultConfig:
    def test_has_three_levels(self):
        assert "fast" in DEFAULT_CONFIG["levels"]
        assert "standard" in DEFAULT_CONFIG["levels"]
        assert "deep" in DEFAULT_CONFIG["levels"]

    def test_each_level_has_model_and_agent(self):
        for level_name, level in DEFAULT_CONFIG["levels"].items():
            assert "model" in level, f"{level_name} missing model"
            assert "agent" in level, f"{level_name} missing agent"
            assert "cost_per_1k_input" in level, f"{level_name} missing cost_per_1k_input"
            assert "cost_per_1k_output" in level, f"{level_name} missing cost_per_1k_output"

    def test_default_level_is_fast(self):
        assert DEFAULT_CONFIG["default_level"] == "fast"

    def test_confidence_threshold(self):
        assert DEFAULT_CONFIG["confidence_threshold"] == 0.7


class TestLoadConfig:
    def test_returns_defaults_when_no_files_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            global_path = Path(tmpdir) / "polyrouter" / "config.json"
            with patch("lib.config.GLOBAL_CONFIG_PATH", global_path):
                with patch("lib.config.find_project_config", return_value=None):
                    config = load_config()
            assert config["default_level"] == "fast"
            assert config["levels"]["fast"]["model"] == "haiku"

    def test_global_config_overrides_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / "polyrouter"
            global_dir.mkdir()
            global_path = global_dir / "config.json"
            global_path.write_text(json.dumps({"default_level": "standard"}))
            with patch("lib.config.GLOBAL_CONFIG_PATH", global_path):
                with patch("lib.config.find_project_config", return_value=None):
                    config = load_config()
            assert config["default_level"] == "standard"
            assert config["levels"]["fast"]["model"] == "haiku"

    def test_project_config_overrides_global(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / "polyrouter"
            global_dir.mkdir()
            global_path = global_dir / "config.json"
            global_path.write_text(json.dumps({"default_level": "standard"}))
            project_path = Path(tmpdir) / "project" / "config.json"
            project_path.parent.mkdir()
            project_path.write_text(json.dumps({"default_level": "deep"}))
            with patch("lib.config.GLOBAL_CONFIG_PATH", global_path):
                with patch("lib.config.find_project_config", return_value=project_path):
                    config = load_config()
            assert config["default_level"] == "deep"

    def test_shallow_merge_dicts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / "polyrouter"
            global_dir.mkdir()
            global_path = global_dir / "config.json"
            override = {"levels": {"fast": {"model": "sonnet", "agent": "standard-executor"}}}
            global_path.write_text(json.dumps(override))
            with patch("lib.config.GLOBAL_CONFIG_PATH", global_path):
                with patch("lib.config.find_project_config", return_value=None):
                    config = load_config()
            assert config["levels"]["fast"]["model"] == "sonnet"
            assert config["levels"]["standard"]["model"] == "sonnet"

    def test_corrupted_config_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / "polyrouter"
            global_dir.mkdir()
            global_path = global_dir / "config.json"
            global_path.write_text("NOT VALID JSON {{{")
            with patch("lib.config.GLOBAL_CONFIG_PATH", global_path):
                with patch("lib.config.find_project_config", return_value=None):
                    config = load_config()
            assert config["default_level"] == "fast"
