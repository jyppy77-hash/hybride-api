"""
Tests unitaires pour engine/models.py et config/engine.py (EngineConfig).
Verifie les modeles Pydantic et les poids de configuration.
"""

import pytest
from pydantic import ValidationError

from engine.models import GenerateRequest
from config.engine import LOTO_CONFIG, EM_CONFIG


# ═══════════════════════════════════════════════════════════════════════
# GenerateRequest
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateRequest:

    def test_defaults(self):
        """Valeurs par defaut : n=5, mode='balanced'."""
        req = GenerateRequest()
        assert req.n == 5
        assert req.mode == "balanced"

    def test_custom_values(self):
        """Valeurs personnalisees acceptees."""
        req = GenerateRequest(n=10, mode="balanced")
        assert req.n == 10
        assert req.mode == "balanced"

    def test_invalid_n_type(self):
        """n non-entier → ValidationError."""
        with pytest.raises(ValidationError):
            GenerateRequest(n="abc")

    # V56 — F09: aligned limit n=10 (was 20)
    def test_n_too_large(self):
        """n > 10 → ValidationError."""
        with pytest.raises(ValidationError):
            GenerateRequest(n=100)

    def test_n_11_rejected(self):
        """n = 11 → ValidationError (aligned with API le=10)."""
        with pytest.raises(ValidationError):
            GenerateRequest(n=11)

    def test_n_10_accepted(self):
        """n = 10 → accepted (max limit)."""
        req = GenerateRequest(n=10)
        assert req.n == 10

    def test_n_zero(self):
        """n = 0 → ValidationError."""
        with pytest.raises(ValidationError):
            GenerateRequest(n=0)

    def test_n_negative(self):
        """n < 0 → ValidationError."""
        with pytest.raises(ValidationError):
            GenerateRequest(n=-1)

    def test_invalid_mode(self):
        """mode='xyz' → ValidationError."""
        with pytest.raises(ValidationError):
            GenerateRequest(mode="xyz")

    def test_all_valid_modes(self):
        """All 3 valid modes accepted."""
        for m in ("conservative", "balanced", "recent"):
            req = GenerateRequest(mode=m)
            assert req.mode == m


# ═══════════════════════════════════════════════════════════════════════
# EngineConfig scoring weights (replaces legacy CONFIG dict)
# ═══════════════════════════════════════════════════════════════════════

class TestScoringWeights:

    def test_coef_frequence_retard_sum_to_one(self):
        """poids_frequence + poids_retard = 1.0 for both configs."""
        for cfg in (LOTO_CONFIG, EM_CONFIG):
            assert pytest.approx(cfg.poids_frequence + cfg.poids_retard) == 1.0

    def test_mode_weights_sum_to_one(self):
        """All 3-window mode weights sum to 1.0."""
        for cfg in (LOTO_CONFIG, EM_CONFIG):
            for mode, weights in cfg.modes.items():
                assert pytest.approx(sum(weights)) == 1.0, f"{cfg.game} {mode}"

    def test_fenetre_positive(self):
        """Window durations are positive."""
        for cfg in (LOTO_CONFIG, EM_CONFIG):
            assert cfg.fenetre_principale_annees > 0
            assert cfg.fenetre_recente_annees > 0

    def test_weights_positive(self):
        """Scoring weights are positive."""
        for cfg in (LOTO_CONFIG, EM_CONFIG):
            assert cfg.poids_frequence > 0
            assert cfg.poids_retard > 0
