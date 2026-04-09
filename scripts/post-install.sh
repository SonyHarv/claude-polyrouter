#!/usr/bin/env bash
# post-install.sh — Update HUD symlink to always point to the latest installed version.
# Run automatically as a post-install hook, or manually at any time.
#
# What it does:
#   1. Finds the latest semver version directory under the plugin cache
#   2. Creates/updates a `current` symlink → that version directory
#   3. Ensures ~/.claude/hud/ exists
#   4. Creates/updates ~/.claude/hud/polyrouter-hud.mjs → current/hud/polyrouter-hud.mjs
#   5. Injects the classify-prompt.py UserPromptSubmit hook into settings.json
#
# The HUD symlink goes through `current` so future version bumps only need
# to re-run this script (or the hook) — settings.json never changes.

set -euo pipefail

PLUGIN_CACHE_DIR="$HOME/.claude/plugins/cache/claude-polyrouter/claude-polyrouter"
CURRENT_LINK="$PLUGIN_CACHE_DIR/current"
HUD_DIR="$HOME/.claude/hud"
HUD_LINK="$HUD_DIR/polyrouter-hud.mjs"
SETTINGS_FILE="$HOME/.claude/settings.json"
HOOK_CMD="python3 \${CLAUDE_PLUGIN_ROOT}/hooks/classify-prompt.py"

# ── 1. Find latest installed version ─────────────────────────────────────────
latest_version=$(
  ls -1 "$PLUGIN_CACHE_DIR" 2>/dev/null \
  | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' \
  | sort -V \
  | tail -n1
)

if [[ -z "$latest_version" ]]; then
  echo "[polyrouter] ERROR: No versioned directories found in $PLUGIN_CACHE_DIR" >&2
  exit 1
fi

latest_dir="$PLUGIN_CACHE_DIR/$latest_version"

# ── 2. Fast path: skip if symlinks already correct AND hook already injected ─
hook_exists() {
  [[ -f "$SETTINGS_FILE" ]] && \
  jq -e '.hooks.UserPromptSubmit // [] | map(select(.command and (.command | contains("classify-prompt.py")))) | length > 0' "$SETTINGS_FILE" >/dev/null 2>&1
}

if [[ -L "$CURRENT_LINK" && "$(readlink "$CURRENT_LINK")" == "$latest_dir" ]] \
&& [[ -L "$HUD_LINK" && "$(readlink "$HUD_LINK")" == "$CURRENT_LINK/hud/polyrouter-hud.mjs" ]] \
&& [[ -e "$HUD_LINK" ]] \
&& hook_exists; then
  exit 0
fi

echo "[polyrouter] Updating symlinks for v$latest_version..."

# ── 3. Create/update `current` symlink ───────────────────────────────────────
if [[ -L "$CURRENT_LINK" ]]; then
  rm "$CURRENT_LINK"
elif [[ -e "$CURRENT_LINK" ]]; then
  echo "[polyrouter] ERROR: $CURRENT_LINK exists and is not a symlink — refusing to overwrite." >&2
  exit 1
fi

ln -s "$latest_dir" "$CURRENT_LINK"

# ── 4. Ensure ~/.claude/hud/ exists ──────────────────────────────────────────
mkdir -p "$HUD_DIR"

# ── 5. Create/update HUD symlink via `current` ───────────────────────────────
if [[ -L "$HUD_LINK" ]]; then
  rm "$HUD_LINK"
elif [[ -e "$HUD_LINK" ]]; then
  echo "[polyrouter] ERROR: $HUD_LINK exists and is not a symlink — refusing to overwrite." >&2
  exit 1
fi

ln -s "$CURRENT_LINK/hud/polyrouter-hud.mjs" "$HUD_LINK"
echo "[polyrouter] Symlinks updated: current -> v$latest_version, HUD -> current/hud"

# ── 6. Inject classify-prompt hook into settings.json ────────────────────────
inject_hook() {
  if [[ ! -f "$SETTINGS_FILE" ]]; then
    return 0  # no settings.json — plugin hooks.json will handle it
  fi

  # Check if the hook already exists
  if jq -e '.hooks.UserPromptSubmit // [] | map(select(.command and (.command | contains("classify-prompt.py")))) | length > 0' "$SETTINGS_FILE" >/dev/null 2>&1; then
    return 0  # already present
  fi

  local hook_entry
  hook_entry=$(cat <<'HOOKJSON'
{
  "type": "command",
  "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/classify-prompt.py",
  "timeout": 15
}
HOOKJSON
  )

  local tmp
  tmp=$(mktemp)

  # Ensure .hooks.UserPromptSubmit exists as an array, then append
  jq --argjson hook "$hook_entry" '
    .hooks //= {} |
    .hooks.UserPromptSubmit //= [] |
    .hooks.UserPromptSubmit += [$hook]
  ' "$SETTINGS_FILE" > "$tmp" && mv "$tmp" "$SETTINGS_FILE"

  echo "[polyrouter] Injected classify-prompt hook into settings.json"
}

inject_hook
