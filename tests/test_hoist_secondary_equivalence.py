"""Golden test levier B — équivalence BIT-IDENTIQUE du hoist scoring secondaire.

Prouve empiriquement la garantie de l'audit B (§3) : hoister le calcul de base
secondaire (1×/tirage au lieu de 100×) produit des grilles STRICTEMENT identiques
(nums ET secondary ET score), pas seulement "statistiquement proches".

Mécanique :
  - Le hoist est désormais TOUJOURS actif dans generate_grids (il passe
    scores_secondary_base à generer_grille).
  - Référence "sans hoist" = on force precomputed_scores=None dans generer_secondary
    (via wrapper patché) → recompute per-grille = ancien comportement.
  - Même seed RNG → on compare les 20 grilles 1 à 1.

Pourquoi c'est bit-identique : calculer_scores_hybrides_secondary est SQL pur sans
RNG → supprimer 99 appels redondants ne décale pas la séquence random globale →
random.choices du sampling voit un état identique. Loto ET EM.

Tests purs en mémoire (mocks DB), zéro réseau.
"""
from __future__ import annotations

import random
from unittest.mock import patch

import pytest

from config.engine import EM_CONFIG, LOTO_CONFIG
from engine.hybride_base import HybrideEngine
from tests.conftest import AsyncSmartMockCursor, make_async_conn
from tests.test_hybride_em import EMAsyncSmartMockCursor, make_em_conn


_SEED = 2026
_N = 20

# Référence originale de la méthode (version hoist-aware) — réutilisée par le
# wrapper qui force le recompute per-grille.
_ORIG_GENERER_SECONDARY = HybrideEngine.generer_secondary


async def _generer_secondary_no_hoist(self, conn, **kwargs):
    """Wrapper : force precomputed_scores=None → recompute per-grille (ancien comportement)."""
    kwargs["precomputed_scores"] = None
    return await _ORIG_GENERER_SECONDARY(self, conn, **kwargs)


def _fingerprint(grids: list[dict], secondary_name: str) -> list[tuple]:
    """Empreinte ordonnée (nums, secondary, score) pour comparaison bit-identique."""
    out = []
    for g in grids:
        sec = g.get(secondary_name)
        sec_key = tuple(sec) if isinstance(sec, list) else sec
        out.append((tuple(g["nums"]), sec_key, g["score"]))
    return out


async def _run_hoist(engine: HybrideEngine, conn_factory) -> list[dict]:
    """generate_grids avec le hoist actif (comportement par défaut)."""
    random.seed(_SEED)
    result = await engine.generate_grids(
        n=_N, mode="balanced", _get_connection=conn_factory,
    )
    return result["grids"]


async def _run_no_hoist(engine: HybrideEngine, conn_factory) -> list[dict]:
    """generate_grids avec recompute per-grille forcé (référence pré-hoist)."""
    random.seed(_SEED)
    with patch.object(HybrideEngine, "generer_secondary", _generer_secondary_no_hoist):
        result = await engine.generate_grids(
            n=_N, mode="balanced", _get_connection=conn_factory,
        )
    return result["grids"]


class TestHoistSecondaryEquivalence:

    @pytest.mark.asyncio
    async def test_loto_bit_identical(self):
        engine = HybrideEngine(LOTO_CONFIG)
        cursor_a = AsyncSmartMockCursor()
        cursor_b = AsyncSmartMockCursor()

        grids_hoist = await _run_hoist(engine, lambda: make_async_conn(cursor_a))
        grids_recompute = await _run_no_hoist(engine, lambda: make_async_conn(cursor_b))

        assert len(grids_hoist) == _N
        fp_hoist = _fingerprint(grids_hoist, "chance")
        fp_recompute = _fingerprint(grids_recompute, "chance")
        assert fp_hoist == fp_recompute, (
            "Loto : hoist NON bit-identique au recompute per-grille !\n"
            f"hoist[:3]={fp_hoist[:3]}\nrecompute[:3]={fp_recompute[:3]}"
        )

    @pytest.mark.asyncio
    async def test_em_bit_identical(self):
        engine = HybrideEngine(EM_CONFIG)
        cursor_a = EMAsyncSmartMockCursor()
        cursor_b = EMAsyncSmartMockCursor()

        grids_hoist = await _run_hoist(engine, lambda: make_em_conn(cursor_a))
        grids_recompute = await _run_no_hoist(engine, lambda: make_em_conn(cursor_b))

        assert len(grids_hoist) == _N
        fp_hoist = _fingerprint(grids_hoist, "etoiles")
        fp_recompute = _fingerprint(grids_recompute, "etoiles")
        assert fp_hoist == fp_recompute, (
            "EM : hoist NON bit-identique au recompute per-grille !\n"
            f"hoist[:3]={fp_hoist[:3]}\nrecompute[:3]={fp_recompute[:3]}"
        )

    @pytest.mark.asyncio
    async def test_hoist_calls_secondary_scoring_once_per_tirage(self):
        """Preuve du gain : avec hoist, calculer_scores_hybrides_secondary est appelé
        1× (pas 20×) pour générer 20 grilles."""
        engine = HybrideEngine(LOTO_CONFIG)
        cursor = AsyncSmartMockCursor()

        spy = patch.object(
            HybrideEngine, "calculer_scores_hybrides_secondary",
            wraps=engine.calculer_scores_hybrides_secondary,
        )
        random.seed(_SEED)
        with spy as mocked:
            await engine.generate_grids(
                n=_N, mode="balanced", _get_connection=lambda: make_async_conn(cursor),
            )
        assert mocked.call_count == 1, (
            f"hoist attendu : 1 appel scoring secondaire, obtenu {mocked.call_count}"
        )
