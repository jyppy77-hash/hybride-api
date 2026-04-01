"""
Tests for base_chat_utils shared functions — V71 R3b.
"""

from types import SimpleNamespace

from services.base_chat_utils import (
    _format_stats_context_base,
    _format_grille_context_base,
    _build_session_context_base,
)


_SAMPLE_STATS = {
    "numero": 7, "type": "principal",
    "frequence_totale": 45, "total_tirages": 980,
    "pourcentage_apparition": "4.6%",
    "derniere_sortie": "2026-03-15",
    "ecart_actuel": 3, "ecart_moyen": 22,
    "classement": 12, "categorie": "chaud",
    "periode": "2019-11-04 au 2026-03-15",
}

_SAMPLE_GRILLE = {
    "numeros": [5, 15, 25, 35, 45], "chance": 3,
    "analyse": {
        "somme": 125, "somme_ok": True,
        "pairs": 2, "impairs": 3, "equilibre_pair_impair": True,
        "bas": 2, "hauts": 3, "equilibre_bas_haut": True,
        "dispersion": 40, "dispersion_ok": True,
        "consecutifs": 0,
        "numeros_chauds": [15], "numeros_froids": [45],
        "numeros_neutres": [5, 25, 35],
        "conformite_pct": 82,
        "badges": ["Equilibre"],
    },
    "historique": {
        "deja_sortie": False,
        "exact_dates": [],
        "meilleure_correspondance": {
            "nb_numeros_communs": 2,
            "numeros_communs": [15, 35],
            "date": "2025-01-01",
            "chance_match": False,
        },
    },
}


class TestFormatStatsBase:
    def test_loto_type_label(self):
        result = _format_stats_context_base(_SAMPLE_STATS, {"principal": "principal"}, 49)
        assert "Numéro principal 7" in result
        assert "sur 49" in result

    def test_em_type_label(self):
        stats = {**_SAMPLE_STATS, "type": "boule"}
        result = _format_stats_context_base(stats, {"boule": "boule", "etoile": "étoile"}, 50)
        assert "Numéro boule 7" in result
        assert "sur 50" in result


class TestFormatGrilleBase:
    def test_loto_ranges(self):
        result = _format_grille_context_base(
            _SAMPLE_GRILLE, "chance", "chance",
            "100-140", 24, "25-49",
        )
        assert "idéal : 100-140" in result
        assert "Bas (1-24)" in result
        assert "Hauts (25-49)" in result
        assert "(chance: 3)" in result

    def test_em_ranges(self):
        grille = {**_SAMPLE_GRILLE, "etoiles": [2, 7]}
        grille.pop("chance", None)
        result = _format_grille_context_base(
            grille, "etoiles", "étoiles",
            "95-160", 25, "26-50",
            match_key="etoiles_match", match_label=" + étoile(s)",
        )
        assert "idéal : 95-160" in result
        assert "Bas (1-25)" in result
        assert "Hauts (26-50)" in result
        assert "(étoiles: 2 7)" in result


class TestBuildSessionBase:
    def test_empty_returns_empty(self):
        result = _build_session_context_base(
            [], "hello",
            detect_numero_fn=lambda m: (None, None),
            detect_tirage_fn=lambda m: None,
            type_label_fn=lambda t: t,
        )
        assert result == ""

    def test_with_numeros(self):
        history = [
            SimpleNamespace(role="user", content="le 7"),
            SimpleNamespace(role="assistant", content="ok"),
        ]
        call_count = [0]

        def fake_detect(msg):
            call_count[0] += 1
            if "7" in msg:
                return (7, "principal")
            if "12" in msg:
                return (12, "principal")
            return (None, None)

        result = _build_session_context_base(
            history, "et le 12",
            detect_numero_fn=fake_detect,
            detect_tirage_fn=lambda m: None,
            type_label_fn=lambda t: t,
        )
        assert "[SESSION]" in result
        assert "7 (principal)" in result
        assert "12 (principal)" in result
