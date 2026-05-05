"""V127 — Tests recheck Phase 0 timeout réduit 3s → 1s (Option C audit V126.1).

Garde le bloquant pour préserver défense anti-hallucination V126,
mais limite l'impact latence non-streaming à +1s pire cas (vs +3s avant).
"""

import asyncio
import logging
from datetime import date

import pytest

from services.chat_pipeline_gemini import _recheck_phase0_draw_accuracy


def _real_tirage_loto():
    """Tirage simulé en base : numéros 1-2-3-4-5 + chance 7."""
    return {
        "date": date(2026, 4, 15),
        "boules": [1, 2, 3, 4, 5],
        "chance": 7,
    }


@pytest.mark.asyncio
async def test_recheck_completes_under_1s_returns_replacement():
    """DB répond rapidement + mismatch numéros → replacement message renvoyé."""
    async def _fast_db(_d):
        await asyncio.sleep(0.05)  # 50ms simulé
        return _real_tirage_loto()

    # Réponse Gemini hallucinée (numéros 99-99-99-99-99 != réels 1-2-3-4-5)
    resp = "Le tirage du 15 avril 2026 a donné 99 - 88 - 77 - 66 - 55"
    out = await _recheck_phase0_draw_accuracy(
        resp, "0", "fr", "[TEST]",
        get_tirage_fn=_fast_db, game="loto",
    )
    assert out is not None
    assert "1" in out and "2" in out  # contient les vrais numéros


@pytest.mark.asyncio
async def test_recheck_timeout_at_1s_returns_none(caplog):
    """DB > 1s → asyncio.TimeoutError → log warning + return None (log-only)."""
    async def _slow_db(_d):
        await asyncio.sleep(1.5)  # plus long que le timeout 1s V127
        return _real_tirage_loto()

    resp = "Le tirage du 15 avril 2026 a donné 99 - 88 - 77 - 66 - 55"
    with caplog.at_level(logging.WARNING):
        out = await _recheck_phase0_draw_accuracy(
            resp, "0", "fr", "[TEST]",
            get_tirage_fn=_slow_db, game="loto",
        )
    assert out is None
    assert any("V127 reapply TIMEOUT" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_recheck_timeout_uses_1s_not_3s():
    """Vérification de la valeur de timeout — DB qui prend 2s doit timeout
    (avant V127 timeout=3, n'aurait pas timeout)."""
    async def _2s_db(_d):
        await asyncio.sleep(2.0)
        return _real_tirage_loto()

    resp = "Le tirage du 15 avril 2026 a donné 99 - 88 - 77 - 66 - 55"
    start = asyncio.get_event_loop().time()
    out = await _recheck_phase0_draw_accuracy(
        resp, "0", "fr", "[TEST]",
        get_tirage_fn=_2s_db, game="loto",
    )
    elapsed = asyncio.get_event_loop().time() - start
    # Timeout 1s atteint → return None bien avant 2s
    assert out is None
    assert elapsed < 1.5  # marge sécurité


@pytest.mark.asyncio
async def test_recheck_phase_outside_coverage_short_circuit():
    """V131.G — Phase hors ("0", "1", "T") → pas de DB call (pas d'impact timeout).

    Note V131.G : phase coverage étendue à ("0", "1", "T") pour couvrir cas
    terrain Jyppy 5/05/2026 (Phase 1 hallucination grille HYBRIDE recyclée).
    Test ajusté de "1" → "G" pour rester sémantiquement valide (Phase G/SQL/A
    etc. restent court-circuitées).
    """
    called = []

    async def _db(_d):
        called.append(True)
        return _real_tirage_loto()

    resp = "Le tirage du 15 avril 2026 a donné 99 - 88 - 77 - 66 - 55"
    out = await _recheck_phase0_draw_accuracy(
        resp, "G", "fr", "[TEST]",  # V131.G : "1" → "G" (Phase G hors coverage)
        get_tirage_fn=_db, game="loto",
    )
    assert out is None
    assert not called
