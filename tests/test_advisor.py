"""Tests for v1.7 advisor category detection and [POLY:ADVISOR] block formatter.

Covers `lib/advisor.py`:
- detect_advisor_category(): keyword-based classification into 6 buckets
  (auth_redesign, schema_migration, cross_service_refactor, security_critical,
  scaling_decision, architecture_general).
- format_advisor_block(): renders the [POLY:ADVISOR] block with category
  label, checklist bullets, and the manual-escape-hatch hint line.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.advisor import (
    AdvisorCategory,
    detect_advisor_category,
    format_advisor_block,
)


class TestDetectCategoryAuthRedesign:
    """auth_redesign — auth/session/token + architectural verb."""

    def test_auth_redesign_session_migrate(self):
        cat = detect_advisor_category("we need to migrate session handling to JWT")
        assert cat.key == "auth_redesign"
        assert "Auth" in cat.label

    def test_auth_redesign_oauth_replace(self):
        cat = detect_advisor_category("replace the OAuth2 flow with our own SSO")
        assert cat.key == "auth_redesign"

    def test_auth_redesign_rbac_redesign(self):
        cat = detect_advisor_category("redesign the RBAC permissions model")
        assert cat.key == "auth_redesign"


class TestDetectCategorySchemaMigration:
    """schema_migration — schema/table/column + verb."""

    def test_schema_migration_alter_table(self):
        cat = detect_advisor_category("we need to alter the users table to add a NOT NULL column")
        assert cat.key == "schema_migration"

    def test_schema_migration_index_refactor(self):
        cat = detect_advisor_category("refactor the foreign key constraints and indexes")
        assert cat.key == "schema_migration"


class TestDetectCategoryCrossServiceRefactor:
    """cross_service_refactor — microservices/api contract + verb."""

    def test_cross_service_split_monolith(self):
        cat = detect_advisor_category("split the monolith into microservices")
        assert cat.key == "cross_service_refactor"

    def test_cross_service_api_contract_refactor(self):
        cat = detect_advisor_category("refactor the API contract between the gateway and downstream services")
        assert cat.key == "cross_service_refactor"


class TestDetectCategorySecurityCritical:
    """security_critical — secrets/encryption/compliance + verb."""

    def test_security_encryption_migrate(self):
        cat = detect_advisor_category("migrate from AES-128 encryption to a stronger crypto primitive")
        assert cat.key == "security_critical"

    def test_security_pii_refactor(self):
        cat = detect_advisor_category("refactor how we store PII to meet GDPR compliance")
        assert cat.key == "security_critical"


class TestDetectCategoryScalingDecision:
    """scaling_decision — performance/throughput/sharding + verb."""

    def test_scaling_sharding_introduce(self):
        cat = detect_advisor_category("introduce sharding to handle the new throughput requirements")
        assert cat.key == "scaling_decision"

    def test_scaling_caching_overhaul(self):
        cat = detect_advisor_category("overhaul the caching strategy to reduce p99 latency")
        assert cat.key == "scaling_decision"


class TestDetectCategoryGenericFallback:
    """architecture_general — used when no specific category matches."""

    def test_empty_query_returns_generic(self):
        cat = detect_advisor_category("")
        assert cat.key == "architecture_general"
        assert cat.confidence == 0.0

    def test_whitespace_only_returns_generic(self):
        cat = detect_advisor_category("   \n  ")
        assert cat.key == "architecture_general"

    def test_non_string_returns_generic(self):
        cat = detect_advisor_category(None)  # type: ignore[arg-type]
        assert cat.key == "architecture_general"

    def test_arch_verb_only_falls_through(self):
        # Architectural verb but no topic keyword from any of the 5 buckets.
        cat = detect_advisor_category("redesign the build pipeline tooling")
        assert cat.key == "architecture_general"
        # Has arch verb → mid confidence (0.5) per fallback rule.
        assert cat.confidence == pytest.approx(0.5)

    def test_no_arch_verb_no_topic(self):
        cat = detect_advisor_category("just hello world")
        assert cat.key == "architecture_general"
        assert cat.confidence == pytest.approx(0.2)


class TestConfidenceScoring:
    """Architectural verbs act as a confidence multiplier."""

    def test_confidence_is_in_unit_range(self):
        cat = detect_advisor_category("migrate the auth session model")
        assert 0.0 <= cat.confidence <= 1.0

    def test_arch_verb_amplifies_score(self):
        # Both phrases mention auth concepts; the one with an arch verb
        # should classify with at least equal confidence.
        with_verb = detect_advisor_category("redesign the auth system")
        plain = detect_advisor_category("the auth system")
        # Plain still classifies (auth keyword) but at lower confidence.
        assert with_verb.key == "auth_redesign"
        assert plain.key == "auth_redesign"
        assert with_verb.confidence >= plain.confidence


class TestCategoryReturnType:
    """detect_advisor_category always returns a fully populated AdvisorCategory."""

    def test_returns_advisorcategory_instance(self):
        cat = detect_advisor_category("redesign the auth flow")
        assert isinstance(cat, AdvisorCategory)
        assert cat.key
        assert cat.label
        assert isinstance(cat.checklist, tuple)
        assert len(cat.checklist) >= 3  # All categories have meaningful checklists.
        assert all(isinstance(b, str) and b.strip() for b in cat.checklist)

    def test_all_categories_have_distinct_keys(self):
        queries = {
            "auth_redesign": "redesign the auth session model",
            "schema_migration": "migrate the schema to add a column",
            "cross_service_refactor": "refactor microservice api contracts",
            "security_critical": "rewrite the encryption primitives for new compliance",
            "scaling_decision": "overhaul caching for throughput",
        }
        seen_keys = {detect_advisor_category(q).key for q in queries.values()}
        assert seen_keys == set(queries.keys())


class TestFormatAdvisorBlock:
    """format_advisor_block renders the well-known [POLY:ADVISOR] format."""

    def test_block_header_present(self):
        cat = detect_advisor_category("redesign the auth flow")
        block = format_advisor_block(cat)
        assert block.startswith("[POLY:ADVISOR]")
        assert f"Category: {cat.label}" in block
        assert "Before proposing changes, consult:" in block

    def test_block_lists_all_checklist_items(self):
        cat = detect_advisor_category("redesign the auth flow")
        block = format_advisor_block(cat)
        for item in cat.checklist:
            assert f"  - {item}" in block

    def test_block_includes_manual_escape_hatch(self):
        cat = detect_advisor_category("redesign the auth flow")
        block = format_advisor_block(cat)
        assert "/polyrouter:advisor" in block

    def test_block_uses_generic_checklist_for_fallback(self):
        cat = detect_advisor_category("")
        block = format_advisor_block(cat)
        assert "[POLY:ADVISOR]" in block
        assert "Architectural decision" in block  # generic label
        # Generic checklist mentions blast radius / tradeoffs.
        assert "blast radius" in block.lower() or "tradeoff" in block.lower()
