#!/usr/bin/env node
/**
 * Poly HUD — Animated ASCII mascot statusLine for Claude Polyrouter.
 *
 * Reads session + stats JSON, resolves OMC coexistence, outputs a single
 * statusLine string with zero additionalContext token cost.
 *
 * Format: [polyrouter] [^.^] ~ · sonnet · std · ████░ · $12.34↓ · es
 */

import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { execSync } from "node:child_process";

const home = homedir();
const SESSION_PATH = join(home, ".claude", "polyrouter-session.json");
const STATS_PATH = join(home, ".claude", "polyrouter-stats.json");
const COMPACT_PATH = join(home, ".claude", "polyrouter-compact.json");
const OMC_HUD = join(home, ".claude", "hud", "omc-hud.mjs");

// --- Poly mascot animation frames ---

const MASCOT_STATES = {
  idle: {
    frames: ["[^.^]~", "[^.^]~", "[^-^]", "[^.^]~"],
    color: "#afa9ec",
  },
  routing: {
    frames: ["[^o^]\u00BB", "[^o^]\u00BB\u00BB", "[^O^]\u00BB\u00BB\u00BB"],
    color: "#5dcaa5",
  },
  keepalive: {
    frames: ["[^.^]z", "[~.~]zz", "[~_~]zzz", "[^.^]*"],
    color: "#484f58",
  },
  danger: {
    frames: ["[\u00B0O\u00B0]!", "[\u00B0O\u00B0]!!", "[>O<]!!!", "[>O<]!!!!"],
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
};

const TIER_SHORT = { fast: "fast", standard: "std", deep: "deep" };
const TIER_MODELS = { fast: "haiku", standard: "sonnet", deep: "opus" };

// --- Cache freshness bar ---
const CACHE_BAR_LEVELS = [
  { max: 600,  bar: "cache:█████", color: "#97c459" },       // 0-10 min: fresh
  { max: 1800, bar: "cache:████░", color: "#ef9f27" },       // 10-30 min: warm
  { max: 3000, bar: "cache:███░░ !", color: "#e8853a" },     // 30-50 min: warning
];
const CACHE_BAR_EXPIRED = { bar: "cache:░░░░░ exp", color: "#e24b4a" }; // 50+ min

function cacheBar(elapsedSec) {
  for (const lvl of CACHE_BAR_LEVELS) {
    if (elapsedSec < lvl.max) return lvl;
  }
  return CACHE_BAR_EXPIRED;
}
const OMC_NOISE = [
  /omc-setup/i, /not installed/i, /not built/i, /\[OMC HUD\]/i,
  /\[OMC\].*setup/i, /Claude Code has switched/i, /switched to/i,
  /model changed/i, /switching/i,
];

// --- ANSI true-color helpers ---

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function ansiColor(text, hex) {
  const [r, g, b] = hexToRgb(hex);
  return `\x1b[38;2;${r};${g};${b}m${text}\x1b[0m`;
}

// --- Helpers ---

function readStdin() {
  try { return readFileSync(0, "utf-8"); } catch { return ""; }
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

function detectState(session, compact) {
  if (!session || !session.last_route) return "idle";

  // Danger: cache about to expire (>50 min idle)
  const elapsed = (Date.now() / 1000) - (session.last_query_time || 0);
  if (elapsed > 3000) return "danger";       // >50 min
  if (elapsed > 2400) return "keepalive";     // >40 min, drowsy

  // Recent query = routing/thinking (priority over compact)
  if (elapsed < 3) return "routing";
  if (elapsed < 10) return "thinking";

  // Compact advisory active
  if (compact && compact.advisory_active) return "compact";

  return "idle";
}

function getOmcOutput(stdin) {
  if (!existsSync(OMC_HUD)) return "";
  try {
    const raw = execSync(`node "${OMC_HUD}"`, {
      timeout: 5000, encoding: "utf-8",
      input: stdin, stdio: ["pipe", "pipe", "pipe"],
    }).trim();
    if (!raw) return "";
    return raw.split("\n").filter(l => !OMC_NOISE.some(re => re.test(l))).join("\n").trim();
  } catch { return ""; }
}

// --- Main ---

function main() {
  const stdin = readStdin();
  const session = readJson(SESSION_PATH);
  const stats = readJson(STATS_PATH);
  const compact = readJson(COMPACT_PATH);

  // Timeout check: no display if >30 min stale
  if (session && session.last_query_time) {
    const elapsed = (Date.now() / 1000) - session.last_query_time;
    if (elapsed > 1800) {
      // Still show OMC if present
      const omc = getOmcOutput(stdin);
      if (omc) console.log(omc);
      return;
    }
  }

  // Determine Poly state and frame
  const state = detectState(session, compact);
  const tick = Math.floor(Date.now() / 1000);
  const frame = getFrame(state, tick);
  const stateColor = MASCOT_STATES[state]?.color || MASCOT_STATES.idle.color;

  // Elapsed seconds since last query (for cache bar)
  const elapsed = session && session.last_query_time
    ? (Date.now() / 1000) - session.last_query_time
    : null;

  // Build Poly segment — apply ANSI colors
  const parts = [ansiColor(frame, stateColor)];

  if (session && session.last_route) {
    const tier = session.last_route;
    const model = TIER_MODELS[tier] || tier;
    const short = TIER_SHORT[tier] || tier;
    parts.push(model);
    parts.push(short);
  }

  // Cache freshness bar (colored by cache age)
  if (elapsed !== null) {
    const cb = cacheBar(elapsed);
    parts.push(ansiColor(cb.bar, cb.color));
  }

  // Stats: savings
  if (stats && stats.estimated_savings > 0) {
    parts.push(`$${stats.estimated_savings.toFixed(2)}\u2193`);
  }

  // Language
  if (session && session.last_language) {
    parts.push(session.last_language);
  }

  const polyLine = `[polyrouter] ${parts.join(" \u00B7 ")}`;

  // OMC coexistence: OMC goes first, Poly appends
  const omc = getOmcOutput(stdin);
  const output = omc ? `${omc}  ${polyLine}` : polyLine;

  console.log(output);
}

main();
