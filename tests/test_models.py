"""
Tests unitaires pour engine/models.py et engine/hybride.CONFIG
Verifie les modeles Pydantic et les poids de configuration.
"""

import pytest
from pydantic import ValidationError

from engine.models import GenerateRequest, Ticket
from engine.hybride import CONFIG


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


# ═══════════════════════════════════════════════════════════════════════
# Ticket
# ═══════════════════════════════════════════════════════════════════════

class TestTicket:

    def test_valid_ticket(self):
        """Ticket valide avec tous les champs."""
        t = Ticket(nums=[1, 12, 23, 34, 45], chance=7, score=85, badges=["Hybride V1"])
        assert t.nums == [1, 12, 23, 34, 45]
        assert t.chance == 7
        assert t.score == 85
        assert t.badges == ["Hybride V1"]

    def test_missing_field(self):
        """Champ manquant → ValidationError."""
        with pytest.raises(ValidationError):
            Ticket(nums=[1, 2, 3, 4, 5], chance=1)


# ═══════════════════════════════════════════════════════════════════════
# CONFIG (poids du modele hybride)
# ═══════════════════════════════════════════════════════════════════════

class TestScoringWeights:

    EXPECTED_KEYS = {
        "fenetre_principale_annees",
        "fenetre_recente_annees",
        "poids_principal",
        "poids_recent",
        "coef_frequence",
        "coef_retard",
    }

    def test_all_keys_present(self):
        """Toutes les cles attendues existent dans CONFIG."""
        assert self.EXPECTED_KEYS.issubset(set(CONFIG.keys()))

    def test_weights_are_numbers(self):
        """Chaque poids est un int ou float."""
        for key in self.EXPECTED_KEYS:
            assert isinstance(CONFIG[key], (int, float)), f"{key} n'est pas un nombre"

    def test_weights_positive(self):
        """Chaque poids est strictement positif."""
        for key in self.EXPECTED_KEYS:
            assert CONFIG[key] > 0, f"{key} <= 0"

    def test_poids_sum_to_one(self):
        """poids_principal + poids_recent = 1.0."""
        assert pytest.approx(CONFIG["poids_principal"] + CONFIG["poids_recent"]) == 1.0

    def test_coef_sum_to_one(self):
        """coef_frequence + coef_retard = 1.0."""
        assert pytest.approx(CONFIG["coef_frequence"] + CONFIG["coef_retard"]) == 1.0
