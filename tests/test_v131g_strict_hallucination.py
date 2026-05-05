"""V131.G — Strict anti-hallucination block (env var opt-in buffer mode).

Cas terrain motivant : prod 5/05/2026 12:04:30 EM FR — question
"peux tu me donner le 10 eme tirage de 2021 ." → hallucination
context-leak grille HYBRIDE (audit V131.G READ-ONLY P1+P3+Q9).

Tests :
- TestStrictHallucinationEnvVar (4) : env var truthy/falsy/empty/strict
- TestHybrideTagStrip (5) : strip [GRILLE GÉNÉRÉE] + [BREAKDOWN] + [CONTRAINTES]
- TestPhase1RecheckExtended (3) : V131.G phase coverage 0/1/T
- TestStreamingStrictBlock (3) : buffer mode + replacement i18n
"""

import importlib
import os
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.chat_pipeline_gemini import (
    _HYBRIDE_TAG_STRIP_RE,
    _NOCHUNKS_FALLBACK_I18N,
    _STRICT_BLOCK_FALLBACK_I18N,
    _recheck_phase0_draw_accuracy,
    _strip_hybride_tags,
    stream_and_respond,
    sse_event,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _msg(role, content):
    """Crée un mock msg compatible Pydantic (role/content attrs)."""
    m = MagicMock()
    m.role = role
    m.content = content
    return m


async def _normal_iter(*chunks):
    for c in chunks:
        yield c


async def _empty_iter():
    """Stream qui yield 1 seul chunk vide (pour tests buffer mode)."""
    chunk = MagicMock()
    chunk.text = ""
    chunk.candidates = []
    chunk.usage_metadata = None
    yield chunk


async def _collect(gen):
    out = []
    async for c in gen:
        out.append(c)
    return out


# ─────────────────────────────────────────────────────────────────────
# Classe 1 — TestStrictHallucinationEnvVar (4 tests)
# ─────────────────────────────────────────────────────────────────────


class TestStrictHallucinationEnvVar:
    """V131.G — Env var STRICT_HALLUCINATION_BLOCK pattern V134 _env_bool."""

    def test_default_false_when_env_absent(self):
        """V131.G — env var absente → flag False (rollout shadow safe)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STRICT_HALLUCINATION_BLOCK", None)
            import config.engine
            importlib.reload(config.engine)
            assert config.engine.STRICT_HALLUCINATION_BLOCK_ENABLED is False

    def test_truthy_variants_enable_flag(self):
        """V131.G — "true"/"1"/"yes"/"on" case-insens. → True (pattern V134)."""
        for val in ("true", "TRUE", "1", "yes", "YES", "on", "ON"):
            with patch.dict(os.environ, {"STRICT_HALLUCINATION_BLOCK": val}):
                import config.engine
                importlib.reload(config.engine)
                assert config.engine.STRICT_HALLUCINATION_BLOCK_ENABLED is True, (
                    f"Value {val!r} should enable strict mode"
                )

    def test_falsy_strict_fail_closed(self):
        """V131.G — "false"/"0"/"no"/"off"/empty → False (strict fail-closed)."""
        for val in ("false", "0", "no", "off", "", "  ", "yes please"):
            with patch.dict(os.environ, {"STRICT_HALLUCINATION_BLOCK": val}):
                import config.engine
                importlib.reload(config.engine)
                assert config.engine.STRICT_HALLUCINATION_BLOCK_ENABLED is False, (
                    f"Value {val!r} should NOT enable strict mode (fail-closed)"
                )

    def test_strict_block_fallback_i18n_dict_complete(self):
        """V131.G — Dict 6 langs avec "🤖" + format consistant."""
        assert set(_STRICT_BLOCK_FALLBACK_I18N.keys()) == {"fr", "en", "es", "pt", "de", "nl"}
        for lang, msg in _STRICT_BLOCK_FALLBACK_I18N.items():
            assert isinstance(msg, str)
            assert "🤖" in msg
            assert len(msg) >= 50
        # Distinct du dict NOCHUNKS V131.F
        assert _STRICT_BLOCK_FALLBACK_I18N["fr"] != _NOCHUNKS_FALLBACK_I18N["fr"]


# ─────────────────────────────────────────────────────────────────────
# Classe 2 — TestHybrideTagStrip (5 tests)
# ─────────────────────────────────────────────────────────────────────


class TestHybrideTagStrip:
    """V131.G — Strip tags techniques HYBRIDE des messages assistant."""

    def test_strip_grille_generee_block(self):
        """V131.G — [GRILLE GÉNÉRÉE PAR HYBRIDE]\\n... strippé jusqu'au double \\n."""
        text = (
            "Voici ta grille:\n"
            "[GRILLE GÉNÉRÉE PAR HYBRIDE]\n"
            "Numéros : [1, 10, 12, 29, 49]\n"
            "Étoiles : [2, 10]\n\n"
            "Bon tirage!"
        )
        out = _strip_hybride_tags(text)
        assert "GRILLE GÉNÉRÉE" not in out
        assert "Bon tirage" in out

    def test_strip_breakdown_block(self):
        """V131.G — [BREAKDOWN — Critères de sélection] strippé."""
        text = (
            "Stats:\n"
            "[BREAKDOWN — Critères de sélection]\n"
            "Équilibre pair/impair : 3 pairs, 2 impairs\n\n"
            "Fin"
        )
        out = _strip_hybride_tags(text)
        assert "BREAKDOWN" not in out
        assert "Fin" in out

    def test_strip_contraintes_utilisateur(self):
        """V131.G — [CONTRAINTES UTILISATEUR] strippé."""
        text = (
            "Contraintes:\n"
            "[CONTRAINTES UTILISATEUR]\n"
            "- Plage exclue : 1-31 (dates de naissance)\n\n"
            "Voilà"
        )
        out = _strip_hybride_tags(text)
        assert "CONTRAINTES" not in out
        assert "Voilà" in out

    def test_no_tag_idempotent(self):
        """V131.G — Texte sans tag retourné inchangé."""
        text = "Texte conversationnel naturel sans aucun tag technique."
        assert _strip_hybride_tags(text) == text

    def test_strip_handles_internal_brackets(self):
        """V131.G — Bug regex initial : `[1, 10, 12]` interne ne casse pas le strip.

        Régression : le pattern initial `[^\\[]*?` interdisait les `[` internes
        et empêchait le match. Fix : `.*?` avec `re.DOTALL` + lookahead `\\n\\n|\\Z`.
        """
        text = (
            "[GRILLE GÉNÉRÉE PAR HYBRIDE]\n"
            "Numéros : [1, 10, 12, 29, 49]\n"
            "Étoiles : [2, 10]\n\n"
            "Reste"
        )
        out = _strip_hybride_tags(text)
        assert "GRILLE GÉNÉRÉE" not in out
        assert "Numéros" not in out
        assert "Reste" in out


# ─────────────────────────────────────────────────────────────────────
# Classe 3 — TestPhase1RecheckExtended (3 tests)
# ─────────────────────────────────────────────────────────────────────


class TestPhase1RecheckExtended:
    """V131.G — _recheck_phase0_draw_accuracy étendue à phases 0/1/T."""

    @pytest.mark.asyncio
    async def test_phase_1_now_covered(self):
        """V131.G — Phase 1 + mismatch → safe_replacement (était None V126)."""
        response = "Le tirage du 28 mars 2026 : 1-10-12-29-49"
        # Mock get_tirage_fn retourne un tirage différent → mismatch
        mock_tirage = {
            "boules": [18, 20, 35, 38, 48],
            "etoiles": [9, 12],
            "date": "2026-03-28",  # clé attendue par _format_last_draw_context
        }
        get_tirage_fn = AsyncMock(return_value=mock_tirage)

        result = await _recheck_phase0_draw_accuracy(
            response, "1", "fr", "[TEST]",
            get_tirage_fn=get_tirage_fn,
            game="loto",
        )
        # V131.G : Phase 1 désormais couverte → mismatch détecté → safe_replacement
        assert result is not None
        assert "donn" in result.lower() or "data" in result.lower()

    @pytest.mark.asyncio
    async def test_phase_t_now_covered(self):
        """V131.G — Phase T + mismatch → safe_replacement (était None V126)."""
        response = "Le tirage du 15 février 2026 : 7-14-21-28-35"
        mock_tirage = {
            "boules": [3, 8, 11, 22, 44],
            "chance": 5,  # Loto sans étoiles
            "date": "2026-02-15",
        }
        get_tirage_fn = AsyncMock(return_value=mock_tirage)

        result = await _recheck_phase0_draw_accuracy(
            response, "T", "fr", "[TEST]",
            get_tirage_fn=get_tirage_fn,
            game="loto",
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_phase_g_still_skipped(self):
        """V131.G — Phase G/SQL/AFFIRMATION etc. restent skippées."""
        response = "Une grille générée : 1-2-3-4-5"
        get_tirage_fn = AsyncMock()
        for phase in ("G", "SQL", "AFFIRMATION", "P", "OOR", "I"):
            result = await _recheck_phase0_draw_accuracy(
                response, phase, "fr", "[TEST]",
                get_tirage_fn=get_tirage_fn,
                game="loto",
            )
            assert result is None, f"Phase {phase} doit rester skippée"
        # get_tirage_fn ne doit JAMAIS avoir été appelé sur ces phases
        get_tirage_fn.assert_not_called()


# ─────────────────────────────────────────────────────────────────────
# Classe 4 — TestStreamingStrictBlock (3 tests)
# ─────────────────────────────────────────────────────────────────────


class TestStreamingStrictBlock:
    """V131.G — Buffer mode opt-in via ctx flag _strict_hallucination_block."""

    @pytest.mark.asyncio
    async def test_block_yields_i18n_when_invented_seq(self):
        """V131.G — strict mode + invented seq + context tag factuel
        → yield message i18n strict au lieu des chunks bufferés.
        """
        import time as _time

        # Mock stream qui yield directement des strings (signature stream_gemini_chat)
        async def _stream(*args, **kwargs):
            yield "Le tirage : 1-10-12-29-49"

        # Ctx avec enrichment_context contenant des numéros DIFFÉRENTS
        # → invented seq détectée → block
        ctx = {
            "system_prompt": "sys",
            "contents": [{"role": "user", "parts": [{"text": "test"}]}],
            "mode": "chat",
            "insult_prefix": "",
            "history": [],
            "lang": "fr",
            "_http_client": MagicMock(),
            "gem_api_key": "",
            "_strict_hallucination_block": True,  # V131.G strict mode ON
            "_chat_meta": {
                "phase": "1",  # V131.G : Phase 1 désormais couverte
                "lang": "fr",
                "t0": _time.monotonic(),  # leçon V131.F : log_chat_exchange duration calc
                "enrichment_context": (
                    "[RÉSULTAT TIRAGE]\n"
                    "Numéros : 18, 20, 35, 38, 48\n"
                    "[/RÉSULTAT TIRAGE]"
                ),
            },
            "_get_tirage_fn": None,
            "_game": "loto",
        }

        events = await _collect(stream_and_respond(
            ctx, "OLD HARDCODED", "[TEST]", "loto", "fr",
            "msg", "page", "chat", stream_fn=_stream,
        ))

        full_text = "".join(events)
        # Le message strict block FR doit être yieldé
        assert "certitude" in full_text.lower() or "reformul" in full_text.lower()
        # Les chunks originaux NE doivent PAS apparaître (block)
        assert "1-10-12-29-49" not in full_text

    @pytest.mark.asyncio
    async def test_no_block_yields_normal_chunks_when_no_halluci(self):
        """V131.G — strict mode ON + réponse factuelle → chunks bufferés délivrés."""
        import time as _time

        # Mock stream avec réponse factuelle (numéros = ceux du contexte)
        async def _stream(*args, **kwargs):
            yield "Les numéros sont 18, 20, 35, 38, 48 — tirage validé."

        ctx = {
            "system_prompt": "sys",
            "contents": [{"role": "user", "parts": [{"text": "test"}]}],
            "mode": "chat",
            "insult_prefix": "",
            "history": [],
            "lang": "fr",
            "_http_client": MagicMock(),
            "gem_api_key": "",
            "_strict_hallucination_block": True,
            "_chat_meta": {
                "phase": "1",
                "lang": "fr",
                "t0": _time.monotonic(),
                "enrichment_context": (
                    "[RÉSULTAT TIRAGE]\n"
                    "Numéros : 18, 20, 35, 38, 48\n"
                    "[/RÉSULTAT TIRAGE]"
                ),
            },
            "_get_tirage_fn": None,
            "_game": "loto",
        }

        events = await _collect(stream_and_respond(
            ctx, "OLD", "[TEST]", "loto", "fr",
            "msg", "page", "chat", stream_fn=_stream,
        ))

        full_text = "".join(events)
        # Les chunks originaux DOIVENT être présents (pas de block)
        assert "18" in full_text and "tirage validé" in full_text
        # Le message strict NE doit PAS apparaître
        assert "certitude" not in full_text.lower()

    @pytest.mark.asyncio
    async def test_strict_off_preserves_v131f_behavior(self):
        """V131.G — env var OFF (default) → comportement V131.F préservé.

        Régression critique : si strict mode désactivé, les chunks sont
        yieldés progressivement (pas de buffer mode), checks log-only.
        """
        import time as _time

        async def _stream(*args, **kwargs):
            yield "part1"
            yield "part2"

        ctx = {
            "system_prompt": "sys",
            "contents": [{"role": "user", "parts": [{"text": "test"}]}],
            "mode": "chat",
            "insult_prefix": "",
            "history": [],
            "lang": "fr",
            "_http_client": MagicMock(),
            "gem_api_key": "",
            # _strict_hallucination_block ABSENT du ctx → default False via .get()
            "_chat_meta": {
                "phase": "Gemini",
                "lang": "fr",
                "t0": _time.monotonic(),
                "enrichment_context": "",
            },
            "_get_tirage_fn": None,
            "_game": "loto",
        }

        events = await _collect(stream_and_respond(
            ctx, "OLD", "[TEST]", "loto", "fr",
            "msg", "page", "chat", stream_fn=_stream,
        ))

        full_text = "".join(events)
        # Les 2 chunks doivent être présents (yield progressif V131.F)
        assert "part1" in full_text
        assert "part2" in full_text
