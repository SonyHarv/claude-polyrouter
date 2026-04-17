#!/usr/bin/env node
/**
 * Poly HUD v1.6 — Animated ASCII mascot statusLine for Claude Polyrouter.
 *
 * Reads session + stats JSON, resolves OMC coexistence, outputs a single
 * statusLine string with zero additionalContext token cost.
 *
 * Format (no subagent):
 *   [poly v1.6] [^.^]~ haiku·fast │ cache:████░ ctx:8% │ 5h:45%(1h2m) wk:9%(6d19h) snt:3%(6d19h) │ $0.03↓ es
 *
 * Format (with subagent):
 *   [poly v1.6] [^.^]~ prompt:haiku·fast ⚙ exec:opus·xhigh·adv │ 🤖1 cache:████░ ctx:15% │ ... │ $9.50↓ es
 *
 * Format (high ctx):
 *   [poly v1.6] [^.^]~ haiku·fast ⚠compact │ cache:████░ ctx:78% │ ... │ $0.03↓ es
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

const SEP = " \u2502 "; // ' │ '

// --- Poly mascot animation frames (must stay in sync with hud.py) ---

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
  { max: 600,  bar: "cache:\u2588\u2588\u2588\u2588\u2588", color: "#97c459" },   // 0-10 min: fresh
  { max: 1800, bar: "cache:\u2588\u2588\u2588\u2588\u2591", color: "#ef9f27" },   // 10-30 min: warm
  { max: 3000, bar: "cache:\u2588\u2588\u2588\u2591\u2591 !", color: "#e8853a" }, // 30-50 min: warning
];
const CACHE_BAR_EXPIRED = { bar: "cache:\u2591\u2591\u2591\u2591\u2591 exp", color: "#e24b4a" };

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

function detectState(session, compact) {
  if (!session || !session.last_route) return "idle";

  const elapsed = (Date.now() / 1000) - (session.last_query_time || 0);
  const ctxPct = session.ctx_tokens || 0;
  const limits = session.limits || {};

  // Critical: any limit ≥ 90% or ctx ≥ 90%
  const anyLimitCritical = ["five_hour_pct", "weekly_pct", "sonnet_weekly_pct"]
    .some(k => limits[k] != null && limits[k] >= 90);
  if (ctxPct >= 90 || anyLimitCritical) return "critical";

  if (ctxPct >= 70) return "ctx_high";

  if (elapsed > 3000) return "danger";
  if (elapsed > 2400) return "keepalive";
  if (elapsed < 3) return "routing";
  if (elapsed < 10) return "thinking";
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

// --- Terminal width helpers ---

function terminalCols() {
  return process.stdout.columns ?? Infinity;
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
      const omc = getOmcOutput(stdin);
      if (omc) console.log(omc);
      return;
    }
  }

  const state = detectState(session, compact);
  const tick = Math.floor(Date.now() / 1000);
  const frame = getFrame(state, tick);
  const stateColor = MASCOT_STATES[state]?.color || MASCOT_STATES.idle.color;

  const elapsed = session && session.last_query_time
    ? (Date.now() / 1000) - session.last_query_time
    : null;

  const ctxPct = (session && session.ctx_tokens) ? session.ctx_tokens : null;
  const limits = (session && session.limits) ? session.limits : null;
  const subagentActive = session && session.subagent_active;
  const subagentCount = (session && session.subagent_count) || 0;
  const execModel = session && session.exec_model;
  const execEffort = session && session.exec_effort;
  const execAdvisor = session && session.exec_advisor;
  const effortLevel = session && session.effort_level;
  const requiresAdvisor = session && session.requires_advisor;

  const cols = terminalCols();

  // --- Model segment ---
  let modelSeg = "";
  if (session && session.last_route) {
    const tier = session.last_route;
    const model = TIER_MODELS[tier] || tier;
    const route = TIER_SHORT[tier] || tier;

    let effortSuffix = "";
    if (tier === "deep" && (effortLevel === "high" || effortLevel === "xhigh")) {
      effortSuffix = `\u00B7${effortLevel}`;
    }

    if (subagentActive) {
      modelSeg = `prompt:${model}\u00B7${route}${effortSuffix}`;
    } else {
      modelSeg = `${model}\u00B7${route}${effortSuffix}`;
      if (requiresAdvisor) {
        modelSeg += `\u00B7adv`;
      }
    }

    // ⚠compact when ctx ≥ 70%
    if (ctxPct !== null && ctxPct >= 70) {
      modelSeg += " \u26A0compact";
    }
  }

  // --- Exec segment ---
  let execSeg = "";
  if (subagentActive && execModel) {
    const execParts = [execModel];
    if (execEffort) execParts.push(execEffort);
    if (execAdvisor) execParts.push("adv");
    execSeg = ` \u2699 exec:${execParts.join("\u00B7")}`;
  }

  // --- Group 1: prefix + mascot + model + exec ---
  const group1Parts = [`[poly v1.6] ${ansiColor(frame, stateColor)}`];
  if (modelSeg) {
    group1Parts.push(modelSeg + execSeg);
  } else if (execSeg) {
    group1Parts.push(execSeg.trim());
  }
  const group1 = group1Parts.join(" ");

  // --- Middle group: 🤖N cache ctx ---
  // Priority for dropping: snt > wk > 5h > ctx > 🤖N > cache
  const middleParts = [];
  if (subagentCount > 0) {
    middleParts.push(`\uD83E\uDD16${subagentCount}`);
  }
  if (elapsed !== null) {
    const cb = cacheBar(elapsed);
    middleParts.push(ansiColor(cb.bar, cb.color));
  }
  if (ctxPct !== null && cols >= 80) {
    middleParts.push(`ctx:${ctxPct}%`);
  }

  // --- Limits group (tiered hiding) ---
  const limitsParts = [];
  if (limits && cols >= 120) {
    const fhPct = limits.five_hour_pct;
    const fhRem = limits.five_hour_remaining_sec;
    const wkPct = limits.weekly_pct;
    const wkRem = limits.weekly_remaining_sec;
    const sntPct = limits.sonnet_weekly_pct;
    const sntRem = limits.sonnet_weekly_remaining_sec;

    if (fhPct != null) {
      const r = formatSeconds(fhRem);
      limitsParts.push(r ? `5h:${fhPct}%(${r})` : `5h:${fhPct}%`);
    }
    if (wkPct != null) {
      const r = formatSeconds(wkRem);
      limitsParts.push(r ? `wk:${wkPct}%(${r})` : `wk:${wkPct}%`);
    }
    // snt only at full width
    if (sntPct != null) {
      const r = formatSeconds(sntRem);
      limitsParts.push(r ? `snt:${sntPct}%(${r})` : `snt:${sntPct}%`);
    }
  } else if (limits && cols >= 80) {
    // cols 80-119: show 5h + wk, drop snt
    const fhPct = limits.five_hour_pct;
    const fhRem = limits.five_hour_remaining_sec;
    const wkPct = limits.weekly_pct;
    const wkRem = limits.weekly_remaining_sec;
    if (fhPct != null) {
      const r = formatSeconds(fhRem);
      limitsParts.push(r ? `5h:${fhPct}%(${r})` : `5h:${fhPct}%`);
    }
    if (wkPct != null) {
      const r = formatSeconds(wkRem);
      limitsParts.push(r ? `wk:${wkPct}%(${r})` : `wk:${wkPct}%`);
    }
  }
  // cols < 80: limits dropped entirely

  // --- Tail: savings + lang ---
  const tailParts = [];
  if (stats && stats.estimated_savings > 0) {
    tailParts.push(`$${stats.estimated_savings.toFixed(2)}\u2193`);
  }
  if (session && session.last_language) {
    tailParts.push(session.last_language);
  }

  // --- Assemble segments with │ separator ---
  const segments = [group1];
  if (middleParts.length > 0) segments.push(middleParts.join(" "));
  if (limitsParts.length > 0) segments.push(limitsParts.join(" "));
  if (tailParts.length > 0) segments.push(tailParts.join(" "));

  const polyLine = segments.join(SEP);

  // OMC coexistence: OMC goes first
  const omc = getOmcOutput(stdin);
  const output = omc ? `${omc}  ${polyLine}` : polyLine;

  console.log(output);
}

main();
