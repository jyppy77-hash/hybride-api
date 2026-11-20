"""
Tests — Lot 1.6.074 (19/11/2026) : fix chatbot, étoiles / numéros / prochain tirage hors FR
(audit RO 074 du 19/11, causes CF-1, CF-3, CF-4, CF-5, CF-7).

T1  Matrice de routage, pipeline RÉEL (`_prepare_chat_context*`), détecteurs réels ; seules la base et
    Gemini sont mockés : les 47 questions du smoke de Muse (19/11) + #15.
T1b CF-4 : la détection du numéro EM pour lang="fr" est celle de la config (inchangée) ; non-bascule
    en Phase 1 (génération, comparaison, classement, mot étoile).
T2  CF-1 : contrôle 2 sur des réponses types (verbatim smoke + reconstituées), étoiles 10 / 11 / 12,
    paire réellement fausse toujours bloquée ; buffer strict de bout en bout.
T3  CF-7 : fuites verbatim retirées (en-tête traduit, lignes d'ancrage), témoins intacts.
T4  CF-5 : 0-bis EM 6 langues, pas de capture des questions de dernier tirage / dernière sortie ;
    _NEXT_KW_RE fléchi sans « prochaine ».
T5  CF-3 : « top N des paires / triplets » en Phase P (Loto + EM), témoins en Phase 3.
T6  Version 1.6.074 / VERSION_DATE 2026-11-19 (config + /api/version).
T7  D3 (ex aequo des paires) : O1 tri SQL déterministe (paires, paires d'étoiles, triplets ; hot / cold) ;
    O2 Phase P : 5 lignes + ex aequo du 5e (plafond 10), rang de compétition, mention et consigne ex aequo ;
    bloc identique à 1.6.074 initial sans ex aequo ; pipeline réel (top_n=50).

Aucun accès base, réseau ou Gemini (garde autouse tests/conftest.py).
"""

import contextlib
import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════
# Harnais pipeline (base et Gemini mockés, détecteurs réels)
# ═══════════════════════════════════════════════════════

def _stats(numero, type_num=None):
    return {"numero": numero, "type": type_num or "boule", "frequence_totale": 62, "total_tirages": 732,
            "pourcentage_apparition": "8.47%", "derniere_sortie": "2026-09-29", "ecart_actuel": 14,
            "ecart_moyen": 11.7, "classement": 30, "classement_sur": 50, "categorie": "neutre",
            "periode": "2019-11-15 au 2026-11-17"}


def _tirage(game):
    async def _f(target):
        d = target if isinstance(target, date) else date(2026, 11, 17)
        base = {"date": d, "boules": [3, 12, 14, 17, 37]}
        return {**base, "chance": 7} if game == "loto" else {**base, "etoiles": [3, 12]}
    return _f


_DATA = {
    "get_classement_numeros": {"items": [{"numero": 7, "frequence": 100, "ecart_actuel": 2, "categorie": "chaud"}],
                               "total_tirages": 732, "periode": "mock"},
    "get_pair_correlations": {"total_draws": 732, "pairs": [{"num_a": 3, "num_b": 12, "count": 20,
                                                              "percentage": 2.7}]},
    "get_star_pair_correlations": {"total_draws": 732, "pairs": [{"num_a": 2, "num_b": 9, "count": 30,
                                                                   "percentage": 4.1}]},
    "get_triplet_correlations": {"total_draws": 732, "triplets": [{"num_a": 1, "num_b": 2, "num_c": 3,
                                                                    "count": 5, "percentage": 0.7}]},
}
_GRID = {"grids": [{"nums": [3, 12, 21, 33, 44], "etoiles": [2, 9], "chance": 4, "score": 85,
                    "badges": [], "mode": "balanced"}]}


async def _run(game, msg, lang=None, spy_cfg=None):
    """Retourne (meta, mocks) pour un tour unique, historique vide. lang=None : endpoint sans `lang`."""
    mod = "services.chat_pipeline" if game == "loto" else "services.chat_pipeline_em"
    names = ({"prochain": "_get_prochain_tirage", "tirage": "_get_tirage_data", "sql": "_generate_sql",
              "prompt": "load_prompt"} if game == "loto" else
             {"prochain": "_get_prochain_tirage_em", "tirage": "_get_tirage_data_em", "sql": "_generate_sql_em",
              "prompt": "load_prompt_em"})
    mocks = {}
    with contextlib.ExitStack() as st:
        if spy_cfg is not None:
            import services.chat_pipeline_shared as shared
            orig = shared._prepare_chat_context_base

            async def _spy(message, history, page, http_client, lang_, cfg):
                spy_cfg["cfg"] = cfg
                return await orig(message, history, page, http_client, lang_, cfg)
            st.enter_context(patch(f"{mod}._prepare_chat_context_base", side_effect=_spy))
        st.enter_context(patch("services.chat_pipeline._get_draw_count", new_callable=AsyncMock, return_value=1000))
        st.enter_context(patch(f"{mod}.{names['prompt']}", return_value="sys"))
        mocks["prochain"] = st.enter_context(patch(
            f"{mod}.{names['prochain']}", new_callable=AsyncMock,
            return_value="[PROCHAIN TIRAGE]\nDate du prochain tirage : (mock)"))
        mocks["tirage"] = st.enter_context(patch(f"{mod}.{names['tirage']}", side_effect=_tirage(game)))
        mocks["stats"] = st.enter_context(patch(f"{mod}.get_numero_stats", new_callable=AsyncMock,
                                                side_effect=_stats))
        mocks["sql"] = st.enter_context(patch(f"{mod}.{names['sql']}", new_callable=AsyncMock,
                                              return_value="NO_SQL"))
        for fn in ("analyze_grille_for_chat", "get_classement_numeros", "get_comparaison_numeros",
                   "get_comparaison_with_period", "get_numeros_par_categorie", "get_pair_correlations",
                   "get_star_pair_correlations", "get_triplet_correlations", "get_single_pair",
                   "get_single_star_pair", "get_grid_numbers_stats"):
            with contextlib.suppress(AttributeError):
                mocks[fn] = st.enter_context(patch(f"{mod}.{fn}", new_callable=AsyncMock,
                                                   return_value=_DATA.get(fn)))
        st.enter_context(patch("engine.hybride_em.generate_grids", new_callable=AsyncMock, return_value=_GRID))
        st.enter_context(patch("engine.hybride.generate_grids", new_callable=AsyncMock, return_value=_GRID))
        kw = {} if lang is None else {"lang": lang}
        if game == "loto":
            from services.chat_pipeline import _prepare_chat_context as prep
            early, ctx = await prep(msg, [], "loto", MagicMock(), **kw)
        else:
            from services.chat_pipeline_em import _prepare_chat_context_em as prep
            early, ctx = await prep(msg, [], "accueil-em", MagicMock(), **kw)
    assert early is None, f"court-circuit inattendu : {early}"
    return ctx["_chat_meta"], mocks


# ═══════════════════════════════════════════════════════
# T1 — matrice de routage : 47 questions du smoke de Muse + #15
# ═══════════════════════════════════════════════════════
# (id, jeu, lang, message, phase attendue en 1.6.074, appel get_numero_stats attendu | None)

SMOKE = [
    ("T1-FR", "em", "fr", "Quand le numéro 31 est-il sorti pour la dernière fois à l'EuroMillions ?", "1", (31, "boule")),
    ("T1-EN", "em", "en", "When was number 31 last drawn in EuroMillions?", "1", (31, "boule")),
    ("T1-ES", "em", "es", "¿Cuándo salió el número 31 por última vez en el Euromillones?", "1", (31, "boule")),
    ("T1-PT", "em", "pt", "Quando foi a última vez que o número 31 saiu no Euromilhões?", "1", (31, "boule")),
    ("T1-DE", "em", "de", "Wann wurde die Nummer 31 zuletzt bei EuroMillions gezogen?", "1", (31, "boule")),
    ("T1-NL", "em", "nl", "Wanneer is nummer 31 voor het laatst getrokken bij EuroMillions?", "1", (31, "boule")),
    ("T2-FR", "em", "fr", "Quand est sortie l'étoile 12 pour la dernière fois à l'EuroMillions ?", "1", (12, "etoile")),
    ("T2-EN", "em", "en", "When was star 12 last drawn in EuroMillions?", "1", (12, "etoile")),
    ("T2-ES", "em", "es", "¿Cuándo salió la estrella 12 por última vez en el Euromillones?", "1", (12, "etoile")),
    ("T2-PT", "em", "pt", "Quando foi a última vez que a estrela 12 saiu no Euromilhões?", "1", (12, "etoile")),
    ("T2-DE", "em", "de", "Wann wurde der Stern 12 zuletzt bei EuroMillions gezogen?", "1", (12, "etoile")),
    ("T2-NL", "em", "nl", "Wanneer is ster 12 voor het laatst getrokken bij EuroMillions?", "1", (12, "etoile")),
    ("T3-FR", "em", "fr", "Quel est le dernier tirage EuroMillions ?", "T", None),
    ("T3-EN", "em", "en", "What was the last EuroMillions draw?", "SQL", None),
    ("T3-ES", "em", "es", "¿Cuál fue el último sorteo de Euromillones?", "T", None),
    ("T3-PT", "em", "pt", "Qual foi o último sorteio do Euromilhões?", "T", None),
    ("T3-DE", "em", "de", "Was war die letzte EuroMillions-Ziehung?", "SQL", None),
    ("T3-NL", "em", "nl", "Wat was de laatste EuroMillions-trekking?", "SQL", None),
    ("T4-FR", "em", "fr", "C'est quand le prochain tirage EuroMillions ?", "0-bis", None),
    ("T4-EN", "em", "en", "When is the next EuroMillions draw?", "0-bis", None),
    ("T4-ES", "em", "es", "¿Cuándo es el próximo sorteo de Euromillones?", "0-bis", None),
    ("T4-PT", "em", "pt", "Quando é o próximo sorteio do Euromilhões?", "0-bis", None),
    ("T4-DE", "em", "de", "Wann ist die nächste EuroMillions-Ziehung?", "0-bis", None),
    ("T4-NL", "em", "nl", "Wanneer is de volgende EuroMillions-trekking?", "0-bis", None),
    ("R1", "em", "fr", "Dernière sortie du 4 ?", "1", (4, "boule")),
    ("R2", "em", "fr", "le numéro 4", "1", (4, "boule")),
    ("R3", "em", "fr", "l'étoile 4", "1", (4, "etoile")),
    ("T5-FR", "loto", None, "Quand le numéro 34 est-il sorti pour la dernière fois au Loto ?", "1", (34, "principal")),
    ("T5-EN", "loto", None, "When was number 34 last drawn in the Loto?", "SQL", None),
    ("T5-ES", "loto", None, "¿Cuándo salió el número 34 por última vez en la Loto?", "SQL", None),
    ("T5-PT", "loto", None, "Quando foi a última vez que o número 34 saiu no Loto?", "SQL", None),
    ("T5-DE", "loto", None, "Wann wurde die Nummer 34 zuletzt beim Loto gezogen?", "SQL", None),
    ("T5-NL", "loto", None, "Wanneer is nummer 34 voor het laatst getrokken bij de Loto?", "SQL", None),
    ("T6-FR", "loto", None, "Quel est le dernier tirage du Loto ?", "T", None),
    ("T6-EN", "loto", None, "What was the last Loto draw?", "SQL", None),
    ("T6-ES", "loto", None, "¿Cuál fue el último sorteo de la Loto?", "T", None),
    ("T6-PT", "loto", None, "Qual foi o último sorteio do Loto?", "T", None),
    ("T6-DE", "loto", None, "Was war die letzte Loto-Ziehung?", "SQL", None),
    ("T6-NL", "loto", None, "Wat was de laatste Loto-trekking?", "SQL", None),
    ("T7-FR", "loto", None, "C'est quand le prochain tirage du Loto ?", "0-bis", None),
    ("T7-EN", "loto", None, "When is the next Loto draw?", "SQL", None),
    ("T7-ES", "loto", None, "¿Cuándo es el próximo sorteo de la Loto?", "SQL", None),
    ("T7-PT", "loto", None, "Quando é o próximo sorteio do Loto?", "SQL", None),
    ("T7-DE", "loto", None, "Wann ist die nächste Loto-Ziehung?", "SQL", None),
    ("T7-NL", "loto", None, "Wanneer is de volgende Loto-trekking?", "SQL", None),
    ("R4", "loto", None, "le numéro 7", "1", (7, "principal")),
    ("R5", "loto", None, "le numéro 33", "1", (33, "principal")),
    ("#15", "em", "en", "When was number 4 last drawn?", "1", (4, "boule")),
]


def test_t1_smoke_matrix_size():
    assert len(SMOKE) == 48  # 47 questions du smoke + #15


@pytest.mark.asyncio
@pytest.mark.parametrize("qid,game,lang,msg,phase,stats_args", SMOKE, ids=[s[0] for s in SMOKE])
async def test_t1_smoke_routing(qid, game, lang, msg, phase, stats_args):
    meta, mocks = await _run(game, msg, lang)
    enrich = meta["enrichment_context"] or ""
    assert meta["phase"] == phase, f"{qid} : phase {meta['phase']!r} au lieu de {phase!r}"
    if stats_args is None:
        mocks["stats"].assert_not_called()
        assert "[DONNÉES TEMPS RÉEL" not in enrich
    else:
        mocks["stats"].assert_awaited_once_with(*stats_args)
        assert "[DONNÉES TEMPS RÉEL" in enrich
        assert "[RÉSULTAT TIRAGE" in enrich, f"{qid} : dernier tirage absent (Phase 1 enrichie)"
    if phase == "0-bis":
        assert enrich.startswith("[PROCHAIN TIRAGE]")


# ═══════════════════════════════════════════════════════
# T1b — CF-4 : FR inchangé, non-bascule
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("msg", [s[3] for s in SMOKE if s[1] == "em" and s[2] == "fr"]
                         + ["When was number 31 last drawn?", "le numéro 4", "number 7"])
async def test_t1b_fr_uses_config_detector_unchanged(msg):
    from services.chat_detectors_em import _detect_numero_em
    spy = {}
    await _run("em", msg, "fr", spy_cfg=spy)
    assert spy["cfg"]["detect_numero"] is _detect_numero_em  # lang="fr" : détecteur de la config, intact


@pytest.mark.asyncio
async def test_t1b_cfg_not_shared_between_langs():
    """Un tour EN (fonction liée) ne contamine pas le tour FR suivant : config EM neuve à chaque requête."""
    from services.chat_detectors_em import _detect_numero_em
    spy_en, spy_fr = {}, {}
    await _run("em", "When was number 31 last drawn in EuroMillions?", "en", spy_cfg=spy_en)
    await _run("em", "Quand le numéro 31 est-il sorti pour la dernière fois à l'EuroMillions ?", "fr", spy_cfg=spy_fr)
    assert spy_en["cfg"]["detect_numero"] is not _detect_numero_em  # EN : fonction liée
    assert spy_fr["cfg"]["detect_numero"] is _detect_numero_em      # FR : objet d'origine
    assert spy_fr["cfg"] is not spy_en["cfg"]


@pytest.mark.asyncio
async def test_t1b_non_fr_wraps_detector_but_star_stays_priority():
    spy = {}
    await _run("em", "When was star 12 last drawn in EuroMillions?", "en", spy_cfg=spy)
    assert spy["cfg"]["detect_numero"]("When was star 12 last drawn in EuroMillions?") == (12, "etoile")
    assert spy["cfg"]["detect_numero"]("When was number 31 last drawn in EuroMillions?") == (31, "boule")


@pytest.mark.parametrize("msg", [
    "generate a grid with number 7", "number 7 vs number 12", "compare number 7 and number 12",
    "Generiere eine Kombination mit der Nummer 7", "Nummer 7 gegen Nummer 12",
    "vergleiche die Nummer 7 und die Nummer 12", "When did star number 12 last come out?",
    "¿Cuándo salió la estrella número 12 por última vez?", "Wann kam Stern Nummer 12 zuletzt?",
    "Wanneer viel ster nummer 12 het laatst?", "numbers 7 and 12", "die Nummern 7 und 12",
])
def test_t1b_hors_fr_detector_no_new_detection(msg):
    from services.chat_detectors_em_intent import _detect_numero_em_hors_fr
    assert _detect_numero_em_hors_fr(msg) == (None, None)


@pytest.mark.parametrize("msg,num", [
    ("When was number 31 last drawn in EuroMillions?", 31), ("¿Cuándo salió el número 31?", 31),
    ("Quando saiu o numero 31?", 31), ("Wann wurde die Nummer 31 gezogen?", 31),
    ("Wann wurde die Zahl 4 zuletzt gezogen?", 4), ("Wanneer is nummer 4 getrokken?", 4),
])
def test_t1b_hors_fr_detector_explicit_forms(msg, num):
    from services.chat_detectors_em_intent import _detect_numero_em_hors_fr
    assert _detect_numero_em_hors_fr(msg) == (num, "boule")


def test_t1b_hors_fr_detector_bounds_and_dates():
    from services.chat_detectors_em_intent import _detect_numero_em_hors_fr
    assert _detect_numero_em_hors_fr("number 51") == (None, None)
    assert _detect_numero_em_hors_fr("number 0") == (None, None)
    assert _detect_numero_em_hors_fr("number 7 on 13/11/2026") == (7, "boule")  # date masquée


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,msg,not_phase", [
    ("en", "generate a grid with number 7", "1"),
    ("de", "Generiere eine Kombination mit der Nummer 7", "1"),
    ("en", "number 7 vs number 12", "1"),
    ("de", "Nummer 7 gegen Nummer 12", "1"),
    ("en", "top 5 numbers", "1"),
    ("de", "die 10 häufigsten Zahlen", "1"),
    ("en", "Is number 7 among the most drawn numbers?", "1"),  # Phase 3 passe avant la Phase 1
])
async def test_t1b_non_bascule_phase1(lang, msg, not_phase):
    meta, mocks = await _run("em", msg, lang)
    assert meta["phase"] != not_phase, f"{msg!r} a basculé en Phase {not_phase}"
    mocks["stats"].assert_not_called()


# ═══════════════════════════════════════════════════════
# T2 — CF-1 : contrôle 2, étoiles à deux chiffres
# ═══════════════════════════════════════════════════════

def _draw_fn(d, boules, etoiles):
    async def _f(target):
        if target == d:
            return {"date": d, "boules": boules, "etoiles": etoiles}
        return None
    return _f


_D1311 = date(2026, 11, 13)
_B1311 = [16, 27, 32, 41, 45]

T2_VERBATIM = [
    ("T2-ES", "¡Vaya, la estrella 12! Salió el 13 de noviembre de 2026, hace solo 1 sorteo. 🔥 Es una estrella "
              "bastante popular, con 128 apariciones en 732 sorteos.", "es"),
    ("T2-PT", "Ora, ora! A estrela 12, um clássico! Ela saiu no sorteio de 13 de novembro de 2026, há apenas 1 "
              "sorteio. É um número bem quente, com 128 aparições em 732 sorteios.", "pt"),
    ("T2-DE", "Also, der Stern 12 wurde zuletzt am 13. November 2026 gezogen! 🔥 Das ist ja erst eine Ziehung her. "
              "Er ist mit 128 Auftritten auf 732 Ziehungen auch eine der Top-Sterne.", "de"),
    ("T2-NL", "Ster 12 is heel recent getrokken, op 13 november 2026! 🔥 Dat was in de trekking met de nummers "
              "16 - 27 - 32 - 41 - 45 en sterren 2 - 12.", "nl"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("qid,text,lang", T2_VERBATIM, ids=[t[0] for t in T2_VERBATIM])
async def test_t2_verbatim_smoke_not_blocked(qid, text, lang):
    from services.chat_pipeline_gemini import _recheck_phase0_draw_accuracy
    r = await _recheck_phase0_draw_accuracy(text, "1", lang, "[T]",
                                            get_tirage_fn=_draw_fn(_D1311, _B1311, [2, 12]), game="em")
    assert r is None


@pytest.mark.asyncio
async def test_t2_verbatim_r3_not_blocked():
    from services.chat_pipeline_gemini import _recheck_phase0_draw_accuracy
    text = ("Ah, l'étoile 4 ! 🤔 Elle est sortie 103 fois sur les 732 tirages analysés, soit 14.07% du temps. "
            "Elle s'est montrée pour la dernière fois le 16 octobre 2026, avec les numéros 7-15-16-22-35 et "
            "l'étoile 6. Ça fait 9 tirages qu'elle se fait désirer !")
    r = await _recheck_phase0_draw_accuracy(text, "1", "fr", "[T]", game="em",
                                            get_tirage_fn=_draw_fn(date(2026, 10, 16), [7, 15, 16, 22, 35], [4, 6]))
    assert r is None


def _rebuilt(star, lang):
    if lang == "fr":
        return (f"L'étoile {star} est sortie pour la dernière fois le 13 novembre 2026 : "
                f"16 - 27 - 32 - 41 - 45, étoiles 2 et {star}. Écart : 1 tirage.")
    return (f"Star {star} was last drawn on 13 November 2026: 16 - 27 - 32 - 41 - 45, "
            f"stars 2 and {star}. Gap: 1 draw.")


@pytest.mark.asyncio
@pytest.mark.parametrize("star", [10, 11, 12])
@pytest.mark.parametrize("lang", ["fr", "en"])
async def test_t2_rebuilt_two_digit_star_not_blocked(star, lang):
    from services.chat_pipeline_gemini import _recheck_phase0_draw_accuracy
    r = await _recheck_phase0_draw_accuracy(_rebuilt(star, lang), "1", lang, "[T]", game="em",
                                            get_tirage_fn=_draw_fn(_D1311, _B1311, [2, star]))
    assert r is None


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["fr", "en"])
@pytest.mark.parametrize("cited,real", [((2, 12), (3, 12)), ((2, 11), (2, 12)), ((5, 9), (2, 12))])
async def test_t2_really_wrong_pair_still_blocked(lang, cited, real):
    from services.chat_pipeline_gemini import _recheck_phase0_draw_accuracy
    text = (f"L'étoile 12 est sortie le 13 novembre 2026 : 16 - 27 - 32 - 41 - 45, étoiles {cited[0]} et "
            f"{cited[1]}." if lang == "fr" else
            f"Star 12 was drawn on 13 November 2026: 16 - 27 - 32 - 41 - 45, stars {cited[0]} and {cited[1]}.")
    r = await _recheck_phase0_draw_accuracy(text, "1", lang, "[T]", game="em",
                                            get_tirage_fn=_draw_fn(_D1311, _B1311, list(real)))
    assert r is not None


@pytest.mark.parametrize("text,pair", [
    ("étoiles 2 et 12", ("2", "12")), ("étoiles 2 - 12", ("2", "12")), ("stars 2 and 12", ("2", "12")),
    ("stars: 2 - 12", ("2", "12")), ("estrellas 2 y 12", ("2", "12")), ("estrelas 2 e 12", ("2", "12")),
    ("Sterne 2 und 12", ("2", "12")), ("sterren 2 en 12", ("2", "12")), ("⭐ 2 et 12", ("2", "12")),
    ("Étoiles : 10 - 11", ("10", "11")), ("star 3, star 8", ("3", "8")), ("étoile 3 et 8", ("3", "8")),
    ("l'étoile 12 est sortie, étoiles 2 et 12", ("2", "12")),
    ("Star 12, 1 draw ago. Stars 2 and 12.", ("2", "12")),
    ("Stern 12 wurde gezogen: Sterne 2 und 12", ("2", "12")),
])
def test_t2_extract_cited_stars_forms(text, pair):
    from services.chat_pipeline_gemini import _extract_cited_stars
    assert _extract_cited_stars(text) == pair


@pytest.mark.parametrize("text", ["l'étoile 12 est sortie", "Star 12, 1 draw ago", "Stern 12",
                                  "étoiles 2 et 128 apparitions", "stars 13 and 14"])
def test_t2_extract_cited_stars_none(text):
    from services.chat_pipeline_gemini import _extract_cited_stars
    assert _extract_cited_stars(text) is None


@pytest.mark.asyncio
async def test_t2_strict_buffer_end_to_end_not_blocked():
    """Buffer strict (prod) : la réponse juste « étoile 12 » n'est plus remplacée par le message strict."""
    from services import chat_pipeline_gemini as g
    text = _rebuilt(12, "fr")

    async def _stream(*args, **kwargs):
        yield text

    ctx = {"mode": "decouverte", "insult_prefix": "", "_http_client": None, "gem_api_key": None,
           "system_prompt": "sys", "contents": [], "history": [], "_strict_hallucination_block": True,
           "_strict_stat_check": False, "_get_tirage_fn": _draw_fn(_D1311, _B1311, [2, 12]), "_game": "em",
           "_chat_meta": {"phase": "1", "lang": "fr", "enrichment_context": (
               "[DONNÉES TEMPS RÉEL — CHIFFRES EXACTS - Numéro étoile 12]\n[/DONNÉES TEMPS RÉEL]\n\n"
               "[RÉSULTAT TIRAGE — CHIFFRES EXACTS, NE PAS MODIFIER]\n"
               "Tirage du 13 novembre 2026 : 16 - 27 - 32 - 41 - 45 | Étoiles : 2 - 12\n[/RÉSULTAT TIRAGE]")}}
    with patch.object(g, "log_from_meta"):
        events = [e async for e in g.stream_and_respond(ctx, "fb", "[T]", "em", "fr", "q", "accueil-em",
                                                        call_type="chat_em", stream_fn=_stream)]
    body = "".join(events)
    assert "certitude" not in body and '"source": "fallback"' not in body
    assert "16 - 27 - 32 - 41 - 45" in body


# ═══════════════════════════════════════════════════════
# T3 — CF-7 : filtres de sortie
# ═══════════════════════════════════════════════════════

@pytest.mark.parametrize("leak", [
    "[REALTIMEGEGEVENS - Numéro 31] frequentie: 120",
    "[REALTIMEGEGEVENS - Numéro 31]\nfrequentie: 120\nlaatste_verschijning: 2026-11-10",
])
def test_t3_t1_nl_translated_header_removed(leak):
    from services.base_chat_utils import _clean_response
    out = _clean_response(leak, "nl")
    assert "REALTIMEGEGEVENS" not in out and "[" not in out
    assert "frequentie: 120" in out  # limite assumée : le contenu qui suit n'est pas retiré (remède : CF-4)


@pytest.mark.parametrize("tag", [
    "[REAL-TIME DATA]", "[Draw result - 13/11]", "[SQL RESULT]", "[ECHTZEITDATEN]", "[ZIEHUNGSERGEBNIS]",
    "[SQL-ERGEBNIS]", "[DATOS EN TIEMPO REAL]", "[resultado del sorteo]", "[DADOS EM TEMPO REAL]",
    "[TREKKINGSRESULTAAT]", "[SQL-RESULTAAT]", "[Página: accueil-em]", "[Gebruikersvraag]",
])
def test_t3_translated_tags_removed(tag):
    from services.base_chat_utils import _clean_response
    assert _clean_response(f"{tag} Bonjour", "fr").strip() == "Bonjour"  # espace de bord : comme les tags FR


@pytest.mark.parametrize("keep", [
    "Nummer [N]? Net getrokken! 🔥", "On est mardi 26 mai 2026 !", "Voir [la page Statistiques]",
    "[COMPARISONS] de grilles", "Le [RANKINGS] reste un mot",
])
def test_t3_witnesses_kept(keep):
    from services.base_chat_utils import _clean_response
    assert _clean_response(keep, "fr") == keep


@pytest.mark.parametrize("leak,rest", [
    ("Datum: 2026-11-21\nJour: Vrijdag\nDe volgende trekking is vrijdag.", "De volgende trekking is vrijdag."),
    ("Dag: vrijdag\nDatum: 2026-11-20\nTijd: 21:00:00\nDe volgende EuroMillions-trekking is al morgen…",
     "De volgende EuroMillions-trekking is al morgen…"),
    ("Date : samedi 22 novembre 2026\nJour : samedi\nLe prochain tirage du Loto est samedi.",
     "Le prochain tirage du Loto est samedi."),
])
def test_t3_anchor_label_lines_removed(leak, rest):
    from services.chat_pipeline_gemini import _strip_temporal_anchor_leak
    assert _strip_temporal_anchor_leak(leak) == rest


@pytest.mark.parametrize("keep", [
    "On est mardi 26 mai 2026 ! Le prochain tirage est vendredi.",
    "Le tirage du 13 novembre 2026 : 16 - 27 - 32 - 41 - 45.",
    "Datum: 2026-11-21",                                  # ligne seule : jamais tout le texte
    "Datum van de volgende trekking is vrijdag 20 november, om 21 uur.\nTot dan!",  # phrase, pas étiquette
    "Hora: es la hora de jugar con los números calientes de esta semana, ¿vale?\nOk",  # valeur trop longue
])
def test_t3_anchor_witnesses_kept(keep):
    from services.chat_pipeline_gemini import _strip_temporal_anchor_leak
    assert _strip_temporal_anchor_leak(keep) == keep


def test_t3_anchor_max_three_lines():
    from services.chat_pipeline_gemini import _strip_temporal_anchor_leak
    txt = "Dag: vrijdag\nDatum: 2026-11-20\nTijd: 21:00\nData: x\nTekst."
    assert _strip_temporal_anchor_leak(txt) == "Data: x\nTekst."


# ═══════════════════════════════════════════════════════
# T4 — CF-5 : Phase 0-bis EM 6 langues, _NEXT_KW_RE
# ═══════════════════════════════════════════════════════

T4_YES = [s[3] for s in SMOKE if s[0].startswith("T4-")] + [
    "What is the date of the next draw?", "next draw?", "¿Cuándo es la próxima extracción?",
    "fecha del próximo sorteo", "Qual é a data do próximo sorteio?", "Wann findet die nächste Ziehung statt?",
    "Wann ist der nächsten Ziehung?", "Wanneer is de volgende trekking?",
]
# T1-FR / T2-FR (« Quand … à l'EuroMillions ? ») sont captés par le motif FR historique (« quand … euromillions »)
# depuis V82, puis neutralisés par la garde 1.6.073 (critère a) → Phase 1 : hors périmètre, cf. test dédié.
T4_NO = [s[3] for s in SMOKE if s[1] == "em" and (s[0][:2] == "T3" or (s[0][:2] in ("T1", "T2")
                                                                    and s[2] != "fr"))] + [
    "When was number 4 last drawn?", "next time I play I will pick 7",
]


@pytest.mark.parametrize("msg", T4_YES)
def test_t4_0bis_detected(msg):
    from services.chat_detectors_em_intent import _detect_prochain_tirage_em
    assert _detect_prochain_tirage_em(msg)


@pytest.mark.parametrize("msg", T4_NO)
def test_t4_0bis_not_detected(msg):
    from services.chat_detectors_em_intent import _detect_prochain_tirage_em
    assert not _detect_prochain_tirage_em(msg)


@pytest.mark.parametrize("qid", ["T1-FR", "T2-FR"])
def test_t4_fr_historical_capture_unchanged(qid):
    """Préexistant (V82) : le motif FR capte « Quand … EuroMillions ? » ; le lot 074 n'y touche pas."""
    from services.chat_detectors_em_intent import _detect_prochain_tirage_em
    msg = next(s[3] for s in SMOKE if s[0] == qid)
    assert _detect_prochain_tirage_em(msg)  # puis garde 073 critère a → Phase 1 (cf. test_t1_smoke_routing)


@pytest.mark.parametrize("word,hit", [
    ("prochain", True), ("next", True), ("próximo", True), ("próxima", True), ("nächste", True),
    ("nächsten", True), ("nächster", True), ("volgende", True), ("volgend", True), ("prochaine", False),
])
def test_t4_next_kw_inflected_without_prochaine(word, hit):
    from services.base_chat_detect_temporal import _NEXT_KW_RE
    assert bool(_NEXT_KW_RE.search(f"le {word} tirage")) is hit


# ═══════════════════════════════════════════════════════
# T5 — CF-3 : paires / triplets avant « top N »
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("game,lang,msg,tag", [
    ("loto", None, "top 5 des paires", "[CORRÉLATIONS DE PAIRES"),
    ("loto", None, "Quel est le top 5 des paires ?", "[CORRÉLATIONS DE PAIRES"),
    ("loto", None, "les 5 paires les plus fréquentes", "[CORRÉLATIONS DE PAIRES"),
    ("loto", None, "top 3 des triplets", "[CORRÉLATIONS DE TRIPLETS"),
    ("em", "fr", "top 5 des paires", "[CORRÉLATIONS DE PAIRES"),
    ("em", "en", "top 5 pairs", "[CORRÉLATIONS DE PAIRES"),
    ("em", "es", "top 5 de las parejas", "[CORRÉLATIONS DE PAIRES"),
    ("em", "de", "top 5 der Paare", "[CORRÉLATIONS DE PAIRES"),
])
async def test_t5_pairs_go_to_phase_p(game, lang, msg, tag):
    meta, mocks = await _run(game, msg, lang)
    assert meta["phase"] == "P"
    assert tag in meta["enrichment_context"]
    mocks["get_classement_numeros"].assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("game,lang,msg", [
    ("loto", None, "top 5 des numéros"), ("loto", None, "top 5 numbers"),
    ("loto", None, "les numéros les plus fréquents"), ("em", "fr", "top 5 des numéros"),
    ("em", "en", "top 5 numbers"),
])
async def test_t5_number_rankings_stay_phase_3(game, lang, msg):
    meta, _ = await _run(game, msg, lang)
    assert meta["phase"] == "3"
    assert "[CLASSEMENT" in meta["enrichment_context"]


# ═══════════════════════════════════════════════════════
# T6 — version
# ═══════════════════════════════════════════════════════

def test_t6_version_config():
    from config.version import APP_VERSION, VERSION_DATE
    assert tuple(int(p) for p in APP_VERSION.split(".")) >= (1, 6, 74)  # plancher (lot 1.6.075)
    assert VERSION_DATE >= "2026-11-19"


def test_t6_api_version():
    env = patch.dict(os.environ, {"DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
                                  "EM_PUBLIC_ACCESS": "true"})
    with env, patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None), \
         patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None):
        import importlib
        import rate_limit as rl_mod
        importlib.reload(rl_mod)
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        rl_mod.limiter.reset()
        resp = TestClient(main_mod.app, raise_server_exceptions=False).get("/api/version")
    assert resp.status_code == 200
    body = resp.json()
    assert tuple(int(p) for p in body["version"].split(".")) >= (1, 6, 74)  # plancher (lot 1.6.075)
    assert body["date"] >= "2026-11-19"


# ═══════════════════════════════════════════════════════
# T7 — D3 : ex aequo des paires / paires d'étoiles / triplets
# ═══════════════════════════════════════════════════════

_TIE_NOTE = ("Ex aequo : les lignes de même compte partagent le même rang. "
             "Cite-les toutes comme ex aequo, sans en privilégier une.")
_IMPORTANT = "IMPORTANT : Le hasard reste souverain. Ces corrélations sont purement statistiques."


def _svc_capture(cfg, rows):
    """BaseStatsService à connexion mockée ; renvoie (svc, cursor) pour lire le SQL exécuté."""
    from services.base_stats import BaseStatsService
    svc = BaseStatsService(cfg)
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value={"total": 100})
    cursor.fetchall = AsyncMock(return_value=rows)
    cursor.execute = AsyncMock()
    conn = MagicMock()
    conn.cursor = AsyncMock(return_value=cursor)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    svc._get_connection = MagicMock(return_value=ctx)
    return svc, cursor


def _order_by(cursor):
    sql = cursor.execute.call_args_list[-1].args[0]
    return sql[sql.index("ORDER BY"):]


# ── O1 : SQL exécuté ──

@pytest.mark.asyncio
@pytest.mark.parametrize("game,fn,order,expected", [
    ("loto", "get_pair_correlations", "hot", "ORDER BY pair_count DESC, num_a ASC, num_b ASC LIMIT %s"),
    ("loto", "get_pair_correlations", "cold", "ORDER BY pair_count ASC, num_a ASC, num_b ASC LIMIT %s"),
    ("em", "get_pair_correlations", "hot", "ORDER BY pair_count DESC, num_a ASC, num_b ASC LIMIT %s"),
    ("em", "get_pair_correlations", "cold", "ORDER BY pair_count ASC, num_a ASC, num_b ASC LIMIT %s"),
    ("em", "get_star_pair_correlations", "hot", "ORDER BY pair_count DESC, num_a ASC, num_b ASC LIMIT %s"),
    ("em", "get_star_pair_correlations", "cold", "ORDER BY pair_count ASC, num_a ASC, num_b ASC LIMIT %s"),
    ("loto", "get_triplet_correlations", None,
     "ORDER BY triplet_count DESC, num_a ASC, num_b ASC, num_c ASC LIMIT %s"),
    ("em", "get_triplet_correlations", None,
     "ORDER BY triplet_count DESC, num_a ASC, num_b ASC, num_c ASC LIMIT %s"),
])
async def test_t7_o1_sql_order_by(game, fn, order, expected):
    from services.em_stats_service import EM_CONFIG
    from services.stats_service import LOTO_CONFIG
    svc, cursor = _svc_capture(LOTO_CONFIG if game == "loto" else EM_CONFIG, [])
    kw = {"top_n": 50} if order is None else {"top_n": 50, "order": order}
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await getattr(svc, fn)(**kw)
    assert result is not None
    assert _order_by(cursor) == expected
    assert cursor.execute.call_args_list[-1].args[1][-1] == 50


@pytest.mark.asyncio
async def test_t7_o1_rank_field_still_position():
    from services.stats_service import LOTO_CONFIG
    rows = [{"num_a": 4, "num_b": 22, "pair_count": 20}, {"num_a": 17, "num_b": 30, "pair_count": 20},
            {"num_a": 7, "num_b": 11, "pair_count": 19}]
    svc, _ = _svc_capture(LOTO_CONFIG, rows)
    with patch("services.base_stats.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("services.base_stats.cache_set", new_callable=AsyncMock):
        result = await svc.get_pair_correlations(top_n=3)
    assert [p["rank"] for p in result["pairs"]] == [1, 2, 3]


# ── O2 : sélection et format ──

def _pairs(spec, total=980):
    return {"total_draws": total, "window": None,
            "pairs": [{"num_a": a, "num_b": b, "count": c, "percentage": p, "rank": i}
                      for i, (a, b, c, p) in enumerate(spec, 1)]}


_NO_TIE = [(4, 22, 20, 2.0), (17, 30, 19, 1.9), (7, 11, 18, 1.8), (26, 42, 17, 1.7), (31, 40, 16, 1.6)]

# Blocs de 1.6.074 initial (commit 4ee4a9b), figés : sans ex aequo, le bloc ne doit pas bouger d'un octet.
_V0_PAIRS_LOTO = (
    "[CORRÉLATIONS DE PAIRES — Numéros principaux]\n"
    "Total tirages analysés : 980\n"
    "1. 4 + 22 → 20 fois (2.0%)\n"
    "2. 17 + 30 → 19 fois (1.9%)\n"
    "3. 7 + 11 → 18 fois (1.8%)\n"
    "4. 26 + 42 → 17 fois (1.7%)\n"
    "5. 31 + 40 → 16 fois (1.6%)\n"
    + _IMPORTANT
)
_V0_STARS = (
    "[CORRÉLATIONS DE PAIRES — Étoiles]\n"
    "Total tirages analysés : 980\n"
    "1. ⭐4 + ⭐22 → 20 fois (2.0%)\n"
    "2. ⭐17 + ⭐30 → 19 fois (1.9%)\n"
    "3. ⭐7 + ⭐11 → 18 fois (1.8%)\n"
    "4. ⭐26 + ⭐42 → 17 fois (1.7%)\n"
    "5. ⭐31 + ⭐40 → 16 fois (1.6%)"
)
_V0_TRIPLETS_EM = (
    "[CORRÉLATIONS DE TRIPLETS — Boules EuroMillions]\n"
    "Total tirages analysés : 980\n"
    "1. 1 + 2 + 3 → 9 fois (0.9%)\n"
    "2. 4 + 5 + 6 → 8 fois (0.8%)\n"
    "3. 7 + 8 + 9 → 7 fois (0.7%)\n"
    "4. 10 + 11 + 12 → 6 fois (0.6%)\n"
    "5. 13 + 14 + 15 → 5 fois (0.5%)\n"
    + _IMPORTANT
)


def _triplets(counts):
    return {"total_draws": 980, "window": None,
            "triplets": [{"num_a": 3 * i + 1, "num_b": 3 * i + 2, "num_c": 3 * i + 3, "count": c,
                          "percentage": c / 10, "rank": i + 1} for i, c in enumerate(counts)]}


@pytest.mark.parametrize("extra", [0, 2, 45])
def test_t7_o2a_no_tie_block_identical(extra):
    """(a) aucun ex aequo au 5e rang : 5 lignes, bloc octet pour octet identique à 1.6.074 initial."""
    from services.chat_utils import _format_pairs_context
    from services.chat_utils_em import _format_star_pairs_context_em, _format_triplets_context_em
    spec = _NO_TIE + [(1, 2 + i, 15 - (i // 10), 0.5) for i in range(extra)]
    data = _pairs(spec)
    assert _format_pairs_context(data) == _V0_PAIRS_LOTO
    assert _format_star_pairs_context_em(data) == _V0_STARS
    assert _format_triplets_context_em(_triplets([9, 8, 7, 6, 5] + [4] * extra)) == _V0_TRIPLETS_EM
    assert _TIE_NOTE not in _format_pairs_context(data)


_D3_LOTO = [(4, 22, 20, 2.0), (17, 30, 20, 2.0), (7, 11, 19, 1.9), (13, 31, 18, 1.8), (26, 42, 18, 1.8),
            (31, 40, 18, 1.8), (1, 2, 17, 1.7), (3, 5, 17, 1.7)]


def test_t7_o2b_d3_loto():
    """(b) cas D3 Loto : 20, 20, 19, 18, 18, 18, 17… → 6 lignes, rangs 1, 1, 3, 4, 4, 4."""
    from services.chat_utils import _format_pairs_context
    block = _format_pairs_context(_pairs(_D3_LOTO))
    assert block == (
        "[CORRÉLATIONS DE PAIRES — Numéros principaux]\n"
        "Total tirages analysés : 980\n"
        "1. 4 + 22 → 20 fois (2.0%) (ex aequo)\n"
        "1. 17 + 30 → 20 fois (2.0%) (ex aequo)\n"
        "3. 7 + 11 → 19 fois (1.9%)\n"
        "4. 13 + 31 → 18 fois (1.8%) (ex aequo)\n"
        "4. 26 + 42 → 18 fois (1.8%) (ex aequo)\n"
        "4. 31 + 40 → 18 fois (1.8%) (ex aequo)\n"
        + _TIE_NOTE + "\n"
        + _IMPORTANT
    )


def test_t7_o2c_stars_smoke():
    """(c) étoiles du smoke : 20, 18, 17 ×5, 16… → 7 lignes, rangs 1, 2, 3, 3, 3, 3, 3 ; consigne en fin."""
    from services.chat_utils_em import _format_star_pairs_context_em
    spec = [(2, 10, 20, 2.7), (2, 8, 18, 2.5), (1, 10, 17, 2.3), (2, 6, 17, 2.3), (3, 9, 17, 2.3),
            (4, 12, 17, 2.3), (7, 11, 17, 2.3), (1, 2, 16, 2.2), (5, 6, 15, 2.0)]
    block = _format_star_pairs_context_em(_pairs(spec, total=732))
    assert block == (
        "[CORRÉLATIONS DE PAIRES — Étoiles]\n"
        "Total tirages analysés : 732\n"
        "1. ⭐2 + ⭐10 → 20 fois (2.7%)\n"
        "2. ⭐2 + ⭐8 → 18 fois (2.5%)\n"
        "3. ⭐1 + ⭐10 → 17 fois (2.3%) (ex aequo)\n"
        "3. ⭐2 + ⭐6 → 17 fois (2.3%) (ex aequo)\n"
        "3. ⭐3 + ⭐9 → 17 fois (2.3%) (ex aequo)\n"
        "3. ⭐4 + ⭐12 → 17 fois (2.3%) (ex aequo)\n"
        "3. ⭐7 + ⭐11 → 17 fois (2.3%) (ex aequo)\n"
        + _TIE_NOTE
    )


def test_t7_o2d_cap():
    """(d) 3 lignes à 9 puis 12 à 5 : 10 lignes listées + « Et 5 autres paires à 5 fois »."""
    from services.chat_utils import _format_pairs_context
    spec = [(1, 2 + i, 9, 0.9) for i in range(3)] + [(10, 11 + i, 5, 0.5) for i in range(12)] + [(30, 31, 4, 0.4)]
    lines = _format_pairs_context(_pairs(spec)).split("\n")
    listed = [ln for ln in lines if "→" in ln]
    assert len(listed) == 10
    assert [ln.split(".")[0] for ln in listed] == ["1"] * 3 + ["4"] * 7
    assert all(ln.endswith(" (ex aequo)") for ln in listed)
    assert lines[-3:] == ["Et 5 autres paires à 5 fois (ex aequo, non listées).", _TIE_NOTE, _IMPORTANT]


def test_t7_o2e_at_least():
    """(e) 50 lignes toutes au compte de la 5e : « au moins »."""
    from services.chat_utils import _format_pairs_context
    spec = [(1 + i // 49, 2 + i % 49, 7, 0.7) for i in range(50)]
    lines = _format_pairs_context(_pairs(spec)).split("\n")
    assert len([ln for ln in lines if "→" in ln]) == 10
    assert "Et au moins 40 autres paires à 7 fois (ex aequo, non listées)." in lines


def test_t7_o2_singular_and_triplets_wording():
    from services.chat_utils import _format_pairs_context, _format_triplets_context
    spec = [(1, 2 + i, 9 - i, 0.9) for i in range(4)] + [(20, 21 + i, 3, 0.3) for i in range(7)]
    assert "Et 1 autre paire à 3 fois (ex aequo, non listées)." in _format_pairs_context(_pairs(spec))
    block = _format_triplets_context(_triplets([9, 9, 8, 7, 6, 6, 6]))
    assert "1. 1 + 2 + 3 → 9 fois (0.9%) (ex aequo)" in block
    assert "5. 13 + 14 + 15 → 6 fois (0.6%) (ex aequo)" in block
    assert "5. 19 + 20 + 21 → 6 fois (0.6%) (ex aequo)" in block
    assert _TIE_NOTE + "\n" + _IMPORTANT in block
    many = _format_triplets_context(_triplets([9] * 13))
    assert "Et 3 autres triplets à 9 fois (ex aequo, non listés)." in many


def test_t7_o2_input_not_mutated():
    """Les données (partagées avec le cache) ne sont pas modifiées par le formateur."""
    import copy
    from services.chat_utils import _format_pairs_context
    data = _pairs(_D3_LOTO)
    before = copy.deepcopy(data)
    _format_pairs_context(data)
    assert data == before


# ── O2 : pipeline réel (base et Gemini mockés) ──

@pytest.mark.asyncio
@pytest.mark.parametrize("game,lang,msg", [
    ("loto", None, "top 5 des paires"),
    ("em", "en", "top 5 pairs"),
])
async def test_t7_pipeline_pairs_with_ties(monkeypatch, game, lang, msg):
    monkeypatch.setitem(_DATA, "get_pair_correlations", _pairs(_D3_LOTO))
    stars = [(2, 10, 20, 2.7), (2, 8, 18, 2.5), (1, 10, 17, 2.3), (2, 6, 17, 2.3), (3, 9, 17, 2.3),
             (4, 12, 17, 2.3), (7, 11, 17, 2.3), (1, 2, 16, 2.2)]
    monkeypatch.setitem(_DATA, "get_star_pair_correlations", _pairs(stars, total=732))
    meta, mocks = await _run(game, msg, lang)
    assert meta["phase"] == "P"
    ctx = meta["enrichment_context"]
    mocks["get_pair_correlations"].assert_awaited_once_with(top_n=50)
    assert "1. 17 + 30 → 20 fois (2.0%) (ex aequo)" in ctx
    assert "3. 7 + 11 → 19 fois (1.9%)\n" in ctx
    assert "4. 31 + 40 → 18 fois (1.8%) (ex aequo)" in ctx
    assert "1 + 2 → 17" not in ctx
    assert _TIE_NOTE + "\n" + _IMPORTANT in ctx
    if game == "em":
        mocks["get_star_pair_correlations"].assert_awaited_once_with(top_n=50)
        assert "3. ⭐7 + ⭐11 → 17 fois (2.3%) (ex aequo)" in ctx
        assert ctx.endswith(_TIE_NOTE)
        assert "⭐1 + ⭐2" not in ctx


@pytest.mark.asyncio
async def test_t7_pipeline_triplets_with_ties(monkeypatch):
    monkeypatch.setitem(_DATA, "get_triplet_correlations", _triplets([9, 8, 7, 6, 5, 5, 4]))
    meta, mocks = await _run("loto", "top 3 des triplets")
    assert meta["phase"] == "P"
    mocks["get_triplet_correlations"].assert_awaited_once_with(top_n=50)
    ctx = meta["enrichment_context"]
    assert "5. 13 + 14 + 15 → 5 fois (0.5%) (ex aequo)" in ctx
    assert "5. 16 + 17 + 18 → 5 fois (0.5%) (ex aequo)" in ctx
    assert "4. 10 + 11 + 12 → 6 fois (0.6%)\n" in ctx
    assert "19 + 20 + 21" not in ctx
    assert _TIE_NOTE + "\n" + _IMPORTANT in ctx
