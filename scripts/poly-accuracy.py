#!/usr/bin/env python3
"""Accuracy runner for the polyrouter classification pipeline.

Loads tests/fixtures/accuracy_corpus.json, runs each prompt through the
same stages used in production (extract_signals → compute_score → tier →
architectural promotion), and writes a Markdown report to
~/claude-code-analysis/poly-scorer-accuracy.md.

Exit code is non-zero if overall accuracy falls under the target (default
0.80) so the script can act as a CI gate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
LANG_DIR = REPO_ROOT / "languages"
CORPUS_PATH = REPO_ROOT / "tests" / "fixtures" / "accuracy_corpus.json"
DEFAULT_REPORT = Path.home() / "claude-code-analysis" / "poly-scorer-accuracy.md"
DEFAULT_TARGET = 0.80

sys.path.insert(0, str(HOOKS_DIR))

from lib.classifier import compile_patterns, extract_signals  # noqa: E402
from lib.config import load_config  # noqa: E402
from lib.detector import load_languages  # noqa: E402
from lib.effort import (  # noqa: E402
    compute_deep_effort,
    maybe_promote_to_deep_xhigh,
    requires_advisor,
)
from lib.scorer import compute_score, score_to_tier  # noqa: E402

TIERS = ("fast", "standard", "deep")


def classify(query: str, lang: str, languages: dict, compiled: dict, config: dict):
    """Run the pipeline for one prompt. Returns (tier, effort, score, signals)."""
    lang_codes = [lang] if lang in languages else list(languages.keys())
    ps = extract_signals(query, lang_codes, compiled)

    score, _method = compute_score(query, ps.signals, ps.word_count, context=None)
    thresholds = config.get("scoring", {}).get("thresholds", None)
    level, _confidence = score_to_tier(score, thresholds)

    level, arch_promoted = maybe_promote_to_deep_xhigh(level, ps.signals, query)

    if level == "deep":
        effort = "xhigh" if arch_promoted else compute_deep_effort(
            score, ps.signals, query, ps.word_count,
        )
    else:
        effort = {"fast": "low", "standard": "medium"}.get(level, "medium")

    return level, effort, round(score, 3), ps.signals


def evaluate(corpus: dict, languages: dict, compiled: dict, config: dict):
    """Run the classifier over every prompt and collect per-tier stats."""
    results = []
    per_tier_tp = defaultdict(int)
    per_tier_fp = defaultdict(int)
    per_tier_fn = defaultdict(int)
    per_tier_total = defaultdict(int)
    per_lang_total = defaultdict(int)
    per_lang_correct = defaultdict(int)
    confusion = defaultdict(lambda: defaultdict(int))

    correct = 0
    for item in corpus.get("prompts", []):
        query = item.get("query", "")
        expected = item.get("expected", "fast")
        lang = item.get("lang", "en")

        predicted, effort, score, signals = classify(
            query, lang, languages, compiled, config,
        )

        per_tier_total[expected] += 1
        per_lang_total[lang] += 1
        confusion[expected][predicted] += 1

        hit = predicted == expected
        if hit:
            correct += 1
            per_tier_tp[expected] += 1
            per_lang_correct[lang] += 1
        else:
            per_tier_fn[expected] += 1
            per_tier_fp[predicted] += 1

        results.append({
            "lang": lang,
            "expected": expected,
            "predicted": predicted,
            "effort": effort,
            "score": score,
            "advisor": requires_advisor(effort),
            "signals": signals,
            "query": query,
            "hit": hit,
        })

    total = len(results) or 1
    overall = correct / total

    per_tier_metrics = {}
    for tier in TIERS:
        tp = per_tier_tp[tier]
        fp = per_tier_fp[tier]
        fn = per_tier_fn[tier]
        total_tier = per_tier_total[tier] or 1
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) else 0.0
        )
        per_tier_metrics[tier] = {
            "accuracy": tp / total_tier,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "total": per_tier_total[tier],
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }

    per_lang_metrics = {
        lang: {
            "accuracy": per_lang_correct[lang] / (per_lang_total[lang] or 1),
            "correct": per_lang_correct[lang],
            "total": per_lang_total[lang],
        }
        for lang in per_lang_total
    }

    return {
        "results": results,
        "overall": overall,
        "correct": correct,
        "total": total,
        "per_tier": per_tier_metrics,
        "per_lang": per_lang_metrics,
        "confusion": {k: dict(v) for k, v in confusion.items()},
    }


def _signals_str(signals: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(signals.items())) or "none"


def render_report(report: dict, corpus: dict, target: float) -> str:
    lines = []
    lines.append("# Polyrouter Scorer Accuracy Report")
    lines.append("")
    lines.append(f"- **Corpus version:** {corpus.get('version', 'unknown')}")
    lines.append(f"- **Prompts evaluated:** {report['total']}")
    lines.append(
        f"- **Overall accuracy:** {report['overall']:.1%} "
        f"({report['correct']}/{report['total']})"
    )
    lines.append(f"- **Target:** {target:.0%}")
    status = "PASS" if report["overall"] >= target else "FAIL"
    lines.append(f"- **Status:** **{status}**")
    lines.append("")

    lines.append("## Per-tier metrics")
    lines.append("")
    lines.append("| Tier | N | Accuracy | Precision | Recall | F1 |")
    lines.append("|------|---|----------|-----------|--------|-----|")
    for tier in TIERS:
        m = report["per_tier"][tier]
        lines.append(
            f"| {tier} | {m['total']} | {m['accuracy']:.1%} "
            f"| {m['precision']:.1%} | {m['recall']:.1%} | {m['f1']:.2f} |"
        )
    lines.append("")

    lines.append("## Per-language accuracy")
    lines.append("")
    lines.append("| Language | Correct | Total | Accuracy |")
    lines.append("|----------|---------|-------|----------|")
    for lang in sorted(report["per_lang"]):
        m = report["per_lang"][lang]
        lines.append(
            f"| {lang} | {m['correct']} | {m['total']} | {m['accuracy']:.1%} |"
        )
    lines.append("")

    lines.append("## Confusion matrix")
    lines.append("")
    lines.append("Rows are the **gold** tier, columns are what the scorer predicted.")
    lines.append("")
    lines.append("| gold \\ predicted | fast | standard | deep |")
    lines.append("|------------------|------|----------|------|")
    for tier in TIERS:
        row = report["confusion"].get(tier, {})
        lines.append(
            f"| {tier} | {row.get('fast', 0)} | "
            f"{row.get('standard', 0)} | {row.get('deep', 0)} |"
        )
    lines.append("")

    misrouted = [r for r in report["results"] if not r["hit"]]
    lines.append(f"## Misrouted prompts ({len(misrouted)})")
    lines.append("")
    if not misrouted:
        lines.append("None — 100% routing accuracy.")
    else:
        lines.append(
            "| lang | expected | predicted | score | signals | query |"
        )
        lines.append("|------|----------|-----------|-------|---------|-------|")
        for r in misrouted:
            q = r["query"].replace("|", "\\|")
            if len(q) > 80:
                q = q[:77] + "..."
            lines.append(
                f"| {r['lang']} | {r['expected']} | {r['predicted']} | "
                f"{r['score']:.2f} | {_signals_str(r['signals'])} | {q} |"
            )
    lines.append("")

    xhigh = [r for r in report["results"] if r["effort"] == "xhigh"]
    lines.append(f"## xhigh / Advisor escalations ({len(xhigh)})")
    lines.append("")
    if not xhigh:
        lines.append("No prompts escalated to xhigh.")
    else:
        lines.append("| lang | expected | predicted | effort | advisor | query |")
        lines.append("|------|----------|-----------|--------|---------|-------|")
        for r in xhigh:
            q = r["query"].replace("|", "\\|")
            if len(q) > 70:
                q = q[:67] + "..."
            lines.append(
                f"| {r['lang']} | {r['expected']} | {r['predicted']} | "
                f"{r['effort']} | {'yes' if r['advisor'] else 'no'} | {q} |"
            )
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--target", type=float, default=DEFAULT_TARGET)
    parser.add_argument(
        "--quiet", action="store_true", help="suppress stdout summary",
    )
    args = parser.parse_args()

    if not args.corpus.exists():
        print(f"error: corpus not found at {args.corpus}", file=sys.stderr)
        return 2

    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))

    # Isolate from any env override — the runner is a pure offline check.
    os.environ.pop("CLAUDE_CODE_EFFORT_LEVEL", None)

    config = load_config()
    languages = load_languages(LANG_DIR)
    compiled = compile_patterns(languages)

    report = evaluate(corpus, languages, compiled, config)
    markdown = render_report(report, corpus, args.target)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(markdown, encoding="utf-8")

    if not args.quiet:
        print(f"Overall accuracy: {report['overall']:.1%} "
              f"({report['correct']}/{report['total']})")
        for tier in TIERS:
            m = report["per_tier"][tier]
            print(f"  {tier:<8} acc={m['accuracy']:.1%}  "
                  f"P={m['precision']:.1%}  R={m['recall']:.1%}  F1={m['f1']:.2f}")
        print(f"Report: {args.report}")

    return 0 if report["overall"] >= args.target else 1


if __name__ == "__main__":
    sys.exit(main())
