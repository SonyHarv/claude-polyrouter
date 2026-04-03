#!/usr/bin/env python3
"""SessionStart hook: check for plugin updates on GitHub."""

import json
import os
import sys
import urllib.request
from pathlib import Path


def main():
    plugin_root = Path(os.environ.get(
        "CLAUDE_PLUGIN_ROOT",
        Path(__file__).parent.parent,
    ))

    # Read current version
    try:
        plugin_json = json.loads(
            (plugin_root / "plugin.json").read_text(encoding="utf-8")
        )
        current_version = plugin_json.get("version", "0.0.0")
    except Exception:
        return  # can't read version, skip silently

    # Read config for repo name
    config_path = Path.home() / ".claude" / "polyrouter" / "config.json"
    repo = "sonyharv/claude-polyrouter"
    try:
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            repo = config.get("updates", {}).get("repo", repo)
            if not config.get("updates", {}).get("check_on_start", True):
                return
    except Exception:
        pass

    # Check latest release
    try:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        latest_version = data.get("tag_name", "").lstrip("v")

        if latest_version and latest_version != current_version:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": (
                        f"[Polyrouter] Update available: v{current_version} -> v{latest_version}. "
                        f"Run: claude plugin update claude-polyrouter"
                    ),
                }
            }
            print(json.dumps(output))
    except Exception:
        pass  # silent on any failure


if __name__ == "__main__":
    main()
