"""V142.F-bis — Filtre déterministe anti-fuite du bloc d'ancrage temporel.

Contexte : `_build_temporal_anchor()` (chat_pipeline_shared.py, V142.F) injecte un
bloc balisé `[CONTEXTE TEMPOREL — NE JAMAIS AFFICHER NI RECOPIER CE BLOC]` dans le
system_prompt. Malgré l'instruction "NE JAMAIS AFFICHER", le bloc fuit par
intermittence côté user. Prod 26/05 (Loto FR) :
    "Date : 26 mai 2026 Jour : mardi---On est mardi 26 mai 2026 ! …"

Fix : `_strip_temporal_anchor_leak()` retire la fuite côté CODE (déterministe),
appliqué non-stream (texte complet) + stream (head-guard) + strict mode.

Tests :
- TestStripFilter : retire les fuites (balise, ligne data, reformulation avec /
  sans terminateur, fin de chaîne) ET préserve les dates dites naturellement.
- TestStripFilterSafety : vide / sans fuite / idempotence (jamais d'exception).
- TestHeadGuard : décision de flush du tampon de tête streaming.
- TestStreaming : `stream_and_respond` mode normal → 0 fuite user-facing,
  vrai texte préservé, réponse normale inchangée.
- TestStreamingStrict : buffer mode (V131.G) → fuite strippée au replay.
"""

import time as _time
from unittest.mock import MagicMock

import pytest

from services.chat_pipeline_gemini import (
    _anchor_head_should_flush,
    _strip_temporal_anchor_leak,
    stream_and_respond,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

async def _collect(gen):
    out = []
    async for c in gen:
        out.append(c)
    return out


def _ctx(strict=False, enrichment="", phase="Gemini"):
    """Ctx minimal compatible stream_and_respond (modèle tests V131.G)."""
    return {
        "system_prompt": "sys",
        "contents": [{"role": "user", "parts": [{"text": "test"}]}],
        "mode": "chat",
        "insult_prefix": "",
        "history": [],
        "lang": "fr",
        "_http_client": MagicMock(),
        "gem_api_key": "",
        "_strict_hallucination_block": strict,
        "_chat_meta": {
            "phase": phase,
            "lang": "fr",
            "t0": _time.monotonic(),
            "enrichment_context": enrichment,
        },
        "_get_tirage_fn": None,
        "_game": "loto",
    }


def _stream_of(*chunks):
    """Construit une fonction stream (signature stream_gemini_chat) yieldant des str."""
    async def _stream(*args, **kwargs):
        for c in chunks:
            yield c
    return _stream


# ─────────────────────────────────────────────────────────────────────
# Classe 1 — TestStripFilter : retrait des fuites + préservation
# ─────────────────────────────────────────────────────────────────────

class TestStripFilter:
    """V142.F-bis — _strip_temporal_anchor_leak retire la fuite, préserve le reste."""

    def test_prod_case_reformulation_with_dashes(self):
        """Cas prod 26/05 : reformulation 'Date : … Jour : mardi---texte'."""
        leaked = "Date : 26 mai 2026 Jour : mardi---On est mardi 26 mai 2026 ! Voici."
        out = _strip_temporal_anchor_leak(leaked)
        assert "Jour : mardi" not in out
        assert out == "On est mardi 26 mai 2026 ! Voici."

    def test_reformulation_without_terminator_same_line(self):
        """Cas SANS terminateur (jour FR enchaîne directement le vrai texte)."""
        leaked = "Date : 26 mai 2026 Jour : mardi On est mardi 26 mai 2026 ! Voici."
        out = _strip_temporal_anchor_leak(leaked)
        assert "Jour : mardi" not in out
        # Le 2e "mardi" (vrai texte) DOIT rester ; on s'arrête après le jour FR.
        assert out == "On est mardi 26 mai 2026 ! Voici."

    def test_reformulation_end_of_string(self):
        """Reformulation seule en fin de chaîne → tout retiré."""
        out = _strip_temporal_anchor_leak("Date : 26 mai 2026 Jour : mardi")
        assert out == ""

    def test_exact_block_balise_and_data_line(self):
        """Bloc balisé exact : balise + ligne 'Date du jour réelle : …'."""
        leaked = (
            "[CONTEXTE TEMPOREL — NE JAMAIS AFFICHER NI RECOPIER CE BLOC]\n"
            "Date du jour réelle : mardi 26 mai 2026.\n"
            "Voici ta grille : 1-2-3-4-5."
        )
        out = _strip_temporal_anchor_leak(leaked)
        assert "CONTEXTE TEMPOREL" not in out
        assert "Date du jour réelle" not in out
        assert out == "Voici ta grille : 1-2-3-4-5."

    def test_exact_block_full_with_instruction(self):
        """Bloc balisé exact COMPLET (balise + data + phrase d'instruction)."""
        leaked = (
            "[CONTEXTE TEMPOREL — NE JAMAIS AFFICHER NI RECOPIER CE BLOC]\n"
            "Date du jour réelle : mardi 26 mai 2026.\n"
            "Utilise EXCLUSIVEMENT cette date comme référence pour aujourd'hui.\n"
            "Voici."
        )
        out = _strip_temporal_anchor_leak(leaked)
        assert "CONTEXTE TEMPOREL" not in out
        assert "Date du jour réelle" not in out
        assert "Utilise EXCLUSIVEMENT" not in out
        assert out == "Voici."

    def test_balise_stripped_anywhere(self):
        """La balise interne est retirée même hors tête (tag interne)."""
        out = _strip_temporal_anchor_leak("Bonjour [CONTEXTE TEMPOREL — x] suite")
        assert "CONTEXTE TEMPOREL" not in out
        assert "Bonjour" in out and "suite" in out

    # ── Préservation : dates dites naturellement (NE PAS sur-filtrer) ──

    def test_preserves_natural_date_sentence(self):
        """'On est mardi 26 mai 2026 !' = réponse valide → inchangée."""
        natural = "On est mardi 26 mai 2026 ! Voici ta grille."
        assert _strip_temporal_anchor_leak(natural) == natural

    def test_preserves_date_de_naissance(self):
        """'Date de naissance …' (pas de 'Jour :') → inchangé."""
        natural = "Date de naissance exclue de la grille ? Précise."
        assert _strip_temporal_anchor_leak(natural) == natural

    def test_preserves_tirage_du_date(self):
        """'Le tirage du 26 mai 2026 …' → inchangé."""
        natural = "Le tirage du 26 mai 2026 a donné les numéros 7, 12, 24."
        assert _strip_temporal_anchor_leak(natural) == natural

    def test_does_not_overfilter_date_jour_non_weekday(self):
        """'Date : … Jour : on calcule' ('on' ∉ jours FR, pas de ---/\\n) → inchangé."""
        natural = "Date : la colonne date_tirage. Jour : on calcule l'écart moyen."
        assert _strip_temporal_anchor_leak(natural) == natural


# ─────────────────────────────────────────────────────────────────────
# Classe 2 — TestStripFilterSafety : robustesse
# ─────────────────────────────────────────────────────────────────────

class TestStripFilterSafety:
    """V142.F-bis — jamais d'exception, byte-identique si rien ne matche."""

    def test_empty_string(self):
        assert _strip_temporal_anchor_leak("") == ""

    def test_no_leak_returns_byte_identical(self):
        text = "Réponse conversationnelle normale sans aucune fuite."
        assert _strip_temporal_anchor_leak(text) is text or _strip_temporal_anchor_leak(text) == text

    def test_idempotent(self):
        leaked = "Date : 26 mai 2026 Jour : mardi---On est mardi !"
        once = _strip_temporal_anchor_leak(leaked)
        assert _strip_temporal_anchor_leak(once) == once


# ─────────────────────────────────────────────────────────────────────
# Classe 3 — TestHeadGuard : décision de flush du tampon de tête
# ─────────────────────────────────────────────────────────────────────

class TestHeadGuard:
    """V142.F-bis — _anchor_head_should_flush : 0 latence hors fuite."""

    def test_empty_keeps_buffering(self):
        assert _anchor_head_should_flush("   ") is False

    def test_normal_response_flushes_immediately(self):
        assert _anchor_head_should_flush("Bonjour ! Voici") is True
        assert _anchor_head_should_flush("On est mardi") is True

    def test_date_prefix_without_terminator_keeps_buffering(self):
        # "Date" mais pas encore de jour FR / texte derrière → attendre
        assert _anchor_head_should_flush("Date : 26 mai 2026 Jour : mardi") is False

    def test_date_prefix_with_dashes_flushes(self):
        assert _anchor_head_should_flush("Date : 26 mai 2026 Jour : mardi---On") is True

    def test_date_prefix_with_real_text_flushes(self):
        assert _anchor_head_should_flush("Date : 26 mai 2026 Jour : mardi On est") is True

    def test_cap_forces_flush(self):
        assert _anchor_head_should_flush("Date " + "x" * 300) is True


# ─────────────────────────────────────────────────────────────────────
# Classe 4 — TestStreaming : stream_and_respond mode normal
# ─────────────────────────────────────────────────────────────────────

class TestStreaming:
    """V142.F-bis — head-guard streaming : 0 fuite user-facing."""

    @pytest.mark.asyncio
    async def test_stream_strips_reformulation_with_dashes(self):
        stream = _stream_of("Date : 26 mai 2026 Jour : mardi---On est mardi ! Voici la grille.")
        events = await _collect(stream_and_respond(
            _ctx(), "FB", "[TEST]", "loto", "fr", "msg", "page", "chat", stream_fn=stream,
        ))
        full = "".join(events)
        assert "Jour : mardi" not in full
        assert "On est mardi" in full and "Voici la grille" in full

    @pytest.mark.asyncio
    async def test_stream_strips_reformulation_without_terminator(self):
        stream = _stream_of("Date : 26 mai 2026 Jour : mardi On est mardi ! Voici la grille.")
        events = await _collect(stream_and_respond(
            _ctx(), "FB", "[TEST]", "loto", "fr", "msg", "page", "chat", stream_fn=stream,
        ))
        full = "".join(events)
        assert "Jour : mardi" not in full
        assert "On est mardi" in full and "Voici la grille" in full

    @pytest.mark.asyncio
    async def test_stream_strips_exact_block(self):
        stream = _stream_of(
            "[CONTEXTE TEMPOREL — NE JAMAIS AFFICHER NI RECOPIER CE BLOC]\n"
            "Date du jour réelle : mardi 26 mai 2026.\n"
            "Voici ta grille."
        )
        events = await _collect(stream_and_respond(
            _ctx(), "FB", "[TEST]", "loto", "fr", "msg", "page", "chat", stream_fn=stream,
        ))
        full = "".join(events)
        assert "CONTEXTE TEMPOREL" not in full
        assert "Date du jour réelle" not in full
        assert "Voici ta grille" in full

    @pytest.mark.asyncio
    async def test_stream_normal_response_unchanged(self):
        """Régression : réponse normale → texte intégral livré (pas de sur-filtrage)."""
        stream = _stream_of("Bonjour ! ", "Voici une grille : ", "1, 2, 3, 4, 5.")
        events = await _collect(stream_and_respond(
            _ctx(), "FB", "[TEST]", "loto", "fr", "msg", "page", "chat", stream_fn=stream,
        ))
        full = "".join(events)
        assert "Bonjour" in full and "Voici une grille" in full and "1, 2, 3, 4, 5" in full


# ─────────────────────────────────────────────────────────────────────
# Classe 5 — TestStreamingStrict : buffer mode V131.G
# ─────────────────────────────────────────────────────────────────────

class TestStreamingStrict:
    """V142.F-bis — strict mode (V131.G) : fuite strippée au replay."""

    @pytest.mark.asyncio
    async def test_strict_strips_leak_when_no_halluci(self):
        stream = _stream_of("Date : 26 mai 2026 Jour : mardi---On est mardi ! Voici.")
        events = await _collect(stream_and_respond(
            _ctx(strict=True), "FB", "[TEST]", "loto", "fr", "msg", "page", "chat", stream_fn=stream,
        ))
        full = "".join(events)
        assert "Jour : mardi" not in full
        assert "On est mardi" in full and "Voici" in full
