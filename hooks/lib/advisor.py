"""Advisor hand-off protocol — category detection and structured block.

When `requires_advisor=True`, the executor receives a structured
`[POLY:ADVISOR]` block with a category-specific checklist of what to
consult before proposing changes. This module owns the category
taxonomy and the keyword-based detector.

v1.7 (SCOPE FIRME #4):
- 6 categories: auth_redesign, schema_migration, cross_service_refactor,
  security_critical, scaling_decision, architecture_general (fallback).
- Detection is keyword-based, language-agnostic at the keyword level
  (the architectural verbs work in EN; we accept that other languages
  will fall through to architecture_general — that's still a useful
  block, not silence).
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AdvisorCategory:
    """Result of advisor category detection."""

    key: str           # e.g. "auth_redesign"
    label: str         # human-readable, e.g. "Auth redesign"
    checklist: tuple[str, ...]
    confidence: float  # 0.0..1.0 — proportional to keyword-match density


# --- Architectural verbs (any of these elevates a topic match) ---

_ARCH_VERBS = re.compile(
    r"\b(redesign|refactor|replace|migrate|migration|overhaul|"
    r"restructure|rearchitect|rebuild|consolidate|extract|split|"
    r"merge|introduce|remove|rewrite)\b",
    re.IGNORECASE,
)


# --- Per-category keyword sets and checklists ---

_CATEGORIES: tuple[tuple[str, str, re.Pattern, tuple[str, ...]], ...] = (
    (
        "auth_redesign",
        "Auth redesign",
        re.compile(
            r"\b(auth|authentication|authorization|session|sessions|"
            r"jwt|oauth|oauth2|sso|saml|login|logout|token|tokens|"
            r"identity|principal|rbac|permissions?|role|roles)\b",
            re.IGNORECASE,
        ),
        (
            "All current auth touchpoints in the codebase (grep for token, session, login)",
            "Session vs token tradeoffs for this specific change",
            "Backward compatibility with existing credentials in flight",
            "Migration path (rolling vs cutover) and rollback strategy",
        ),
    ),
    (
        "schema_migration",
        "Schema migration",
        re.compile(
            r"\b(schema|migration|migrations|migrate|alter|alteration|"
            r"database|tables?|columns?|indexes?|index|foreign\s+key|"
            r"constraint|data\s+model|denormalize|normalize|denormalization|"
            r"normalization)\b",
            re.IGNORECASE,
        ),
        (
            "List affected tables, indexes, and foreign keys",
            "Estimate downtime, lock time, and concurrent-write safety",
            "Plan rollback (reversible migration vs forward-fix) and monitoring",
            "Data backfill strategy if columns are NOT NULL",
        ),
    ),
    (
        "cross_service_refactor",
        "Cross-service refactor",
        re.compile(
            r"\b(microservice|microservices|cross[-\s]?service|"
            r"service\s+boundary|service\s+boundaries|distributed|"
            r"monolith|api\s+contract|api\s+contracts|inter[-\s]?service|"
            r"event[-\s]?driven|event\s+sourcing|cqrs|saga|"
            r"orchestration|choreography)\b",
            re.IGNORECASE,
        ),
        (
            "Map all service dependencies and ownership boundaries",
            "Identify breaking API contracts and which consumers must update",
            "Plan deployment ordering (which service ships first) and feature flags",
            "Verify observability (tracing, metrics, logs) covers the new edges",
        ),
    ),
    (
        "security_critical",
        "Security-critical change",
        re.compile(
            r"\b(secret|secrets|credential|credentials|encryption|"
            r"encrypt|decrypt|crypto|cryptographic|pii|sensitive\s+data|"
            r"vulnerability|vulnerabilities|cve|compliance|gdpr|hipaa|"
            r"pci|owasp|sql\s+injection|xss|csrf|rce|ssrf|"
            r"sanitiz|input\s+validation)\b",
            re.IGNORECASE,
        ),
        (
            "Threat model: identify attacker capabilities and trust boundaries",
            "Verify cryptographic primitives and key management approach",
            "Audit input validation and output encoding for the affected flow",
            "Document which compliance regime applies (if any) and the impact",
        ),
    ),
    (
        "scaling_decision",
        "Scaling decision",
        re.compile(
            r"\b(scale|scaling|scalability|performance|bottleneck|"
            r"throughput|latency|p95|p99|tail\s+latency|concurrent|"
            r"concurrency|load|capacity|sharding|sharded|partitioning|"
            r"caching|cache\s+strategy|backpressure|rate\s+limit|"
            r"rate[-\s]?limiting)\b",
            re.IGNORECASE,
        ),
        (
            "Quantify current load and target load (RPS, payload size, fan-out)",
            "Identify the actual bottleneck via profiling — not assumptions",
            "Evaluate horizontal vs vertical scaling and stateful constraints",
            "Plan capacity headroom and failure modes under sustained load",
        ),
    ),
)


# Generic fallback — used when requires_advisor=True but no specific category matched.
_GENERIC_CHECKLIST: tuple[str, ...] = (
    "Identify the existing patterns and abstractions this change interacts with",
    "Map the blast radius (which modules / services / tests are affected)",
    "Articulate the tradeoffs of the proposed approach vs the current one",
    "Surface any assumptions you are making and ask before acting on them",
)


def detect_advisor_category(query: str) -> AdvisorCategory:
    """Classify an architectural prompt into one of the v1.7 advisor categories.

    Strategy: count keyword matches per category. The category with the
    highest count wins; ties prefer the earliest declared category. The
    architectural-verb pattern is a confidence multiplier (presence of a
    verb like "redesign"/"migrate" doubles the score) — without it, a
    topical mention may still classify but with lower confidence.

    Falls back to `architecture_general` when no category scored above
    zero — never returns None, so the [POLY:ADVISOR] block is always
    emitted when `requires_advisor=True`.
    """
    if not isinstance(query, str) or not query.strip():
        return AdvisorCategory(
            key="architecture_general",
            label="Architectural decision",
            checklist=_GENERIC_CHECKLIST,
            confidence=0.0,
        )

    has_arch_verb = bool(_ARCH_VERBS.search(query))
    multiplier = 2 if has_arch_verb else 1

    best: tuple[int, str, str, tuple[str, ...]] | None = None
    total_matches = 0

    for key, label, pattern, checklist in _CATEGORIES:
        hits = len(pattern.findall(query))
        if hits == 0:
            continue
        score = hits * multiplier
        total_matches += score
        if best is None or score > best[0]:
            best = (score, key, label, checklist)

    if best is None:
        return AdvisorCategory(
            key="architecture_general",
            label="Architectural decision",
            checklist=_GENERIC_CHECKLIST,
            confidence=0.5 if has_arch_verb else 0.2,
        )

    score, key, label, checklist = best
    # Confidence: capped fraction of total matched score. With arch verb,
    # a single strong category match (score 2) maxes confidence.
    confidence = min(1.0, score / max(total_matches, 1))
    return AdvisorCategory(
        key=key,
        label=label,
        checklist=checklist,
        confidence=confidence,
    )


def format_advisor_block(category: AdvisorCategory) -> str:
    """Render the [POLY:ADVISOR] block for additionalContext.

    Format:
        [POLY:ADVISOR]
        Category: <label>
        Before proposing changes, consult:
          - <bullet 1>
          - <bullet 2>
          ...
        For deep architectural validation: /polyrouter:advisor "your specific question"
    """
    lines = [
        "[POLY:ADVISOR]",
        f"Category: {category.label}",
        "Before proposing changes, consult:",
    ]
    for item in category.checklist:
        lines.append(f"  - {item}")
    lines.append(
        'For deep architectural validation: /polyrouter:advisor "your specific question"'
    )
    return "\n".join(lines)
