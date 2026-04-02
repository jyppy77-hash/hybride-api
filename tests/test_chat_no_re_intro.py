"""
Tests de non-régression — anti-re-présentation chatbot.
Vérifie que le [RAPPEL CRITIQUE] est TOUJOURS injecté dans le system_prompt,
y compris au premier message (historique vide), pour les 2 pipelines :
  - Loto FR (chat_pipeline._prepare_chat_context)
  - EM 6 langues (chat_pipeline_em._prepare_chat_context_em)
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from services.chat_pipeline import _prepare_chat_context
from services.chat_pipeline_em import _prepare_chat_context_em


def _msg(role, content):
    return SimpleNamespace(role=role, content=content)


# ═══════════════════════════════════════════════════════════════════════
# Loto FR — anti-re-présentation
# ═══════════════════════════════════════════════════════════════════════

class TestAntiReIntroLoto:

    @pytest.mark.asyncio
    async def test_rappel_critique_first_message_empty_history(self):
        """Premier message, historique vide → [RAPPEL CRITIQUE] doit être présent."""
        with patch("services.chat_pipeline.load_prompt", return_value="Tu es HYBRIDE."), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value=None), \
             patch("services.chat_pipeline._detect_generation", return_value=False), \
             patch("services.chat_pipeline._detect_argent", return_value=False), \
             patch("services.chat_pipeline._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline._detect_prochain_tirage", return_value=False), \
             patch("services.chat_pipeline._detect_tirage", return_value=None), \
             patch("services.chat_pipeline._has_temporal_filter", return_value=False), \
             patch("services.chat_pipeline._detect_grille", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_requete_complexe", return_value=None), \
             patch("services.chat_pipeline._detect_cooccurrence_high_n", return_value=False), \
             patch("services.chat_pipeline._detect_triplets", return_value=False), \
             patch("services.chat_pipeline._detect_paires", return_value=False), \
             patch("services.chat_pipeline._detect_out_of_range", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_numero", return_value=(None, None)), \
             patch("services.chat_pipeline._generate_sql", return_value=None), \
             patch("services.chat_pipeline._build_session_context", return_value=""):
            early, ctx = await _prepare_chat_context(
                "quel est le numéro le plus fréquent ?", [], "accueil", MagicMock()
            )
        assert early is None
        assert ctx is not None
        assert "RAPPEL CRITIQUE" in ctx["system_prompt"]
        assert "NE TE RE-PRÉSENTE PAS" in ctx["system_prompt"]
        assert "Je suis HYBRIDE" in ctx["system_prompt"]

    @pytest.mark.asyncio
    async def test_rappel_critique_with_history(self):
        """Avec historique → [RAPPEL CRITIQUE] toujours présent."""
        history = [
            _msg("user", "bonjour"),
            _msg("assistant", "Bonjour ! Comment puis-je t'aider ?"),
        ]
        with patch("services.chat_pipeline.load_prompt", return_value="Tu es HYBRIDE."), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             patch("services.chat_pipeline._detect_insulte", return_value=None), \
             patch("services.chat_pipeline._detect_compliment", return_value=None), \
             patch("services.chat_pipeline._detect_generation", return_value=False), \
             patch("services.chat_pipeline._detect_argent", return_value=False), \
             patch("services.chat_pipeline._is_short_continuation", return_value=False), \
             patch("services.chat_pipeline._detect_prochain_tirage", return_value=False), \
             patch("services.chat_pipeline._detect_tirage", return_value=None), \
             patch("services.chat_pipeline._has_temporal_filter", return_value=False), \
             patch("services.chat_pipeline._detect_grille", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_requete_complexe", return_value=None), \
             patch("services.chat_pipeline._detect_cooccurrence_high_n", return_value=False), \
             patch("services.chat_pipeline._detect_triplets", return_value=False), \
             patch("services.chat_pipeline._detect_paires", return_value=False), \
             patch("services.chat_pipeline._detect_out_of_range", return_value=(None, None)), \
             patch("services.chat_pipeline._detect_numero", return_value=(None, None)), \
             patch("services.chat_pipeline._generate_sql", return_value=None), \
             patch("services.chat_pipeline._build_session_context", return_value=""):
            early, ctx = await _prepare_chat_context(
                "et le numéro chance ?", history, "accueil", MagicMock()
            )
        assert early is None
        assert "RAPPEL CRITIQUE" in ctx["system_prompt"]


# ═══════════════════════════════════════════════════════════════════════
# EM 6 langues — anti-re-présentation
# ═══════════════════════════════════════════════════════════════════════

_EM_PATCHES = [
    "services.chat_pipeline_em._detect_insulte",
    "services.chat_pipeline_em._detect_compliment",
    "services.chat_pipeline_em._detect_generation",
    "services.chat_pipeline_em._detect_argent_em",
    "services.chat_pipeline_em._detect_country_em",
    "services.chat_pipeline_em._is_short_continuation",
    "services.chat_pipeline_em._detect_prochain_tirage_em",
    "services.chat_pipeline_em._detect_tirage",
    "services.chat_pipeline_em._has_temporal_filter",
    "services.chat_pipeline_em._detect_requete_complexe_em",
    "services.chat_pipeline_em._detect_cooccurrence_high_n",
    "services.chat_pipeline_em._detect_triplets_em",
    "services.chat_pipeline_em._detect_paires_em",
    "services.chat_pipeline_em._detect_numero_em",
    "services.chat_pipeline_em._generate_sql_em",
]


def _em_patches():
    """Context manager stack for all EM detector patches (all return falsy)."""
    from contextlib import ExitStack
    stack = ExitStack()
    for p in _EM_PATCHES:
        if "detect_grille" in p:
            stack.enter_context(patch(p, return_value=(None, None)))
        elif "detect_numero" in p or "detect_out_of_range" in p:
            stack.enter_context(patch(p, return_value=(None, None)))
        else:
            stack.enter_context(patch(p, return_value=None))
    stack.enter_context(patch("services.chat_pipeline_em._detect_grille_em", return_value=(None, None)))
    stack.enter_context(patch("services.chat_pipeline_em._detect_out_of_range_em", return_value=(None, None)))
    stack.enter_context(patch("services.chat_pipeline_em._build_session_context_em", return_value=""))
    return stack


class TestAntiReIntroEM:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang,forbidden", [
        ("fr", ["Je suis HYBRIDE", "je m'appelle HYBRIDE"]),
        ("en", ["I'm HYBRIDE", "I am HYBRIDE", "My name is HYBRIDE"]),
        ("es", ["Soy HYBRIDE", "Me llamo HYBRIDE"]),
        ("pt", ["Sou HYBRIDE", "Eu sou HYBRIDE"]),
        ("de", ["Ich bin HYBRIDE", "Mein Name ist HYBRIDE"]),
        ("nl", ["Ik ben HYBRIDE", "Ik ben HYBRIDE", "Mijn naam is HYBRIDE"]),
    ])
    async def test_rappel_critique_first_message_all_langs(self, lang, forbidden):
        """Premier message EM, historique vide → [RAPPEL CRITIQUE] présent pour chaque langue."""
        with patch("services.chat_pipeline_em.load_prompt_em", return_value="Tu es HYBRIDE."), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             _em_patches():
            # V65: use stats question (not "hello") to bypass Phase SALUTATION
            early, ctx = await _prepare_chat_context_em(
                "what is the most frequent number", [], "accueil-em", MagicMock(), lang=lang
            )
        assert early is None
        assert ctx is not None
        assert "RAPPEL CRITIQUE" in ctx["system_prompt"], (
            f"[RAPPEL CRITIQUE] manquant pour lang={lang}"
        )
        assert "NE TE RE-PRÉSENTE PAS" in ctx["system_prompt"]

    @pytest.mark.asyncio
    async def test_rappel_critique_em_with_history(self):
        """EM avec historique → [RAPPEL CRITIQUE] toujours présent."""
        history = [
            _msg("user", "hello"),
            _msg("assistant", "Hi! How can I help?"),
        ]
        with patch("services.chat_pipeline_em.load_prompt_em", return_value="Tu es HYBRIDE."), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             _em_patches():
            early, ctx = await _prepare_chat_context_em(
                "what's the most frequent number?", history, "accueil-em", MagicMock(), lang="en"
            )
        assert early is None
        assert "RAPPEL CRITIQUE" in ctx["system_prompt"]

    @pytest.mark.asyncio
    async def test_rappel_contains_all_lang_patterns(self):
        """Le rappel EM contient les patterns d'auto-présentation de toutes les langues."""
        with patch("services.chat_pipeline_em.load_prompt_em", return_value="sys"), \
             patch.dict("os.environ", {"GEM_API_KEY": "fake"}), \
             _em_patches():
            _, ctx = await _prepare_chat_context_em(
                "test", [], "accueil-em", MagicMock(), lang="fr"
            )
        rappel = ctx["system_prompt"]
        # Vérifie que le rappel mentionne les patterns dans les principales langues
        assert "Je suis HYBRIDE" in rappel
        assert "I'm HYBRIDE" in rappel
        assert "Soy HYBRIDE" in rappel
        assert "Eu sou HYBRIDE" in rappel
        assert "Ich bin HYBRIDE" in rappel
        assert "Ik ben HYBRIDE" in rappel


# ═══════════════════════════════════════════════════════════════════════
# F14 V83 — _clean_response() anti-reintro guard (code-level)
# ═══════════════════════════════════════════════════════════════════════

from services.base_chat_utils import _clean_response


class TestCleanResponseAntiReintro:

    def test_strips_reintro_fr(self):
        text = "Je suis HYBRIDE, l'assistant IA. Voici les stats..."
        result = _clean_response(text)
        assert "Je suis HYBRIDE" not in result
        assert "Voici les stats..." in result

    def test_strips_reintro_en(self):
        text = "I am HYBRIDE, the assistant. Here are the results."
        result = _clean_response(text)
        assert "I am HYBRIDE" not in result
        assert "Here are the results." in result

    def test_strips_reintro_es(self):
        text = "Soy HYBRIDE, el asistente de IA. Aquí están los datos."
        result = _clean_response(text)
        assert "Soy HYBRIDE" not in result
        assert "datos" in result

    def test_strips_reintro_de(self):
        text = "Ich bin HYBRIDE, der Assistent. Hier sind die Daten."
        result = _clean_response(text)
        assert "Ich bin HYBRIDE" not in result
        assert "Hier sind die Daten." in result

    def test_strips_reintro_nl(self):
        text = "Ik ben HYBRIDE, de assistent. Hier zijn de gegevens."
        result = _clean_response(text)
        assert "Ik ben HYBRIDE" not in result
        assert "Hier zijn de gegevens." in result

    def test_keeps_legitimate(self):
        text = "Je suis certain que le numéro 7 est fréquent."
        result = _clean_response(text)
        assert result == text

    def test_strips_mid_response(self):
        text = "Les stats montrent...\n\nJe suis HYBRIDE, l'assistant. Pour rappel, le 7 est chaud."
        result = _clean_response(text)
        assert "Je suis HYBRIDE" not in result
        assert "Les stats montrent..." in result
        assert "Pour rappel" in result

    def test_strips_reintro_pt(self):
        text = "Sou HYBRIDE, o assistente. Aqui estão os dados."
        result = _clean_response(text)
        assert "Sou HYBRIDE" not in result
        assert "dados" in result

    def test_multiple_reintros_in_same_response(self):
        """Two re-introductions in one response → both stripped."""
        text = (
            "Je suis HYBRIDE, l'assistant IA. Voici les stats.\n\n"
            "Pour résumer...\n\n"
            "Je suis HYBRIDE, l'assistant. Le numéro 7 est chaud."
        )
        result = _clean_response(text)
        assert result.count("Je suis HYBRIDE") == 0
        assert "Voici les stats." in result
        assert "Le numéro 7 est chaud." in result

    def test_keeps_je_suis_with_other_subject(self):
        """'Je suis sûr que...' must NOT be stripped (not HYBRIDE/assistant)."""
        text = "Je suis sûr que le numéro 7 est fréquent."
        result = _clean_response(text)
        assert result == text
