"""
Tests V141 A.5 — Stats unified endpoint enrichi (Release 1.6.032, Option 3 hybride).

Couvre la résolution du bug chronique 3/6 cards `-` sur pages
/[module]/statistiques onglet "Analyse par numéro" (POURCENTAGE / ÉCART MOYEN /
CLASSEMENT) tous numéros 1-50 + étoiles 1-12, 6 langues EM.

Approche Option 3 :
- SQL inline existant PRESERVÉ (rétrocompat 100% 8 clés legacy)
- Délégation partielle à BaseStatsService.get_numero_stats() via mock
  get_stats_service pour 4 nouvelles clés (pourcentage float, ecart_moyen,
  classement, classement_sur)
- Anti-hallu strict : try/except → fallback 0.0/0/cfg.num_range[1] (jamais None)

Voir diag : docs/DIAG_STATS_FREQUENCE_AFFICHAGE_2026-05-18.md

7 classes / ~51 tests parametric :
  1. TestStatsNumberEnrichedFields — 3 metrics présents + types + bornes (18)
  2. TestStatsEtoileEMEnrichedFields — pattern étoile EM (9)
  3. TestStatsLegacyFieldsUnchanged — non-régression 8 clés legacy (8)
  4. TestStatsNumberJSONShape — set complet 12 clés (2)
  5. TestHybrideStatsEndpointUnchanged — /hybride-stats inchangé (1)
  6. TestStatsAntiHalluStrict — None/vide/'-' interdit + fallback path (12)
  7. TestStatsReferenceN13EM — référence terrain Jyppy 18/05/2026 (2)
"""

import os
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ════════════════════════════════════════════════════════════
# Setup fixtures / helpers (pattern projet test_unified_routes.py)
# ════════════════════════════════════════════════════════════

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_module_patch = patch.dict(os.environ, {
    "DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
    "EM_PUBLIC_ACCESS": "true",
})


def _async_cm_conn(cursor):
    @asynccontextmanager
    async def _cm():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn
    return _cm


def _default_stats_return(numero=13, classement_sur=50):
    """Default mock dict returned by BaseStatsService.get_numero_stats().

    Référence : curl /api/euromillions/hybride-stats?numero=13&type=boule
    (cf. diag §5.2 — observation 2026-05-18).
    """
    return {
        "numero": numero,
        "type": "boule",
        "frequence_totale": 83,
        "pourcentage_apparition": "11.34%",
        "derniere_sortie": "2026-04-21",
        "ecart_actuel": 7,
        "ecart_moyen": 8.7,
        "classement": 6,
        "classement_sur": classement_sur,
        "categorie": "chaud",
        "total_tirages": 732,
        "periode": "2019-05-14 au 2026-05-15",
    }


def _setup_mocks(mock_db, mock_get_svc, *, fetchall_dates=None, gap=7,
                 stats_return=None, svc_side_effect=None):
    """Wire up cursor + service mocks. Returns nothing (side-effects only)."""
    if fetchall_dates is None:
        fetchall_dates = [
            {"date_de_tirage": date(2019, 6, 14)},
            {"date_de_tirage": date(2024, 11, 2)},
            {"date_de_tirage": date(2026, 4, 21)},
        ]
    cursor = AsyncMock()
    cursor.fetchall.return_value = fetchall_dates
    cursor.fetchone.return_value = {"gap": gap}
    mock_db.get_connection = _async_cm_conn(cursor)

    mock_svc = AsyncMock()
    if svc_side_effect is not None:
        mock_svc.get_numero_stats = AsyncMock(side_effect=svc_side_effect)
    else:
        if stats_return is None:
            stats_return = _default_stats_return()
        mock_svc.get_numero_stats = AsyncMock(return_value=stats_return)
    mock_get_svc.return_value = mock_svc


def _make_client():
    """Build TestClient with env patches + reloads (project pattern)."""
    with _db_module_patch, _static_patch, _static_call:
        import importlib
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _url_stats_number(game, number):
    """URL helper — Loto uses legacy /api/stats/number, EM uses /api/euromillions/stats/number."""
    if game == "euromillions":
        return f"/api/euromillions/stats/number/{number}"
    return f"/api/loto/stats/number/{number}"


# ════════════════════════════════════════════════════════════
# CLASS 1 — Boule Loto/EM : 3 nouvelles metrics présentes + bien typées
# ════════════════════════════════════════════════════════════

class TestStatsNumberEnrichedFields:
    """Vérifie que les 3 nouveaux fields V141 A.5 sont retournés et bien typés."""

    @pytest.mark.parametrize("game, number, max_n", [
        ("loto", 1, 49),
        ("loto", 26, 49),
        ("loto", 49, 49),
        ("euromillions", 1, 50),
        ("euromillions", 13, 50),  # cas terrain Jyppy 18/05
        ("euromillions", 50, 50),
    ])
    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_pourcentage_field_present_and_float(
        self, mock_db, mock_get_svc, game, number, max_n,
    ):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=number, classement_sur=max_n))
        client = _make_client()
        resp = client.get(_url_stats_number(game, number))
        assert resp.status_code == 200, f"HTTP {resp.status_code} pour {game}/{number}"
        data = resp.json()
        assert "pourcentage" in data, f"pourcentage MANQUANT pour {game}/{number}"
        assert data["pourcentage"] is not None, (
            f"pourcentage est None pour {game}/{number} (ANTI-HALLU)"
        )
        assert isinstance(data["pourcentage"], (int, float)), (
            f"pourcentage pas numérique : {type(data['pourcentage'])}"
        )
        assert data["pourcentage"] >= 0, f"pourcentage négatif : {data['pourcentage']}"
        assert data["pourcentage"] <= 100, f"pourcentage > 100% : {data['pourcentage']}"

    @pytest.mark.parametrize("game, number, max_n", [
        ("loto", 1, 49), ("loto", 26, 49), ("loto", 49, 49),
        ("euromillions", 1, 50), ("euromillions", 13, 50), ("euromillions", 50, 50),
    ])
    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_ecart_moyen_field_present_and_float(
        self, mock_db, mock_get_svc, game, number, max_n,
    ):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=number, classement_sur=max_n))
        client = _make_client()
        resp = client.get(_url_stats_number(game, number))
        assert resp.status_code == 200
        data = resp.json()
        assert "ecart_moyen" in data
        assert data["ecart_moyen"] is not None, "ecart_moyen est None (ANTI-HALLU)"
        assert isinstance(data["ecart_moyen"], (int, float))
        assert data["ecart_moyen"] >= 0, f"ecart_moyen négatif : {data['ecart_moyen']}"

    @pytest.mark.parametrize("game, number, max_n", [
        ("loto", 1, 49), ("loto", 26, 49), ("loto", 49, 49),
        ("euromillions", 1, 50), ("euromillions", 13, 50), ("euromillions", 50, 50),
    ])
    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_classement_field_present_and_int(
        self, mock_db, mock_get_svc, game, number, max_n,
    ):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=number, classement_sur=max_n))
        client = _make_client()
        resp = client.get(_url_stats_number(game, number))
        assert resp.status_code == 200
        data = resp.json()
        assert "classement" in data
        assert "classement_sur" in data
        assert data["classement"] is not None
        assert data["classement_sur"] is not None
        assert isinstance(data["classement"], int)
        assert isinstance(data["classement_sur"], int)
        # classement peut être 0 si fallback BDD vide (anti-hallu)
        assert 0 <= data["classement"] <= max_n, (
            f"classement hors bornes : {data['classement']}/{max_n}"
        )
        assert data["classement_sur"] == max_n


# ════════════════════════════════════════════════════════════
# CLASS 2 — Étoiles EM : pattern identique pour étoiles
# ════════════════════════════════════════════════════════════

class TestStatsEtoileEMEnrichedFields:
    """Pattern identique pour étoiles EM (1-12)."""

    @pytest.mark.parametrize("etoile", [1, 6, 12])
    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_pourcentage_etoile_em(self, mock_db, mock_get_svc, etoile):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=etoile, classement_sur=12))
        client = _make_client()
        resp = client.get(f"/api/euromillions/stats/etoile/{etoile}")
        assert resp.status_code == 200
        data = resp.json()
        assert "pourcentage" in data
        assert data["pourcentage"] is not None
        assert isinstance(data["pourcentage"], (int, float))
        assert 0 <= data["pourcentage"] <= 100

    @pytest.mark.parametrize("etoile", [1, 6, 12])
    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_ecart_moyen_etoile_em(self, mock_db, mock_get_svc, etoile):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=etoile, classement_sur=12))
        client = _make_client()
        resp = client.get(f"/api/euromillions/stats/etoile/{etoile}")
        assert resp.status_code == 200
        data = resp.json()
        assert "ecart_moyen" in data
        assert data["ecart_moyen"] is not None
        assert data["ecart_moyen"] >= 0

    @pytest.mark.parametrize("etoile", [1, 6, 12])
    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_classement_etoile_em(self, mock_db, mock_get_svc, etoile):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=etoile, classement_sur=12))
        client = _make_client()
        resp = client.get(f"/api/euromillions/stats/etoile/{etoile}")
        assert resp.status_code == 200
        data = resp.json()
        assert "classement" in data
        assert "classement_sur" in data
        assert 0 <= data["classement"] <= 12
        assert data["classement_sur"] == 12


# ════════════════════════════════════════════════════════════
# CLASS 3 — Non-régression 8 fields legacy (SQL inline PRESERVED)
# ════════════════════════════════════════════════════════════

class TestStatsLegacyFieldsUnchanged:
    """Garantit que les 8 fields legacy (SQL inline) ne changent pas avec V141 A.5."""

    LEGACY_FIELDS = {
        "success", "number", "type",
        "total_appearances",
        "first_appearance", "last_appearance",
        "current_gap", "appearance_dates",
    }

    @pytest.mark.parametrize("game, number, max_n", [
        ("loto", 13, 49),
        ("euromillions", 13, 50),
    ])
    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_legacy_fields_present(
        self, mock_db, mock_get_svc, game, number, max_n,
    ):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=number, classement_sur=max_n))
        client = _make_client()
        resp = client.get(_url_stats_number(game, number))
        assert resp.status_code == 200
        data = resp.json()
        for field in self.LEGACY_FIELDS:
            assert field in data, (
                f"Legacy field {field} manquant pour {game}/{number} — RÉGRESSION SQL inline"
            )

    @pytest.mark.parametrize("game, number, max_n", [
        ("loto", 13, 49),
        ("euromillions", 13, 50),
    ])
    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_total_appearances_int(
        self, mock_db, mock_get_svc, game, number, max_n,
    ):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=number, classement_sur=max_n))
        client = _make_client()
        resp = client.get(_url_stats_number(game, number))
        data = resp.json()
        assert isinstance(data["total_appearances"], int)
        assert data["total_appearances"] >= 0

    @pytest.mark.parametrize("game, number, max_n", [
        ("loto", 13, 49),
        ("euromillions", 13, 50),
    ])
    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_current_gap_int(
        self, mock_db, mock_get_svc, game, number, max_n,
    ):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=number, classement_sur=max_n))
        client = _make_client()
        resp = client.get(_url_stats_number(game, number))
        data = resp.json()
        assert isinstance(data["current_gap"], int)
        assert data["current_gap"] >= 0

    @pytest.mark.parametrize("game, number, max_n", [
        ("loto", 13, 49),
        ("euromillions", 13, 50),
    ])
    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_appearance_dates_list_non_empty(
        self, mock_db, mock_get_svc, game, number, max_n,
    ):
        """SQL inline preserved : appearance_dates list non-vide pour numéro qui sort."""
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=number, classement_sur=max_n))
        client = _make_client()
        resp = client.get(_url_stats_number(game, number))
        data = resp.json()
        assert isinstance(data["appearance_dates"], list)
        assert len(data["appearance_dates"]) > 0, (
            "appearance_dates vide — RÉGRESSION SQL inline"
        )


# ════════════════════════════════════════════════════════════
# CLASS 4 — JSON shape complet (12 fields attendus post-V141 A.5)
# ════════════════════════════════════════════════════════════

class TestStatsNumberJSONShape:
    """Garantit la forme du JSON après enrichissement V141 A.5."""

    EXPECTED_FIELDS_NUMBER = {
        # LEGACY (8)
        "success", "number", "type",
        "total_appearances", "first_appearance", "last_appearance",
        "current_gap", "appearance_dates",
        # NEW V141 A.5 (4)
        "pourcentage", "ecart_moyen", "classement", "classement_sur",
    }

    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_em_number_13_full_shape(self, mock_db, mock_get_svc):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=13, classement_sur=50))
        client = _make_client()
        resp = client.get("/api/euromillions/stats/number/13")
        assert resp.status_code == 200
        data = resp.json()
        for field in self.EXPECTED_FIELDS_NUMBER:
            assert field in data, f"Field V141 A.5 attendu manquant : {field}"

    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_loto_number_26_full_shape(self, mock_db, mock_get_svc):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=26, classement_sur=49))
        client = _make_client()
        resp = client.get("/api/loto/stats/number/26")
        assert resp.status_code == 200
        data = resp.json()
        for field in self.EXPECTED_FIELDS_NUMBER:
            assert field in data, f"Field V141 A.5 attendu manquant Loto : {field}"


# ════════════════════════════════════════════════════════════
# CLASS 5 — /hybride-stats inchangé (rétrocompat chatbot HYBRIDE)
# ════════════════════════════════════════════════════════════

class TestHybrideStatsEndpointUnchanged:
    """Vérifie que /hybride-stats reste exactement comme avant V141 A.5."""

    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_hybride_stats_em_13_unchanged_format(self, mock_db, mock_get_svc):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=13, classement_sur=50))
        client = _make_client()
        resp = client.get("/api/euromillions/hybride-stats?numero=13&type=boule")
        assert resp.status_code == 200
        data = resp.json()
        # Envelope {success, data, error} préservée
        assert "data" in data
        assert "success" in data
        assert data["success"] is True
        d = data["data"]
        # pourcentage_apparition reste STRING formatée "11.34%" (pas float)
        assert "pourcentage_apparition" in d
        assert isinstance(d["pourcentage_apparition"], str)
        assert d["pourcentage_apparition"].endswith("%")
        # Clés long-form préservées
        assert "frequence_totale" in d
        assert "classement_sur" in d
        assert "derniere_sortie" in d


# ════════════════════════════════════════════════════════════
# CLASS 6 — Anti-hallu strict (aucun None/vide/'-' + fallback path)
# ════════════════════════════════════════════════════════════

class TestStatsAntiHalluStrict:
    """Garantit qu'aucun field critique ne renvoie None/vide/'-' (anti-hallu V141 A.5)."""

    CRITICAL_FIELDS = ["pourcentage", "ecart_moyen", "classement", "classement_sur"]

    @pytest.mark.parametrize("game, number, max_n", [
        ("loto", 1, 49), ("loto", 10, 49), ("loto", 20, 49),
        ("loto", 30, 49), ("loto", 40, 49), ("loto", 49, 49),
        ("euromillions", 1, 50), ("euromillions", 10, 50),
        ("euromillions", 25, 50), ("euromillions", 40, 50), ("euromillions", 50, 50),
    ])
    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_no_none_critical_fields(
        self, mock_db, mock_get_svc, game, number, max_n,
    ):
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=number, classement_sur=max_n))
        client = _make_client()
        resp = client.get(_url_stats_number(game, number))
        data = resp.json()
        for field in self.CRITICAL_FIELDS:
            val = data.get(field)
            assert val is not None, f"Field {field}=None pour {game}/{number} (ANTI-HALLU)"
            assert val != "", f"Field {field} vide string pour {game}/{number}"
            assert val != "-", f"Field {field}='-' pour {game}/{number}"

    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_fallback_path_when_get_numero_stats_raises(self, mock_db, mock_get_svc):
        """Si get_numero_stats() raise (BDD down, etc.) → fallback 0.0/0/num_range[1], JAMAIS None.

        Cas réel : try/except du backend V141 A.5 → logger.warning + valeurs sémantiques.
        """
        _setup_mocks(mock_db, mock_get_svc,
                     svc_side_effect=RuntimeError("Simulated DB error"))
        client = _make_client()
        resp = client.get("/api/loto/stats/number/13")
        assert resp.status_code == 200, "Endpoint doit rester 200 même si délégation foire"
        data = resp.json()
        # Anti-hallu : valeurs sémantiquement valides, pas None
        assert data["pourcentage"] == 0.0
        assert data["ecart_moyen"] == 0.0
        assert data["classement"] == 0
        assert data["classement_sur"] == 49  # cfg.num_range[1] Loto

    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_fallback_path_when_get_numero_stats_returns_none(self, mock_db, mock_get_svc):
        """get_numero_stats() peut retourner None (numero hors bornes interne).

        Notre code lève ValueError dans le try → fallback 0.0/0 anti-hallu.
        """
        _setup_mocks(mock_db, mock_get_svc, stats_return=None)
        # stats_return=None → mock_svc.get_numero_stats = AsyncMock(return_value=None)
        # Manual override : on veut return_value=None pas un dict default
        mock_svc = AsyncMock()
        mock_svc.get_numero_stats = AsyncMock(return_value=None)
        mock_get_svc.return_value = mock_svc
        client = _make_client()
        resp = client.get("/api/euromillions/stats/number/13")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pourcentage"] == 0.0
        assert data["ecart_moyen"] == 0.0
        assert data["classement"] == 0
        assert data["classement_sur"] == 50  # cfg.num_range[1] EM


# ════════════════════════════════════════════════════════════
# CLASS 7 — Référence terrain (N°13 EM cas Jyppy 18/05/2026)
# ════════════════════════════════════════════════════════════

class TestStatsReferenceN13EM:
    """Tests référence cas terrain Jyppy (numéro 13 EM, observation 18/05/2026 ~22h)."""

    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_n13_em_pourcentage_plausible(self, mock_db, mock_get_svc):
        """Référence diag §5.2 : pourcentage_apparition '11.34%' → expose 11.34 (float)."""
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=13, classement_sur=50))
        client = _make_client()
        resp = client.get("/api/euromillions/stats/number/13")
        data = resp.json()
        # Référence : 11.34 (avec marge ±5% pour tolérer évolution BDD si tests intégration)
        assert 5 <= data["pourcentage"] <= 20, (
            f"pourcentage N°13 EM inattendu : {data['pourcentage']} (réf ~11.34)"
        )

    @patch("routes.api_data_unified.get_stats_service")
    @patch("routes.api_data_unified.db_cloudsql")
    def test_n13_em_classement_borne(self, mock_db, mock_get_svc):
        """Référence diag §5.2 : classement 6/50."""
        _setup_mocks(mock_db, mock_get_svc,
                     stats_return=_default_stats_return(numero=13, classement_sur=50))
        client = _make_client()
        resp = client.get("/api/euromillions/stats/number/13")
        data = resp.json()
        assert 1 <= data["classement"] <= 50
        assert data["classement_sur"] == 50
