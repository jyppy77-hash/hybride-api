"""
Tests unitaires pour services/chat_utils_em.py.
Couvre le formatage contexte EM (tirage, stats, grille, complexe, session).
"""

from types import SimpleNamespace

from services.chat_utils_em import (
    FALLBACK_RESPONSE_EM,
    _format_tirage_context_em,
    _format_stats_context_em,
    _format_grille_context_em,
    _format_complex_context_em,
    _build_session_context_em,
)


def _msg(role, content):
    return SimpleNamespace(role=role, content=content)


# ═══════════════════════════════════════════════════════════════════════
# _format_tirage_context_em
# ═══════════════════════════════════════════════════════════════════════

class TestFormatTirageContextEM:

    def test_format_normal(self):
        tirage = {
            "date": "2026-02-20",
            "boules": [3, 17, 28, 35, 44],
            "etoiles": [5, 11],
        }
        result = _format_tirage_context_em(tirage)
        assert "RÉSULTAT TIRAGE" in result
        assert "20 février 2026" in result
        assert "3 - 17 - 28 - 35 - 44" in result
        assert "5 - 11" in result
        assert "Étoiles" in result

    def test_format_includes_date(self):
        tirage = {"date": "2025-12-25", "boules": [1, 2, 3, 4, 5], "etoiles": [1, 2]}
        result = _format_tirage_context_em(tirage)
        assert "25 décembre 2025" in result


# ═══════════════════════════════════════════════════════════════════════
# _format_stats_context_em
# ═══════════════════════════════════════════════════════════════════════

class TestFormatStatsContextEM:

    def test_boule_stats(self):
        stats = {
            "type": "boule",
            "numero": 23,
            "categorie": "chaud",
            "frequence_totale": 95,
            "total_tirages": 500,
            "pourcentage_apparition": "19.0%",
            "derniere_sortie": "2026-02-14",
            "ecart_actuel": 3,
            "ecart_moyen": 10,
            "classement": 5,
            "classement_sur": 50,
            "periode": "2019-11-04 au 2026-02-14",
        }
        result = _format_stats_context_em(stats)
        assert "boule" in result
        assert "23" in result
        assert "CHAUD" in result
        assert "50" in result

    def test_etoile_stats(self):
        stats = {
            "type": "etoile",
            "numero": 7,
            "categorie": "froid",
            "frequence_totale": 40,
            "total_tirages": 500,
            "pourcentage_apparition": "8.0%",
            "derniere_sortie": "2026-01-10",
            "ecart_actuel": 15,
            "ecart_moyen": 12,
            "classement": 10,
            "classement_sur": 12,
            "periode": "2019-11-04 au 2026-01-10",
        }
        result = _format_stats_context_em(stats)
        assert "étoile" in result
        assert "7" in result
        assert "FROID" in result


# ═══════════════════════════════════════════════════════════════════════
# _format_grille_context_em
# ═══════════════════════════════════════════════════════════════════════

class TestFormatGrilleContextEM:

    def _make_grille_result(self, etoiles=None, deja_sortie=False):
        return {
            "numeros": [5, 15, 25, 35, 45],
            "etoiles": etoiles,
            "analyse": {
                "somme": 125,
                "somme_ok": True,
                "pairs": 2,
                "impairs": 3,
                "equilibre_pair_impair": True,
                "bas": 2,
                "hauts": 3,
                "equilibre_bas_haut": True,
                "dispersion": 40,
                "dispersion_ok": True,
                "consecutifs": 0,
                "numeros_chauds": [15, 25],
                "numeros_froids": [45],
                "numeros_neutres": [5, 35],
                "conformite_pct": 85,
                "badges": ["Equilibree", "Dispersee"],
            },
            "historique": {
                "deja_sortie": deja_sortie,
                "exact_dates": ["2025-01-01"] if deja_sortie else [],
                "meilleure_correspondance": {
                    "nb_numeros_communs": 3 if not deja_sortie else 5,
                    "numeros_communs": [5, 15, 25],
                    "etoiles_match": False,
                    "date": "2024-06-15",
                },
            },
        }

    def test_basic_grille(self):
        result = _format_grille_context_em(self._make_grille_result())
        assert "ANALYSE DE GRILLE" in result
        assert "5 15 25 35 45" in result
        assert "Somme : 125" in result
        assert "Conformité : 85%" in result

    def test_with_etoiles(self):
        result = _format_grille_context_em(self._make_grille_result(etoiles=[3, 9]))
        assert "étoiles: 3 9" in result

    def test_deja_sortie(self):
        result = _format_grille_context_em(self._make_grille_result(deja_sortie=True))
        assert "déjà sortie" in result


# ═══════════════════════════════════════════════════════════════════════
# _format_complex_context_em
# ═══════════════════════════════════════════════════════════════════════

class TestFormatComplexContextEM:

    def test_classement(self):
        intent = {"type": "classement", "tri": "frequence_desc", "limit": 3, "num_type": "boule"}
        data = {
            "items": [
                {"numero": 7, "frequence": 95, "ecart_actuel": 3, "categorie": "chaud"},
                {"numero": 23, "frequence": 90, "ecart_actuel": 5, "categorie": "chaud"},
                {"numero": 14, "frequence": 88, "ecart_actuel": 7, "categorie": "neutre"},
            ],
            "total_tirages": 500,
            "periode": "2019-11-04 au 2026-02-14",
        }
        result = _format_complex_context_em(intent, data)
        assert "CLASSEMENT" in result
        assert "boules" in result
        assert "Numéro 7" in result

    def test_comparaison(self):
        intent = {"type": "comparaison"}
        data = {
            "num1": {"numero": 7, "frequence_totale": 95, "pourcentage_apparition": "19%", "ecart_actuel": 3, "categorie": "chaud"},
            "num2": {"numero": 23, "frequence_totale": 90, "pourcentage_apparition": "18%", "ecart_actuel": 5, "categorie": "neutre"},
            "diff_frequence": 5,
            "favori_frequence": 7,
        }
        result = _format_complex_context_em(intent, data)
        assert "COMPARAISON" in result
        assert "7" in result
        assert "23" in result

    def test_categorie(self):
        intent = {"type": "categorie"}
        data = {
            "categorie": "chaud",
            "count": 3,
            "numeros": [{"numero": 7}, {"numero": 23}, {"numero": 14}],
            "periode_analyse": "2 dernières années",
        }
        result = _format_complex_context_em(intent, data)
        assert "CHAUDS" in result
        assert "7" in result


# ═══════════════════════════════════════════════════════════════════════
# _build_session_context_em
# ═══════════════════════════════════════════════════════════════════════

class TestBuildSessionContextEM:

    def test_empty_history(self):
        result = _build_session_context_em([], "bonjour")
        assert result == ""

    def test_short_session_no_context(self):
        """Moins de 2 sujets → pas de contexte."""
        history = [_msg("user", "le 7?")]
        result = _build_session_context_em(history, "bonjour")
        assert result == ""

    def test_multi_numeros(self):
        """2 numeros consultes → contexte session."""
        history = [_msg("user", "le numéro 7")]
        result = _build_session_context_em(history, "le numéro 23")
        assert "[SESSION]" in result
        assert "7" in result
        assert "23" in result


# ═══════════════════════════════════════════════════════════════════════
# FALLBACK_RESPONSE_EM
# ═══════════════════════════════════════════════════════════════════════

class TestFallbackEM:

    def test_fallback_not_empty(self):
        assert len(FALLBACK_RESPONSE_EM) > 10
        assert "indisponible" in FALLBACK_RESPONSE_EM
