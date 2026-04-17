"""Tests for dynamic effort mapping (Sprint 2)."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from lib.effort import (
    compute_effort,
    compute_deep_effort,
    normalize_effort_for_env,
    requires_advisor,
    maybe_promote_to_deep_xhigh,
    EFFORT_MAP,
    VALID_EFFORTS,
    DISPLAY_EFFORTS,
)


class TestTierMapping:
    """Tier → effort mapping without overrides."""

    def test_fast_maps_to_low(self):
        assert compute_effort("fast") == "low"

    def test_standard_maps_to_medium(self):
        assert compute_effort("standard") == "medium"

    def test_deep_maps_to_high(self):
        assert compute_effort("deep") == "high"

    def test_unknown_tier_defaults_to_medium(self):
        assert compute_effort("unknown") == "medium"

    def test_empty_tier_defaults_to_medium(self):
        assert compute_effort("") == "medium"


class TestUserOverride:
    """User override always takes priority."""

    def test_override_low(self):
        assert compute_effort("deep", user_override="low") == "low"

    def test_override_high_on_fast_tier(self):
        assert compute_effort("fast", user_override="high") == "high"

    def test_override_max_falls_back_to_high(self):
        assert compute_effort("standard", user_override="max") == "high"

    def test_override_medium(self):
        assert compute_effort("deep", user_override="medium") == "medium"

    def test_invalid_override_ignored(self):
        assert compute_effort("deep", user_override="turbo") == "high"

    def test_empty_override_ignored(self):
        assert compute_effort("fast", user_override="") == "low"

    def test_none_override_ignored(self):
        assert compute_effort("fast", user_override=None) == "low"


class TestEnvOverride:
    """Environment variable is second priority after user override."""

    @patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": "max"})
    def test_env_max_falls_back_to_high(self):
        assert compute_effort("fast") == "high"

    @patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": "low"})
    def test_env_low_overrides_deep(self):
        assert compute_effort("deep") == "low"

    @patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": "high"})
    def test_user_override_beats_env(self):
        assert compute_effort("fast", user_override="low") == "low"

    @patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": "invalid"})
    def test_invalid_env_ignored(self):
        assert compute_effort("standard") == "medium"

    @patch.dict(os.environ, {}, clear=True)
    def test_no_env_falls_through(self):
        # Ensure CLAUDE_CODE_EFFORT_LEVEL is not set
        os.environ.pop("CLAUDE_CODE_EFFORT_LEVEL", None)
        assert compute_effort("deep") == "high"


class TestConstants:
    """Verify constants are correct."""

    def test_all_tiers_have_mapping(self):
        for tier in ("fast", "standard", "deep"):
            assert tier in EFFORT_MAP

    def test_all_mappings_are_valid(self):
        for effort in EFFORT_MAP.values():
            assert effort in VALID_EFFORTS

    def test_valid_efforts_complete(self):
        assert VALID_EFFORTS == {"low", "medium", "high"}

    def test_display_efforts_include_xhigh(self):
        assert DISPLAY_EFFORTS == {"low", "medium", "high", "xhigh"}


class TestDynamicDeepEffort:
    """compute_deep_effort classifies deep-tier complexity sub-levels."""

    def test_single_deep_no_combo_is_medium(self):
        assert compute_deep_effort(
            score=0.70, signals={"deep": 1}, query="debug this function", word_count=4,
        ) == "medium"

    def test_bare_deep_spanish_is_medium(self):
        assert compute_deep_effort(
            score=0.68, signals={"deep": 1}, query="arregla este bug por favor", word_count=5,
        ) == "medium"

    def test_deep_plus_standard_is_high(self):
        assert compute_deep_effort(
            score=0.72, signals={"deep": 1, "standard": 1}, query="fix auth logic", word_count=3,
        ) == "high"

    def test_deep_plus_tool_is_high(self):
        assert compute_deep_effort(
            score=0.72, signals={"deep": 1, "tool_intensive": 1}, query="run tests and debug", word_count=4,
        ) == "high"

    def test_deep_plus_orchestration_is_high(self):
        assert compute_deep_effort(
            score=0.72, signals={"deep": 1, "orchestration": 1}, query="coordina pruebas", word_count=2,
        ) == "high"

    def test_double_deep_is_high(self):
        assert compute_deep_effort(
            score=0.72, signals={"deep": 2}, query="refactor audit module", word_count=3,
        ) == "high"

    def test_score_over_80_is_high(self):
        assert compute_deep_effort(
            score=0.82, signals={"deep": 1}, query="refactor this module", word_count=4,
        ) == "high"

    def test_two_files_plus_deep_is_high(self):
        assert compute_deep_effort(
            score=0.70,
            signals={"deep": 1},
            query="update auth.py and login.py",
            word_count=5,
        ) == "high"

    def test_two_code_blocks_plus_deep_is_high(self):
        query = "refactor this:\n```\nfoo\n```\nand this:\n```\nbar\n```"
        assert compute_deep_effort(
            score=0.70, signals={"deep": 1}, query=query, word_count=8,
        ) == "high"

    def test_architecture_keyword_en_is_xhigh(self):
        assert compute_deep_effort(
            score=0.70,
            signals={"deep": 1},
            query="design the authentication architecture",
            word_count=5,
        ) == "xhigh"

    def test_architecture_keyword_es_is_xhigh(self):
        assert compute_deep_effort(
            score=0.70,
            signals={"deep": 1},
            query="diseña la arquitectura del sistema de pagos",
            word_count=7,
            language="es",
        ) == "xhigh"

    def test_system_design_is_xhigh(self):
        assert compute_deep_effort(
            score=0.70,
            signals={"orchestration": 1},
            query="new system design for caching layer",
            word_count=7,
        ) == "xhigh"

    def test_major_refactor_is_xhigh(self):
        assert compute_deep_effort(
            score=0.72,
            signals={"deep": 1},
            query="plan a major refactor across services",
            word_count=7,
        ) == "xhigh"

    def test_redesign_spanish_is_xhigh(self):
        assert compute_deep_effort(
            score=0.70,
            signals={"deep": 1},
            query="rediseño completo del módulo de auth",
            word_count=6,
            language="es",
        ) == "xhigh"

    def test_migration_strategy_is_xhigh(self):
        assert compute_deep_effort(
            score=0.72,
            signals={"deep": 1},
            query="define migration strategy for legacy DB",
            word_count=6,
        ) == "xhigh"

    def test_orchestration_plus_deep_plus_three_files_is_xhigh(self):
        assert compute_deep_effort(
            score=0.75,
            signals={"deep": 1, "orchestration": 1},
            query="refactor auth.py login.py session.py together",
            word_count=6,
        ) == "xhigh"

    def test_score_over_85_with_long_prompt_is_xhigh(self):
        long_query = " ".join(["refactor"] * 85)
        assert compute_deep_effort(
            score=0.88, signals={"deep": 1}, query=long_query, word_count=85,
        ) == "xhigh"

    def test_score_over_85_but_short_prompt_not_xhigh(self):
        result = compute_deep_effort(
            score=0.88, signals={"deep": 1}, query="fix bug", word_count=2,
        )
        assert result == "high"

    def test_handles_missing_signals(self):
        assert compute_deep_effort(
            score=0.65, signals={}, query="fix", word_count=1,
        ) == "medium"

    def test_handles_non_dict_signals(self):
        assert compute_deep_effort(
            score=0.65, signals=None, query="fix", word_count=1,
        ) == "medium"

    def test_handles_non_string_query(self):
        assert compute_deep_effort(
            score=0.65, signals={"deep": 1}, query=None, word_count=0,
        ) == "medium"


class TestNormalizeForEnv:
    """normalize_effort_for_env maps display labels to CC-valid values."""

    def test_xhigh_normalizes_to_high(self):
        assert normalize_effort_for_env("xhigh") == "high"

    def test_high_stays_high(self):
        assert normalize_effort_for_env("high") == "high"

    def test_medium_stays_medium(self):
        assert normalize_effort_for_env("medium") == "medium"

    def test_low_stays_low(self):
        assert normalize_effort_for_env("low") == "low"

    def test_unknown_falls_back_to_medium(self):
        assert normalize_effort_for_env("ultra") == "medium"


class TestRequiresAdvisor:
    """requires_advisor flags xhigh as the Advisor trigger."""

    def test_xhigh_requires_advisor(self):
        assert requires_advisor("xhigh") is True

    def test_high_does_not(self):
        assert requires_advisor("high") is False

    def test_medium_does_not(self):
        assert requires_advisor("medium") is False

    def test_low_does_not(self):
        assert requires_advisor("low") is False


class TestArchPromotion:
    """maybe_promote_to_deep_xhigh lifts standard → deep when arch keyword
    co-occurs with at least one standard/tool/orch signal."""

    def test_major_refactor_promotes_standard(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"standard": 2},
            "plan a major refactor across all our microservices",
        )
        assert tier == "deep"
        assert promoted is True

    def test_architecture_en_promotes(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"standard": 1},
            "rework the system architecture for scaling",
        )
        assert tier == "deep"
        assert promoted is True

    def test_redesign_conjugation_es_promotes(self):
        # "rediseña" is a verb form not matched by the old regex.
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"standard": 1},
            "rediseña el módulo de pagos",
            language="es",
        )
        assert tier == "deep"
        assert promoted is True

    def test_migration_strategy_promotes(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"tool_intensive": 1},
            "define migration strategy for the database",
        )
        assert tier == "deep"
        assert promoted is True

    def test_arch_keyword_without_signals_does_not_promote(self):
        # Guard: avoid false positives on questions like "what is architecture?"
        tier, promoted = maybe_promote_to_deep_xhigh(
            "fast",
            {},
            "what is software architecture",
        )
        assert tier == "fast"
        assert promoted is False

    def test_signals_without_arch_keyword_does_not_promote(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"standard": 3},
            "refactor the login function",
        )
        assert tier == "standard"
        assert promoted is False

    def test_already_deep_never_promotes(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "deep",
            {"deep": 1, "standard": 1},
            "redesign the payments architecture",
        )
        assert tier == "deep"
        assert promoted is False

    def test_handles_non_dict_signals(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard", None, "major refactor across services",
        )
        assert tier == "standard"
        assert promoted is False

    def test_handles_non_string_query(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard", {"standard": 1}, None,
        )
        assert tier == "standard"
        assert promoted is False


# ---------------------------------------------------------------------------
# v1.6 Feature #6: Language-aware arch patterns (DE / FR / PT xhigh)
# ---------------------------------------------------------------------------

class TestLanguageAwareArchPatterns:
    """_load_arch_re loads language-specific patterns; unknown falls back to EN."""

    def test_de_kritischer_refactor_xhigh(self):
        result = compute_deep_effort(
            score=0.72,
            signals={"deep": 1},
            query="kritischer Refactor der Architektur über mehrere Dienste",
            word_count=8,
            language="de",
        )
        assert result == "xhigh"

    def test_fr_refonte_architecture_distribuee_xhigh(self):
        result = compute_deep_effort(
            score=0.72,
            signals={"deep": 1},
            query="refonte majeure de l'architecture distribuée",
            word_count=7,
            language="fr",
        )
        assert result == "xhigh"

    def test_pt_redesenho_arquitetura_xhigh(self):
        result = compute_deep_effort(
            score=0.72,
            signals={"deep": 1},
            query="redesenho crítico da arquitetura do sistema",
            word_count=7,
            language="pt",
        )
        assert result == "xhigh"

    def test_de_microservices_orch_xhigh(self):
        result = compute_deep_effort(
            score=0.72,
            signals={"orchestration": 1},
            query="plane die Migration von Monolith zu Microservices Schritt für Schritt",
            word_count=10,
            language="de",
        )
        assert result == "xhigh"

    def test_fr_contexte_borne_xhigh(self):
        result = compute_deep_effort(
            score=0.72,
            signals={"deep": 1},
            query="conception d'un contexte borné pour le service de paiement",
            word_count=10,
            language="fr",
        )
        assert result == "xhigh"

    def test_pt_microsservicos_xhigh(self):
        result = compute_deep_effort(
            score=0.72,
            signals={"deep": 1},
            query="estratégia de migração para microsserviços com zero-downtime",
            word_count=8,
            language="pt",
        )
        assert result == "xhigh"

    def test_unknown_language_falls_back_to_en(self):
        # "xx" has no language file; EN fallback should still match "architecture"
        result = compute_deep_effort(
            score=0.72,
            signals={"deep": 1},
            query="design the authentication architecture",
            word_count=5,
            language="xx",
        )
        assert result == "xhigh"

    def test_de_promote_to_deep_xhigh(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"standard": 1},
            "kritischer Refactor der Architektur über mehrere Dienste",
            language="de",
        )
        assert tier == "deep"
        assert promoted is True

    def test_fr_promote_to_deep_xhigh(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"standard": 1},
            "refonte majeure de l'architecture distribuée",
            language="fr",
        )
        assert tier == "deep"
        assert promoted is True

    def test_pt_promote_to_deep_xhigh(self):
        tier, promoted = maybe_promote_to_deep_xhigh(
            "standard",
            {"standard": 1},
            "redesenho crítico da arquitetura do sistema",
            language="pt",
        )
        assert tier == "deep"
        assert promoted is True

    def test_existing_en_xhigh_still_works(self):
        result = compute_deep_effort(
            score=0.70,
            signals={"deep": 1},
            query="design the authentication architecture",
            word_count=5,
            language="en",
        )
        assert result == "xhigh"

    def test_existing_es_xhigh_still_works(self):
        result = compute_deep_effort(
            score=0.70,
            signals={"deep": 1},
            query="diseña la arquitectura del sistema de pagos",
            word_count=7,
            language="es",
        )
        assert result == "xhigh"


# ---------------------------------------------------------------------------
# v1.6 Feature #5: Multi-file refactor promotion
# ---------------------------------------------------------------------------

from lib.effort import maybe_promote_multifile_refactor


class TestMaybePromoteMultifileRefactor:
    """maybe_promote_multifile_refactor: verb + files/qualifier → True."""

    def test_two_files_promotes(self):
        assert maybe_promote_multifile_refactor(
            "refactor auth.py and login.py to share the session logic",
            "standard",
        ) is True

    def test_qualifier_promotes(self):
        assert maybe_promote_multifile_refactor(
            "restructure these three files to use the new interface",
            "standard",
        ) is True

    def test_word_count_floor_rewrite_two_files(self):
        # 3 words → below the 6-word floor
        assert maybe_promote_multifile_refactor(
            "rewrite a.py b.py",
            "standard",
        ) is False

    def test_single_file_no_qualifier(self):
        assert maybe_promote_multifile_refactor(
            "refactor auth.py",
            "standard",
        ) is False

    def test_six_words_single_file_no_qualifier(self):
        assert maybe_promote_multifile_refactor(
            "refactor the formatDate helper in utils.py",
            "standard",
        ) is False

    def test_es_three_files_promotes(self):
        assert maybe_promote_multifile_refactor(
            "refactoriza auth.py login.py session.py para compartir lógica",
            "standard",
        ) is True

    def test_de_qualifier_promotes(self):
        assert maybe_promote_multifile_refactor(
            "Refactor quer durch mehrere Dateien der Zahlungspipeline",
            "standard",
        ) is True

    def test_fr_qualifier_promotes(self):
        assert maybe_promote_multifile_refactor(
            "Refactoriser à travers plusieurs fichiers du service de paiement",
            "standard",
        ) is True

    def test_non_standard_tier_not_promoted(self):
        # Already deep — should not touch it
        assert maybe_promote_multifile_refactor(
            "refactor auth.py and login.py to share the session logic",
            "deep",
        ) is False

    def test_fast_tier_not_promoted(self):
        assert maybe_promote_multifile_refactor(
            "refactor auth.py and login.py to share the session logic",
            "fast",
        ) is False

    def test_no_refactor_verb_not_promoted(self):
        assert maybe_promote_multifile_refactor(
            "update auth.py and login.py to share the session logic",
            "standard",
        ) is False

    # --- Interaction: arch wins over multifile ---
    def test_arch_keyword_wins_over_multifile(self):
        """A prompt matching _ARCH_RE should be handled by arch promotion.
        maybe_promote_multifile_refactor alone returns True here, but in the
        pipeline arch check fires first and multifile is gated on not arch_promoted.
        We just verify multifile function itself returns True; wiring test is
        in the pipeline (classify-prompt integration).
        """
        # "architecture" present + 2 files: multifile func still returns True
        # but in pipeline arch_promoted fires first
        assert maybe_promote_multifile_refactor(
            "refactor auth.py login.py to align with the new architecture design",
            "standard",
        ) is True
