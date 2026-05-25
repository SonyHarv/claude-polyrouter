#!/usr/bin/env node
/**
 * Poly HUD v1.9.1 — Animated ASCII mascot statusLine for Claude Polyrouter.
 *
 * Reads Claude Code's statusLine stdin JSON for live ctx% and rate_limits,
 * with graceful fallback to the session-state file when stdin is absent or
 * fields are missing. Outputs a single statusLine string with zero
 * additionalContext token cost.
 *
 * v1.9.1 changes:
 *   - Native OAuth usage polling: reads ~/.claude/.credentials.json, calls
 *     api.anthropic.com/api/oauth/usage in a detached child process, caches
 *     to ~/.claude/polyrouter-usage-cache.json. Surfaces sonnet weekly (snt)
 *     and Max-plan extra usage that CC stdin does not expose.
 *   - 🧠 indicator on opus subagent / xhigh effort (deep reasoning).
 *   - 📁<dir> CWD indicator in tail group.
 */

import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { request as httpsRequest } from "node:https";

const home = homedir();
const POLY_LABEL = (() => {
  try {
    const here = dirname(fileURLToPath(import.meta.url));
    const pkg = JSON.parse(readFileSync(join(here, "..", ".claude-plugin", "plugin.json"), "utf-8"));
    return pkg && pkg.version ? `poly v${pkg.version}` : "poly";
  } catch { return "poly"; }
})();
const SESSION_PATH = join(home, ".claude", "polyrouter-session.json");
const STATS_PATH = join(home, ".claude", "polyrouter-stats.json");
const COMPACT_PATH = join(home, ".claude", "polyrouter-compact.json");

// v1.9.1: OAuth usage polling (sonnet weekly + Max-plan extra usage).
const CREDENTIALS_PATH = join(home, ".claude", ".credentials.json");
const USAGE_CACHE_PATH = join(home, ".claude", "polyrouter-usage-cache.json");
const USAGE_ENDPOINT_HOST = "api.anthropic.com";
const USAGE_ENDPOINT_PATH = "/api/oauth/usage";
const USAGE_TTL_SEC = 60;
const USAGE_TIMEOUT_MS = 4000;
const HUD_SCRIPT = fileURLToPath(import.meta.url);

const SEP = " │ "; // ' │ '

// --- Poly mascot animation frames (must stay in sync with hud.py) ---

const MASCOT_STATES = {
  idle: {
    frames: ["[^.^]~", "[^.^]~", "[^-^]", "[^.^]~"],
    color: "#afa9ec",
  },
  routing: {
    frames: ["[^o^]»", "[^o^]»»", "[^O^]»»»"],
    color: "#5dcaa5",
  },
  keepalive: {
    frames: ["[^.^]z", "[~.~]zz", "[~_~]zzz", "[^.^]*"],
    color: "#484f58",
  },
  danger: {
    frames: ["[°O°]!", "[°O°]!!", "[>O<]!!!", "[>O<]!!!!"],
    color: "#e24b4a",
  },
  thinking: {
    frames: ["[^.^].", "[^.^]..", "[^.^]...", "[^.~]..."],
    color: "#ef9f27",
  },
  compact: {
    frames: ["[^.^]~", "[^.^]~~", "[^.^]~~~", "[^.^]ok"],
    color: "#97c459",
  },
  // v1.6 new states
  ctx_high: {
    frames: ["[>.^]", "[>.^]~", "[>.^]!", "[>.^]~"],
    color: "#e8853a",
  },
  critical: {
    frames: ["[x.x]", "[x.x]!", "[x.x]!!", "[x.x]"],
    color: "#e24b4a",
  },
};

const TIER_SHORT = { fast: "fast", standard: "std", deep: "deep" };
const TIER_MODELS = { fast: "haiku", standard: "sonnet", deep: "opus" };

// --- Cache freshness bar ---
const CACHE_BAR_LEVELS = [
  { max: 600,  bar: "cache:█████", color: "#97c459" },   // 0-10 min: fresh
  { max: 1800, bar: "cache:████░", color: "#ef9f27" },   // 10-30 min: warm
  { max: 3000, bar: "cache:███░░ !", color: "#e8853a" }, // 30-50 min: warning
];
const CACHE_BAR_EXPIRED = { bar: "cache:░░░░░ exp", color: "#e24b4a" };

function cacheBar(elapsedSec) {
  for (const lvl of CACHE_BAR_LEVELS) {
    if (elapsedSec < lvl.max) return lvl;
  }
  return CACHE_BAR_EXPIRED;
}

// --- ANSI true-color helpers ---

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function ansiColor(text, hex) {
  const [r, g, b] = hexToRgb(hex);
  return `\x1b[38;2;${r};${g};${b}m${text}\x1b[0m`;
}

// --- Threshold-based ANSI coloring (OMC parity) ---
// Normal (<70%): green. Warning (70-89%): yellow. Critical (>=90%): red.
// NO_COLOR env var disables all coloring per the NO_COLOR convention.
const ANSI_RESET = "\x1b[0m";
const ANSI_GREEN = "\x1b[32m";
const ANSI_YELLOW = "\x1b[33m";
const ANSI_RED = "\x1b[31m";

function colorEnabled() {
  return !process.env.NO_COLOR;
}

function thresholdColor(pct) {
  if (pct == null || !colorEnabled()) return "";
  if (pct >= 90) return ANSI_RED;
  if (pct >= 70) return ANSI_YELLOW;
  return ANSI_GREEN;
}

function colorPct(pct) {
  const c = thresholdColor(pct);
  return c ? `${c}${pct}%${ANSI_RESET}` : `${pct}%`;
}

// --- OAuth usage polling (v1.9.1) ---
// HUD reads cache synchronously; if stale, spawns a detached refresh process
// that performs the HTTPS call and writes the cache. Current render returns
// whatever is in cache (potentially stale or null). Never blocks rendering.

function readUsageCache() {
  if (!existsSync(USAGE_CACHE_PATH)) return null;
  try {
    const data = JSON.parse(readFileSync(USAGE_CACHE_PATH, "utf-8"));
    if (typeof data !== "object" || data === null) return null;
    return data;
  } catch { return null; }
}

function isUsageCacheFresh(cache) {
  if (!cache || typeof cache.cached_at !== "number") return false;
  return (Date.now() / 1000 - cache.cached_at) < USAGE_TTL_SEC;
}

function spawnUsageRefresh() {
  try {
    const cp = spawn(process.execPath, [HUD_SCRIPT], {
      detached: true,
      stdio: "ignore",
      env: { ...process.env, POLY_REFRESH_USAGE: "1" },
    });
    cp.unref();
  } catch { /* silent — refresh is best-effort */ }
}

function getOAuthUsage() {
  const cache = readUsageCache();
  if (isUsageCacheFresh(cache)) return cache;
  spawnUsageRefresh();
  return cache; // may be stale or null this cycle; next render will see fresh
}

function readOAuthToken() {
  if (!existsSync(CREDENTIALS_PATH)) return null;
  let data;
  try { data = JSON.parse(readFileSync(CREDENTIALS_PATH, "utf-8")); }
  catch { return null; }
  if (typeof data !== "object" || data === null) return null;
  for (const key of ["claudeAiOauth", "oauth", "auth"]) {
    const inner = data[key];
    if (inner && typeof inner === "object") {
      const tok = inner.accessToken || inner.access_token
                  || inner.oauthToken || inner.token;
      if (tok) return String(tok);
    }
  }
  const tok = data.oauthToken || data.access_token || data.token;
  return tok ? String(tok) : null;
}

function normalizeUsage(raw) {
  const toEpoch = (v) => {
    if (!v) return null;
    if (typeof v === "number") return Math.floor(v);
    const t = Date.parse(String(v));
    return Number.isFinite(t) ? Math.floor(t / 1000) : null;
  };
  const toPct = (v) => {
    if (v == null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  return {
    five_hour_pct: toPct(raw.fiveHourPercent),
    five_hour_resets_at: toEpoch(raw.fiveHourResetsAt),
    weekly_pct: toPct(raw.weeklyPercent),
    weekly_resets_at: toEpoch(raw.weeklyResetsAt),
    sonnet_weekly_pct: toPct(raw.sonnetWeeklyPercent),
    sonnet_weekly_resets_at: toEpoch(raw.sonnetWeeklyResetsAt),
    extra_pct: toPct(raw.extraUsagePercent),
    extra_dollars: toPct(raw.extraUsageDollars),
    extra_limit: toPct(raw.extraUsageLimit),
    cached_at: Date.now() / 1000,
  };
}

function refreshUsageCache() {
  return new Promise((resolve) => {
    const token = readOAuthToken();
    if (!token) { resolve(false); return; }
    const req = httpsRequest({
      host: USAGE_ENDPOINT_HOST,
      path: USAGE_ENDPOINT_PATH,
      method: "GET",
      timeout: USAGE_TIMEOUT_MS,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "User-Agent": "claude-polyrouter/1.9.1",
      },
    }, (res) => {
      if (res.statusCode !== 200) { res.resume(); resolve(false); return; }
      let body = "";
      res.setEncoding("utf-8");
      res.on("data", (chunk) => { body += chunk; });
      res.on("end", () => {
        try {
          const parsed = JSON.parse(body);
          if (typeof parsed !== "object" || parsed === null) { resolve(false); return; }
          const normalized = normalizeUsage(parsed);
          import("node:fs").then(({ writeFileSync }) => {
            try { writeFileSync(USAGE_CACHE_PATH, JSON.stringify(normalized), "utf-8"); }
            catch { /* silent */ }
            resolve(true);
          });
        } catch { resolve(false); }
      });
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { try { req.destroy(); } catch {} resolve(false); });
    req.end();
  });
}

// --- Helpers ---

function readStdin() {
  try { return readFileSync(0, "utf-8"); } catch { return ""; }
}

function parseStdinJson(stdin) {
  if (!stdin) return null;
  try { return JSON.parse(stdin); } catch { return null; }
}

function readJson(path) {
  if (!existsSync(path)) return null;
  try { return JSON.parse(readFileSync(path, "utf-8")); } catch { return null; }
}

function getFrame(state, tick) {
  const s = MASCOT_STATES[state];
  if (!s) return MASCOT_STATES.idle.frames[0];
  return s.frames[tick % s.frames.length];
}

function formatSeconds(sec) {
  if (sec == null || sec < 0) return null;
  sec = Math.floor(sec);
  if (sec < 86400) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return `${h}h${m}m`;
  }
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  return `${d}d${h}h`;
}

// Resolve a rate-limit block from Claude Code stdin (preferred) or fall
// back to the session-file shape. Returns { pct, rem } where rem is
// remaining seconds or null.
function resolveLimit(ccBlock, sessionPct, sessionRem) {
  const nowSec = Date.now() / 1000;
  let pct = null, rem = null;
  if (ccBlock && typeof ccBlock.used_percentage === "number") {
    pct = Math.round(ccBlock.used_percentage);
  }
  if (ccBlock && typeof ccBlock.resets_at === "number") {
    rem = Math.max(0, Math.floor(ccBlock.resets_at - nowSec));
  }
  if (pct == null && sessionPct != null) pct = sessionPct;
  if (rem == null && sessionRem != null) rem = sessionRem;
  return { pct, rem };
}

function detectState(session, compact, ctxPct) {
  if (!session || !session.last_route) return "idle";

  const elapsed = (Date.now() / 1000) - (session.last_query_time || 0);
  const limits = session.limits || {};

  // Critical: any limit >= 90% or ctx >= 90%
  const anyLimitCritical = ["five_hour_pct", "weekly_pct", "sonnet_weekly_pct"]
    .some(k => limits[k] != null && limits[k] >= 90);
  if ((ctxPct != null && ctxPct >= 90) || anyLimitCritical) return "critical";

  if (ctxPct != null && ctxPct >= 70) return "ctx_high";

  if (elapsed > 3000) return "danger";
  if (elapsed > 2400) return "keepalive";
  if (elapsed < 3) return "routing";
  if (elapsed < 10) return "thinking";
  if (compact && compact.advisory_active) return "compact";

  return "idle";
}

// --- Main ---

function main() {
 try {
  const stdin = readStdin();
  const cc = parseStdinJson(stdin); // Claude Code statusLine input (may be null)
  const session = readJson(SESSION_PATH);
  const stats = readJson(STATS_PATH);
  const compact = readJson(COMPACT_PATH);

  // Timeout check: no display if >30 min stale
  if (session && session.last_query_time) {
    const elapsed = (Date.now() / 1000) - session.last_query_time;
    if (elapsed > 1800) {
      console.log(`[${POLY_LABEL}] [^.^]~ idle`);
      return;
    }
  }

  // --- Resolve live data: prefer Claude Code stdin, fallback to session ---
  const sessionLimits = (session && session.limits) ? session.limits : {};
  const liveCtx = cc?.context_window?.used_percentage;
  const ctxPct = (typeof liveCtx === "number")
    ? Math.round(liveCtx)
    : ((session && session.ctx_tokens) ? session.ctx_tokens : null);

  const fh = resolveLimit(
    cc?.rate_limits?.five_hour,
    sessionLimits.five_hour_pct,
    sessionLimits.five_hour_remaining_sec,
  );
  const wk = resolveLimit(
    cc?.rate_limits?.seven_day,
    sessionLimits.weekly_pct,
    sessionLimits.weekly_remaining_sec,
  );
  // snt: prefer OAuth poll (v1.9.1), fall back to session.
  // CC stdin does not expose Sonnet weekly at all.
  const oauthUsage = getOAuthUsage();
  let sntPct = null, sntRem = null;
  if (oauthUsage && oauthUsage.sonnet_weekly_pct != null) {
    sntPct = Math.round(oauthUsage.sonnet_weekly_pct);
    if (oauthUsage.sonnet_weekly_resets_at) {
      sntRem = Math.max(
        0,
        Math.floor(oauthUsage.sonnet_weekly_resets_at - Date.now() / 1000),
      );
    }
  } else {
    const snt = resolveLimit(
      null,
      sessionLimits.sonnet_weekly_pct,
      sessionLimits.sonnet_weekly_remaining_sec,
    );
    sntPct = snt.pct;
    sntRem = snt.rem;
  }

  const state = detectState(session, compact, ctxPct);
  const tick = Math.floor(Date.now() / 1000);
  const frame = getFrame(state, tick);
  const stateColor = MASCOT_STATES[state]?.color || MASCOT_STATES.idle.color;

  const elapsed = session && session.last_query_time
    ? (Date.now() / 1000) - session.last_query_time
    : null;

  const subagentActive = session && session.subagent_active;
  // Subagent counter source: session-only. Claude Code stdin does not
  // currently expose an agents/subagents field.
  const subagentCount = (session && session.subagent_count) || 0;
  const execModel = session && session.exec_model;
  const execEffort = session && session.exec_effort;
  const execAdvisor = session && session.exec_advisor;
  const effortLevel = session && session.effort_level;
  const requiresAdvisor = session && session.requires_advisor;
  const swapDetected = session && session.swap_detected === true;
  // v1.7: retry-escalation state
  const retryActive = session && session.retry_active === true;
  const retryFromTier = session && session.retry_from_tier;
  const retryFromEffort = session && session.retry_from_effort;
  const retryToTier = session && session.retry_to_tier;
  const retryToEffort = session && session.retry_to_effort;
  const retryAtCeiling = session && session.retry_at_ceiling === true;
  // v1.9: Karpathy verifiability routing
  const verifType = session && session.verifiability_type;

  // --- Model segment ---
  let modelSeg = "";
  if (session && session.last_route) {
    const tier = session.last_route;

    // v1.7: retry-escalation arrow replaces the base model·route segment.
    // When at_ceiling, retry is active but no escalation happened — render
    // the normal segment + a ⚠max glyph below.
    let base;
    if (retryActive && !retryAtCeiling && retryFromTier && retryToTier) {
      const fromModel = TIER_MODELS[retryFromTier] || retryFromTier;
      const fromRoute = TIER_SHORT[retryFromTier] || retryFromTier;
      const toModel = TIER_MODELS[retryToTier] || retryToTier;
      const toRoute = TIER_SHORT[retryToTier] || retryToTier;
      let fromEff = "";
      if (retryFromTier === "deep" && (retryFromEffort === "high" || retryFromEffort === "xhigh")) {
        fromEff = `·${retryFromEffort}`;
      }
      let toEff = "";
      if (retryToTier === "deep" && (retryToEffort === "high" || retryToEffort === "xhigh")) {
        toEff = `·${retryToEffort}`;
      }
      base = `${fromModel}·${fromRoute}${fromEff} → ${toModel}·${toRoute}${toEff}`;
    } else {
      const model = TIER_MODELS[tier] || tier;
      const route = TIER_SHORT[tier] || tier;
      let effortSuffix = "";
      if (tier === "deep" && (effortLevel === "high" || effortLevel === "xhigh")) {
        effortSuffix = `·${effortLevel}`;
      }
      base = `${model}·${route}${effortSuffix}`;
    }

    if (subagentActive) {
      modelSeg = `prompt:${base}`;
      if (execAdvisor) {
        modelSeg += `·adv`;
      }
    } else {
      modelSeg = base;
      if (requiresAdvisor) {
        modelSeg += `·adv`;
      }
    }

    // ⚠compact when ctx >= 70% or Claude Code flags 200k overflow
    const ctxCompact = (ctxPct !== null && ctxPct >= 70)
      || (cc && cc.exceeds_200k_tokens === true);
    if (ctxCompact) {
      modelSeg += " ⚠compact";
    }

    // v1.7: silent model swap (CC used a different family than poly routed)
    if (swapDetected) {
      modelSeg += " ⚠swap";
    }

    // v1.7: retry at ceiling (deep/xhigh) — no escalation possible
    if (retryActive && retryAtCeiling) {
      modelSeg += " ⚠max";
    }

    // v1.9: Karpathy verifiability indicator
    if (verifType === "verifiable") {
      modelSeg += " ✓"; // ✓
    } else if (verifType === "non_verifiable") {
      modelSeg += " ~";
    }

    // v1.9.1: 🧠 thinking indicator for xhigh effort (only when no subagent —
    // subagent case is handled below on the exec segment).
    if (!subagentActive && effortLevel === "xhigh") {
      modelSeg += "🧠";
    }
  }

  // --- Exec segment ---
  // v1.9: show indicator whenever a subagent is active, even when the
  // exec_model snapshot has not landed yet (race between Task dispatch
  // and PreToolUse:Task hook write).
  let execSeg = "";
  if (subagentActive) {
    if (execModel) {
      const execParts = [execModel];
      if (execEffort) execParts.push(execEffort);
      if (execAdvisor) execParts.push("adv");
      execSeg = ` ⚙ exec:${execParts.join("·")}`;
      // v1.9.1: 🧠 when subagent is doing extended reasoning
      // (opus tier OR xhigh effort regardless of tier).
      const isDeepSubagent = String(execModel).toLowerCase().includes("opus")
        || execEffort === "xhigh";
      if (isDeepSubagent) execSeg += "🧠";
    } else {
      execSeg = ` ⚙ exec:running`;
    }
  }

  // --- Group 1: prefix + mascot + model + exec ---
  const group1Parts = [`[${POLY_LABEL}] ${ansiColor(frame, stateColor)}`];
  if (modelSeg) {
    group1Parts.push(modelSeg + execSeg);
  } else if (execSeg) {
    group1Parts.push(execSeg.trim());
  }
  const group1 = group1Parts.join(" ");

  // --- Middle group: 🤖N cache ctx ---
  // v1.9: always emit when data is present. CC owns terminal-width wrapping.
  const middleParts = [];
  if (subagentCount > 0) {
    middleParts.push(`🤖${subagentCount}`);
  }
  if (elapsed !== null) {
    const cb = cacheBar(elapsed);
    middleParts.push(ansiColor(cb.bar, cb.color));
  }
  if (ctxPct !== null) {
    middleParts.push(`ctx:${colorPct(ctxPct)}`);
  }

  // --- Limits group ---
  // v1.9: always emit when data is present.
  const limitsParts = [];
  const renderLimit = (label, pct, remSec) => {
    if (pct == null) return null;
    const r = formatSeconds(remSec);
    const v = colorPct(pct);
    return r ? `${label}:${v}(${r})` : `${label}:${v}`;
  };
  const a = renderLimit("5h", fh.pct, fh.rem); if (a) limitsParts.push(a);
  const b = renderLimit("wk", wk.pct, wk.rem); if (b) limitsParts.push(b);
  const c = renderLimit("snt", sntPct, sntRem); if (c) limitsParts.push(c);

  // v1.9.1: Max-plan extra usage. Only render when OAuth poll reports it.
  if (oauthUsage && oauthUsage.extra_pct != null) {
    const pct = Math.round(oauthUsage.extra_pct);
    const dol = oauthUsage.extra_dollars;
    const lim = oauthUsage.extra_limit;
    let label = `extra:${colorPct(pct)}`;
    if (dol != null && lim != null) {
      label += `($${Number(dol).toFixed(2)}/$${Number(lim).toFixed(2)})`;
    }
    limitsParts.push(label);
  }

  // --- Tail: CWD + savings + lang ---
  // v1.9.1: 📁<dirname> shows current working directory.
  const tailParts = [];
  try {
    const cwdName = basename(process.cwd());
    if (cwdName) tailParts.push(`📁${cwdName}`);
  } catch { /* silent */ }
  if (stats && stats.estimated_savings > 0) {
    tailParts.push(`$${stats.estimated_savings.toFixed(2)}↓`);
  }
  if (session && session.last_language) {
    tailParts.push(session.last_language);
  }

  // --- Assemble segments with │ separator ---
  const segments = [group1];
  if (middleParts.length > 0) segments.push(middleParts.join(" "));
  if (limitsParts.length > 0) segments.push(limitsParts.join(" "));
  if (tailParts.length > 0) segments.push(tailParts.join(" "));

  console.log(segments.join(SEP));
 } catch (_e) {
  // v1.8.2: never let the HUD vanish — emit minimal fallback on any throw.
  try { console.log(`[${POLY_LABEL}] [^.^]~`); } catch (_e2) { /* silent */ }
 }
}

// v1.9.1: when invoked with POLY_REFRESH_USAGE=1, perform OAuth poll only
// and exit. The HUD spawns this mode in a detached child to keep the visible
// render fast.
if (process.env.POLY_REFRESH_USAGE === "1") {
  refreshUsageCache().then(() => process.exit(0), () => process.exit(0));
} else {
  main();
}
