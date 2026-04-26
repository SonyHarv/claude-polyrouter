# /clear + session_name Verification Runbook (CALIDAD #17)

**Audience:** maintainers verifying that polyrouter correctly handles
the Claude Code v2.1.120+ behavior where `session_name` survives the
`/clear` command.

**Why this matters:** Before CC v2.1.120, the `session_name` field was
dropped from stdin JSON after `/clear`, so polyrouter's per-session
stats reset along with CC's session state. The fix preserves
`session_name` across `/clear`, and polyrouter now persists it for
stats accumulation only (no HUD display).

---

## Prerequisites

- Claude Code **v2.1.120 or newer** (`claude --version` to confirm).
- A clean polyrouter stats file (or back-up your existing one):
  ```bash
  cp ~/.claude/polyrouter-stats.json ~/.claude/polyrouter-stats.json.bak
  ```

## Smoke test

1. **Start a named session.** From a CC session, set a session name
   either via the `--session-name` CLI flag or via the equivalent
   in-session command supported by your CC build.

2. **Send a routing prompt.** Trigger any prompt that causes
   polyrouter to record a route, e.g. `"explain the codebase"`.

3. **Verify the bucket exists.**
   ```bash
   jq '.by_session_name' ~/.claude/polyrouter-stats.json
   ```
   You should see your session name as a key with `queries: 1`.

4. **Run `/clear`** inside CC.

5. **Send another routing prompt** with no further configuration.

6. **Verify accumulation.**
   ```bash
   jq '.by_session_name' ~/.claude/polyrouter-stats.json
   ```
   The same session name's `queries` should now be `2` (not a new
   bucket, not still `1`). This proves CC re-sent `session_name` after
   `/clear` and polyrouter routed it into the existing bucket.

7. **Verify the stats block displays it.**
   Run `/polyrouter:stats` and confirm the `By session:` section
   appears, with the session name truncated to 20 chars + `…` if
   longer.

## What to do if step 6 shows a new bucket or no bucket

- **No bucket at all:** the hook isn't extracting `session_name`.
  Check `hooks/classify-prompt.py` — `input_data.get("session_name")`
  must be truthy.
- **A new bucket per turn:** CC may not have actually preserved
  `session_name` across `/clear` (older CC, or regression). Check
  with: `jq '.session_name' ~/.claude/polyrouter-session.json` after
  each turn — it should match.
- **Bucket exists but `queries` doesn't increment:** stats write may
  be silently failing. Check file permissions and look for stderr
  warnings from the hook.

## Cleanup

```bash
mv ~/.claude/polyrouter-stats.json.bak ~/.claude/polyrouter-stats.json
```

## Automated coverage

The unit test `tests/test_session_name.py::TestClearCycle` simulates
the two-turn `/clear` cycle without needing a live CC. If that suite
passes, the polyrouter side of the contract is honored — but only the
manual smoke test above proves CC's stdin actually carries
`session_name` through `/clear`.
