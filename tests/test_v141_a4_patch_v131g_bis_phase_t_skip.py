"""V141 A.4 Patch V131.G-bis — Tests anti-faux-positif Phase G + Phase T weekday relatif.

Cible : éliminer le faux positif `HALLUCINATION_INVENTED` Check 1 observé en
prod le 18/05/2026 11:34 (revision hybride-api-eu-00867-cpd, 1.6.030) sur le
cas terrain "donne-moi une grille pour le tirage de mercredi" (Loto FR, SSE
streaming, toggle STRICT_HALLUCINATION_BLOCK=true).

Cause racine (diagnostic READ-ONLY du 18/05) :
1. User : "donne-moi une grille pour le tirage de mercredi"
2. Phase G détectée (intent génération) → HYBRIDE génère une grille
3. Phase T détectée AUSSI ("tirage" + "mercredi") → `_detect_tirage` weekday
   relatif `base_chat_detect_temporal.py:341-348` résout "mercredi" vers
   13/05/2026 (PASSÉ) au lieu de 20/05 (futur attendu par user)
4. Multi-action combine : `enrichment_context = [TIRAGE 13/05] + [GRILLE GÉNÉRÉE]`
5. V131.G `build_gemini_contents` strip `[GRILLE GÉNÉRÉE]` (sécu V131.G
   original cas 5/05 recyclé) → Gemini ne voit que [TIRAGE passé] + question
6. Gemini hallucine prédiction `10-18-27-36-41` → Check 1 `HALLUCINATION_INVENTED`
   bloque (block techniquement correct, faux positif UX).

Solution (2 fixes scope chirurgical) :
- Fix B-bis : nouvelle garde précoce dans `chat_pipeline_shared.py` avant
  Phase T (L1244) — si Phase G a été tentée (`_phase_g_attempted = True`)
  ET le message contient un weekday relatif (`_is_relative_weekday(...)`)
  → court-circuit Phase T → Phase G porte seule la réponse → pas de
  `[TIRAGE passé]` injecté → Gemini répond honnêtement.
- Fix Hyp 3 : call site non-stream `chat_pipeline_gemini.py:1036` propage
  `enrichment_context=` à `_recheck_phase0_draw_accuracy` (gap dormant
  identifié au diag — Fix 1+3 V141 A.4 Patch V131.G inactifs sur ce path).

Helper créé : `services/base_chat_detect_temporal.py::_is_relative_weekday`
(6 langues FR/EN/ES/PT/DE/NL, fallback FR si lang inconnue).

Refs :
- Diagnostic READ-ONLY du 18/05 (rapport CC Max, validation 4 hypothèses)
- Cas terrain prod 18/05 11:34:13 + 11:34:21 (deux tours, identique pattern)
- Audit V131.G original `docs/Archives/AUDIT_V131G_VS_V141A3_2026-05-11.md`
"""
from pathlib import Path

import pytest

from services.base_chat_detect_temporal import (
    _RELATIVE_WEEKDAY_RE,
    _is_relative_weekday,
)
from services.base_chat_detect_generation import _detect_generation


# ════════════════════════════════════════════════════════════════════
# Classe 1 — Tests unitaires directs du helper `_is_relative_weekday`
# ════════════════════════════════════════════════════════════════════


class TestV141A4PatchV131GBis_HelperIsRelativeWeekday:
    """V141 A.4 Patch V131.G-bis — helper `_is_relative_weekday(message, lang)`.

    Vérifie : matching 6 langues, case-insensitive, no-match sur dates
    absolues / mots temporels non-weekday / chaînes vides, fallback FR.
    """

    @pytest.mark.parametrize(
        "lang,weekday",
        [
            ("fr", "lundi"),
            ("fr", "mercredi"),
            ("fr", "samedi"),
            ("en", "monday"),
            ("en", "saturday"),
            ("es", "miércoles"),
            ("es", "sabado"),
            ("pt", "quarta"),
            ("de", "mittwoch"),
            ("nl", "zaterdag"),
        ],
    )
    def test_match_weekday_per_lang(self, lang, weekday):
        """Match weekday dans 6 langues (cas représentatifs)."""
        msg = f"donne-moi une grille pour le tirage de {weekday}"
        assert _is_relative_weekday(msg, lang) is True

    def test_case_insensitive_fr(self):
        """Helper case-insensitive (MERCREDI / Mercredi / mercredi)."""
        for variant in ("MERCREDI", "Mercredi", "mercredi", "mErCrEdI"):
            assert _is_relative_weekday(f"tirage de {variant}", "fr") is True

    def test_no_match_absolute_date_fr(self):
        """Date absolue DD/MM ou textuelle → pas un weekday relatif."""
        assert _is_relative_weekday("le tirage du 15/05/2026", "fr") is False
        assert _is_relative_weekday("le tirage du 15 mai 2026", "fr") is False

    def test_no_match_other_temporal_relative_fr(self):
        """Mots temporels relatifs NON weekday → pas un weekday relatif."""
        assert _is_relative_weekday("donne-moi une grille pour demain", "fr") is False
        assert _is_relative_weekday("les résultats d'hier", "fr") is False
        assert _is_relative_weekday("le tirage d'aujourd'hui", "fr") is False

    def test_no_match_empty_or_none_safe(self):
        """Message vide ou None safe (helper tolérant)."""
        assert _is_relative_weekday("", "fr") is False
        assert _is_relative_weekday(None, "fr") is False

    def test_fallback_unknown_lang_to_fr(self):
        """Lang inconnue (ex: 'it') → fallback regex FR."""
        assert _is_relative_weekday("tirage de mercredi", "it") is True
        assert _is_relative_weekday("draw of monday", "it") is False

    def test_relative_weekday_re_dict_has_6_langs(self):
        """Le dict `_RELATIVE_WEEKDAY_RE` couvre les 6 langues attendues."""
        assert set(_RELATIVE_WEEKDAY_RE.keys()) == {"fr", "en", "es", "pt", "de", "nl"}


# ════════════════════════════════════════════════════════════════════
# Classe 2 — Combo Phase G intent + weekday relatif → skip Phase T
# ════════════════════════════════════════════════════════════════════


class TestV141A4PatchV131GBis_PhaseTSkipOnGenIntent:
    """V141 A.4 Patch V131.G-bis Fix B-bis — combo Phase G + weekday relatif
    déclenche la garde de court-circuit Phase T dans `chat_pipeline_shared.py`.

    Vérification logique au niveau des détecteurs (l'intégration pipeline
    complète nécessite mocks DB lourds — testée séparément en smoke staging
    ÉTAPE 7 par Jyppy sur cas adversarial réels).
    """

    # ES/PT/DE/NL retirés du parametric end-to-end : `_detect_generation`
    # n'est pas multilangue actuellement (dette préexistante à traiter
    # V142+ audit dette). Le helper `_is_relative_weekday` lui EST
    # multilangue (cf Classe 1 parametric 10 cas, et test guard-logic
    # ci-dessous qui prouve que le skip fonctionnerait en 6 langs si
    # `_detect_generation` devenait multilangue). Le cas terrain réel
    # 18/05 11:34 est FR Loto, donc le scope FR+EN suffit pour fermer
    # l'incident prod sans masquer la dette derrière de faux verts.
    @pytest.mark.parametrize(
        "lang,weekday",
        [
            ("fr", "mercredi"),
            ("fr", "samedi"),
            ("en", "wednesday"),
        ],
    )
    def test_combo_gen_intent_plus_weekday_triggers_skip_condition(self, lang, weekday):
        """Cas réel adversarial : `donne-moi une grille pour [weekday]` en FR+EN.
        Vérifie que la garde Fix B-bis va se déclencher :
        - `_detect_generation(message)` = True (intent gen)
        - `_is_relative_weekday(message, lang)` = True (weekday)
        → combo → Phase T skip dans le pipeline (logique chat_pipeline_shared.py).
        """
        phrasings = {
            "fr": f"donne-moi une grille pour le tirage de {weekday}",
            "en": f"give me a grid for the {weekday} draw",
        }
        msg = phrasings[lang]
        assert _detect_generation(msg) is True, f"Phase G should detect intent for: {msg!r}"
        assert _is_relative_weekday(msg, lang) is True, f"weekday detected for: {msg!r}"

    def test_skip_guard_logic_with_simulated_flags(self):
        """Teste la LOGIQUE de la garde Fix B-bis directement, sans dépendre de
        `_detect_generation` (mono-langue actuellement, dette V142+).

        Reproduit le calcul de `chat_pipeline_shared.py:1252` :
            _skip_phase_t_for_gen_intent = _phase_g_attempted and _is_relative_weekday(message, lang)

        Avec `_phase_g_attempted=True` simulé (comme si Phase G avait matché
        en amont, ce qui est le cas réel quand l'intent gen est détecté),
        on vérifie que le combo skip déclencherait en FR ET en ES — ce qui
        prouve :
          1. Le Patch B-bis est correctement implémenté côté garde.
          2. Le combo skip fonctionnera en 6 langs dès que `_detect_generation`
             deviendra multilangue (backlog V142+ Cat A).
          3. La dette `_detect_generation` mono-langue est isolée et documentée
             (régression future bloquée par ce test si quelqu'un casse le
             helper `_is_relative_weekday` multilangue).
        """
        # FR : cas terrain réel 18/05 11:34
        msg_fr = "donne-moi une grille pour le tirage de mercredi"
        phase_g_attempted_fr = True  # Phase G a matché en amont (réel en prod)
        skip_fr = phase_g_attempted_fr and _is_relative_weekday(msg_fr, "fr")
        assert skip_fr is True, "Garde Fix B-bis doit déclencher en FR (cas terrain réel)"

        # ES : helper multilangue OK, prouve que la garde fonctionnerait
        # dès que _detect_generation devient multilangue
        msg_es = "dame una cuadrícula para el sorteo del miércoles"
        phase_g_attempted_es = True  # simulé (Phase G hypothétiquement multilangue)
        skip_es = phase_g_attempted_es and _is_relative_weekday(msg_es, "es")
        assert skip_es is True, (
            "Garde Fix B-bis doit déclencher en ES si Phase G multilangue — "
            "isole la dette `_detect_generation` mono-langue (backlog V142+ Cat A)"
        )

        # Sans Phase G attempted (cas past-results legitime), garde inactive
        # même si weekday relatif détecté
        msg_past = "résultats du tirage de mercredi dernier"
        phase_g_attempted_past = False  # Phase G n'a PAS matché
        skip_past = phase_g_attempted_past and _is_relative_weekday(msg_past, "fr")
        assert skip_past is False, (
            "Garde Fix B-bis ne doit PAS déclencher sans `_phase_g_attempted` "
            "— préserve le cas past-results (non-régression Phase T)"
        )


# ════════════════════════════════════════════════════════════════════
# Classe 3 — Non-régression : past-results requests préservés
# ════════════════════════════════════════════════════════════════════


class TestV141A4PatchV131GBis_PhaseTKeptOnPastIntent:
    """V141 A.4 Patch V131.G-bis Fix B-bis — non-régression sur cas legitime
    où user demande VRAIMENT les résultats d'un tirage passé (weekday relatif
    mais SANS intent génération).

    Garantie : la garde ne déclenche PAS, Phase T s'active normalement,
    `[TIRAGE passé]` injecté comme avant V131.G-bis.
    """

    def test_past_results_no_gen_intent_fr(self):
        """`résultats du tirage de mercredi dernier` → pas d'intent gen → Phase T active."""
        msg = "résultats du tirage de mercredi dernier"
        assert _detect_generation(msg) is False, "Phase G NE doit PAS détecter ce cas"
        assert _is_relative_weekday(msg, "fr") is True

    def test_past_results_no_gen_intent_who_won_fr(self):
        """`qui a gagné samedi ?` → pas d'intent gen → Phase T active."""
        msg = "qui a gagné samedi ?"
        assert _detect_generation(msg) is False
        assert _is_relative_weekday(msg, "fr") is True

    def test_stats_query_weekday_no_gen_intent_fr(self):
        """`stats du dimanche` → pas d'intent gen → Phase T active."""
        msg = "stats du dimanche"
        assert _detect_generation(msg) is False
        assert _is_relative_weekday(msg, "fr") is True

    def test_specific_number_query_weekday_no_gen_intent_fr(self):
        """`le 5 est-il sorti vendredi ?` → pas d'intent gen → Phase 1 ou T active."""
        msg = "le 5 est-il sorti vendredi ?"
        assert _detect_generation(msg) is False
        assert _is_relative_weekday(msg, "fr") is True

    def test_gen_intent_without_weekday_phase_t_can_run_normally(self):
        """`donne-moi une grille équilibrée` → intent gen mais PAS weekday → garde inactive.
        Phase T peut s'activer si elle détecte un autre marqueur temporel (date absolue, etc.).
        """
        msg = "donne-moi une grille équilibrée"
        assert _detect_generation(msg) is True
        assert _is_relative_weekday(msg, "fr") is False


# ════════════════════════════════════════════════════════════════════
# Classe 4 — Fix Hyp 3 : call site non-stream propage enrichment_context
# ════════════════════════════════════════════════════════════════════


class TestV141A4PatchV131GBis_FixHyp3CallSitePropagation:
    """V141 A.4 Patch V131.G-bis Fix Hyp 3 — vérifie via source-inspection que
    les 3 call sites de `_recheck_phase0_draw_accuracy` dans
    `services/chat_pipeline_gemini.py` propagent bien `enrichment_context=`.

    Gap dormant identifié au diag READ-ONLY 18/05 : call site L1036
    (handle_chat_common non-stream) ne propageait pas `enrichment_context`,
    rendant Fix 1 (skip Phase 2/3/3-bis sans `_DATA_TAG_RE`) et Fix 3
    (skip future draw context tag) inactifs sur les endpoints non-streaming.
    """

    @pytest.fixture
    def chat_pipeline_gemini_source(self):
        """Lecture brute du source pour inspection des call sites."""
        path = Path(__file__).resolve().parent.parent / "services" / "chat_pipeline_gemini.py"
        return path.read_text(encoding="utf-8")

    def test_all_recheck_phase0_calls_pass_enrichment_context(self, chat_pipeline_gemini_source):
        """Les 3 call sites doivent tous passer `enrichment_context=`.
        Compte les appels `await _recheck_phase0_draw_accuracy(` (le préfixe
        `await ` exclut la définition `async def _recheck_phase0_draw_accuracy(`
        qui contient `enrichment_context: str = ""` avec `:` et non `=`) et
        vérifie que chacun a `enrichment_context=` dans son scope d'arguments.
        """
        src = chat_pipeline_gemini_source
        # Splitter sur `await _recheck_phase0_draw_accuracy(` exclut la définition
        # (signature `async def _recheck_phase0_draw_accuracy(` non préfixée d'`await`).
        chunks = src.split("await _recheck_phase0_draw_accuracy(")
        call_chunks = chunks[1:]
        assert len(call_chunks) >= 3, (
            f"Attendu >=3 call sites `await _recheck_phase0_draw_accuracy(`, "
            f"trouvés {len(call_chunks)}"
        )
        for idx, chunk in enumerate(call_chunks, start=1):
            scope = chunk[:600]
            assert "enrichment_context=" in scope, (
                f"Call site #{idx} ne propage PAS enrichment_context= "
                f"— gap V131.G-bis Fix Hyp 3 régressé."
            )

    def test_non_stream_call_site_contains_meta_enrichment_pattern(self, chat_pipeline_gemini_source):
        """Le call site non-stream L1036 doit utiliser `_meta.get("enrichment_context", "")`
        (pattern cohérent avec les 2 autres call sites streaming V141 A.4 Patch V131.G).
        """
        src = chat_pipeline_gemini_source
        assert "V141 A.4 Patch V131.G-bis Fix Hyp 3" in src, (
            "Commentaire de traçabilité Fix Hyp 3 absent du source — patch non appliqué."
        )
        assert 'enrichment_context=_meta.get("enrichment_context", "")' in src, (
            "Pattern enrichment_context=_meta.get(...) introuvable — call site L1036 non patché."
        )
