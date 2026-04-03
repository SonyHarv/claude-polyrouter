#!/usr/bin/env node
/**
 * Combined HUD: OMC + Claude Polyrouter status line
 * Passes Claude Code stdin to OMC HUD subprocess and appends polyrouter indicator.
 */

import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { execSync } from "node:child_process";

const home = homedir();
const SESSION_PATH = join(home, ".claude", "polyrouter-session.json");
const STATS_PATH = join(home, ".claude", "polyrouter-stats.json");
const OMC_HUD = join(home, ".claude", "hud", "omc-hud.mjs");

const TIER_ICONS = { fast: "⚡", standard: "⚙️", deep: "🧠" };
const TIER_MODELS = { fast: "haiku", standard: "sonnet", deep: "opus" };
const OMC_NOISE = [/omc-setup/i, /not installed/i, /not built/i, /\[OMC HUD\]/i, /\[OMC\].*setup/i];

function readStdin() {
  try {
    return readFileSync(0, "utf-8");
  } catch {
    return "";
  }
}

function getOmcOutput(stdin) {
  if (!existsSync(OMC_HUD)) return "";
  try {
    const raw = execSync(`node "${OMC_HUD}"`, {
      timeout: 5000,
      encoding: "utf-8",
      input: stdin,
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
    if (!raw) return "";
    const clean = raw.split("\n").filter(l => !OMC_NOISE.some(re => re.test(l))).join("\n").trim();
    return clean;
  } catch {
    return "";
  }
}

function getPolyrouter() {
  if (!existsSync(SESSION_PATH)) return null;
  try {
    const data = JSON.parse(readFileSync(SESSION_PATH, "utf-8"));
    if (!data || !data.last_route) return null;

    const elapsed = (Date.now() / 1000) - (data.last_query_time || 0);
    if (elapsed > 1800) return null;

    const tier = data.last_route;
    const icon = TIER_ICONS[tier] || "📡";
    const model = TIER_MODELS[tier] || tier;
    const lang = data.last_language || "";
    const depth = data.conversation_depth || 0;

    let stats = "";
    if (existsSync(STATS_PATH)) {
      try {
        const s = JSON.parse(readFileSync(STATS_PATH, "utf-8"));
        const total = s.total_queries || 0;
        const savings = s.estimated_savings || 0;
        if (total > 0) {
          stats = ` · ${total}q`;
          if (savings > 0) stats += ` · $${savings.toFixed(2)}↓`;
        }
      } catch { /* ignore */ }
    }

    return `${icon} ${model}${lang ? " · " + lang : ""}${depth > 1 ? " · d" + depth : ""}${stats}`;
  } catch {
    return null;
  }
}

function main() {
  const stdin = readStdin();
  const parts = [];

  const omc = getOmcOutput(stdin);
  if (omc) parts.push(omc);

  const pr = getPolyrouter();
  if (pr) parts.push(`[polyrouter] ${pr}`);

  if (parts.length > 0) {
    console.log(parts.join("  "));
  }
}

main();
