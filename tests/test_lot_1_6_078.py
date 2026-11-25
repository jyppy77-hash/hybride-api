"""Lot 1.6.078 (Release 1.6.078, 26/11/2026 ; audit P1 du 24/11, décisions D1-D10).

  T-A  équivalence flux == _clean_response(texte entier) sur un corpus d'auto-présentations (6 langues, tags /
       CF-7 / CJK en début de ligne, blancs et \\n après la ponctuation, préfixes ambigus) : découpages aléatoires
       (graine fixe), caractère par caractère, une coupe à chaque position, coupes ciblées ;
  T-B  cas épinglés de l'audit (A1.4) : FR-1, FR-2, FR-4, EN-1, EN-3, FR-5, DE-1 ;
  T-C  latence : aucune rétention pour une ligne qui ne commence pas par un des 7 verbes ;
  T-D  plafond 200 caractères (risque 2) : libération sans anti-réintro, rien de perdu, indépendant du découpage ;
  T-E  stream_and_respond strict / non strict : texte affiché == texte entier nettoyé == response_preview ;
  T-F  flush et exception pendant la rétention ;
  T-G  relance 429 de la génération SQL (Loto + EM) : horloge, jitter et attente figés ;
  T-H  chat_log : error_detail = "SqlVertex429", is_error inchangé ;
  T-I  ordinaux EM (6 langues, rendu Jinja), « 1er » Loto ;
  T-J  séparateurs : toLocaleString avec la locale de la page.
Aucun appel réel DB / Vertex.
"""

import ast
import asyncio
import json
import logging
import os
import random
import re
import time
from contextlib import asynccontextmanager, contextmanager
from itertools import combinations, pairwise
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

with patch.dict(os.environ, {"DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb"}):
    import services.base_chat_sql as bcs
    import services.chat_pipeline_gemini as cpg
    import services.chat_pipeline_shared as cps
    import services.chat_sql as chat_sql
    import services.chat_sql_em as chat_sql_em
    from services.base_chat_utils import (
        _REINTRO_HOLD_CAP, _REINTRO_RE, _REINTRO_SUBJECTS, _REINTRO_VERBS, StreamBuffer, _clean_response,
    )

ROOT = Path(__file__).resolve().parent.parent
LANGS = ("fr", "en", "es", "pt", "de", "nl")
_U2019_ESC = chr(92) + "u2019"  # les 6 caractères de l'échappement regex écrit dans le motif (apostrophe typographique)


def _stream(chunks):
    buf = StreamBuffer()
    return "".join(buf.add_chunk(c) for c in chunks) + buf.flush()


# ═══════════════════════════════════════════════════════════════════════
# Motif ↔ listes de formes (StreamBuffer ne décide jamais sans _REINTRO_RE)
# ═══════════════════════════════════════════════════════════════════════

def test_reintro_pattern_unchanged():
    assert _REINTRO_RE.pattern == (
        r'(?:^|\n\n?)'
        r'(?:Je suis|I am|I\'m|Soy|Sou|Ich bin|Ik ben)\s+'
        r"(?:HYBRIDE|l[\'" + _U2019_ESC + r"]assistant|the assistant|el asistente|o assistente|der Assistent|de assistent)"
        r'[^.!?\n]*[.!?]?\s*'
    )
    assert _REINTRO_RE.flags & re.IGNORECASE and _REINTRO_RE.flags & re.MULTILINE


def test_reintro_lists_match_pattern():
    verbs = re.search(r"\(\?:(Je suis[^)]*)\)", _REINTRO_RE.pattern).group(1).replace("\\'", "'").split("|")
    assert tuple(verbs) == _REINTRO_VERBS
    subj = re.search(r"\(\?:(HYBRIDE[^)]*)\)", _REINTRO_RE.pattern).group(1).split("|")
    expanded = []
    for s in subj:
        if s == "l[\\'" + _U2019_ESC + "]assistant":  # séquence d'échappement regex du motif
            expanded += ["l'assistant", "l’assistant"]
        else:
            expanded.append(s)
    assert tuple(expanded) == _REINTRO_SUBJECTS
    for v in _REINTRO_VERBS:
        for s in _REINTRO_SUBJECTS:
            assert _REINTRO_RE.fullmatch(f"{v} {s}.")


# ═══════════════════════════════════════════════════════════════════════
# T-A — équivalence flux == texte entier
# ═══════════════════════════════════════════════════════════════════════

_CORPUS = [
    "Je suis HYBRIDE, l'assistant IA de LotoIA. Le 7 est sorti 98 fois.",
    "Bonne question !\nJe suis HYBRIDE, l'assistant de LotoIA. Le 7 est chaud.",
    "Voici les stats.\n\nJe suis l’assistant LotoIA ! Le 12 est froid.",
    "Ah, bonne question ! 😉 Je suis HYBRIDE, l'assistant IA de LotoIA. Le 7 est sorti 98 fois.",
    "Je suis HYBRIDE.\nJe suis HYBRIDE, encore.\nLe 7.",
    "Je suis certain que le 7 sortira un jour.\nJe suis sûr aussi.",
    "I'm HYBRIDE, your LotoIA assistant. Number 7 came out 98 times.",
    "Good question!\n\nI am the assistant of LotoIA. Number 7 is hot.",
    "Soy HYBRIDE, el asistente de LotoIA. El 7 salió 98 veces.",
    "¡Buena pregunta!\nSoy el asistente de LotoIA.\nEl 7 salió 98 veces.",
    "Sou o assistente HYBRIDE. O 7 saiu 98 vezes.",
    "Boa pergunta!\n\nSou HYBRIDE! O 7 saiu 98 vezes.",
    "Ich bin der Assistent von LotoIA. Die 7 kam 98-mal.",
    "Gute Frage! 😉 Ich bin der Assistent von LotoIA und die 7 kam 98-mal.",
    "Ik ben de assistent van LotoIA. Nummer 7 is 98 keer getrokken.",
    "Goede vraag!\nIk ben HYBRIDE? Nummer 7.",
    "[SESSION]Je suis HYBRIDE, l'assistant. Le 7.",
    "Résultat :\n[RÉSULTAT SQL]\nJe suis HYBRIDE. Le 22 est sorti 104 fois.",
    "[REAL-TIME DATA - Number 7]I'm HYBRIDE. Number 7 is hot.",
    "漢字Je suis HYBRIDE. Suite après CJK.",
    "Je suis HYBRIDE.   \n\n\nLe 7 est chaud.",
    "x\n\n\nJe suis HYBRIDE. y",
    "Je  suis HYBRIDE double espace.",
    "Je suis\nHYBRIDE coupé par un saut.\nSuite",
    "Je suis HYBRIDE\n\nSans ponctuation puis suite",
    "Je suis HYBRIDE!? Oui.",
    "So\nSou\nSoupe\nI\nIl est\nIch\nIk\nJe\nJe ne sais pas.",
    "Fin : Je suis HYBRIDE.",
    "\n\nJe suis HYBRIDE.\n\n",
    "Voici [lien] Je suis HYBRIDE et je lis les stats. Le 7 est chaud.",
    "Ligne\n \nJe suis HYBRIDE. Après une ligne d'espace.",
    "je suis hybride, en minuscules.\nI'M THE ASSISTANT, EN MAJUSCULES.\nFin.",
]

_VERB_FIND = re.compile(r"(?i)je suis|i am|i'm|soy|sou|ich bin|ik ben")


def _targeted_cuts(text: str) -> set[int]:
    cuts = set()
    for m in _VERB_FIND.finditer(text):
        v = m.start()
        cuts |= {v, v + (m.end() - v) // 2, m.end()}  # avant le verbe, au milieu, après
        if v > 0 and text[v - 1] == "\n":
            cuts.add(v - 1)  # entre le \n d'ancre et ... (avant le \n)
        s = re.compile(r"(?i)hybride|l['’]assistant|the assistant|el asistente|o assistente|"
                       r"der assistent|de assistent").search(text, m.end())
        if s:
            cuts.add(s.end())  # juste après HYBRIDE / le sujet
            p = re.compile(r"[.!?\n]").search(text, s.end())
            if p:
                cuts |= {p.start(), p.end()}  # juste avant / après la ponctuation finale
    return {c for c in cuts if 0 < c < len(text)}


def _split(text: str, cuts) -> list[str]:
    bounds = [0, *sorted(set(cuts)), len(text)]
    return [text[a:b] for a, b in pairwise(bounds) if b > a]


def test_corpus_size():
    assert len(_CORPUS) == 32


@pytest.mark.parametrize("idx", range(len(_CORPUS)))
def test_ta_random_splits(idx):
    text = _CORPUS[idx]
    expected = _clean_response(text)
    rng = random.Random(1678 * 100 + idx)
    for _ in range(40):
        n = rng.randint(1, min(15, len(text) - 1))
        chunks = _split(text, rng.sample(range(1, len(text)), n))
        assert _stream(chunks) == expected, chunks


@pytest.mark.parametrize("idx", range(len(_CORPUS)))
def test_ta_char_by_char(idx):
    text = _CORPUS[idx]
    assert _stream(list(text)) == _clean_response(text)


@pytest.mark.parametrize("idx", range(len(_CORPUS)))
def test_ta_every_single_cut(idx):
    text = _CORPUS[idx]
    expected = _clean_response(text)
    for c in range(1, len(text)):
        assert _stream([text[:c], text[c:]]) == expected, c


@pytest.mark.parametrize("idx", range(len(_CORPUS)))
def test_ta_targeted_cut_pairs(idx):
    text = _CORPUS[idx]
    expected = _clean_response(text)
    cuts = sorted(_targeted_cuts(text))
    for pair in combinations(cuts, 2):
        assert _stream(_split(text, pair)) == expected, pair
    assert _stream(_split(text, cuts)) == expected


def test_ta_existing_corpus_still_equivalent():
    """Le corpus 1.6.055 (sans auto-présentation) reste équivalent."""
    from tests.test_stream_buffer_newlines import _RESPONSES
    for text in _RESPONSES:
        assert _stream(list(text)) == _clean_response(text)


# ═══════════════════════════════════════════════════════════════════════
# T-B — cas épinglés de l'audit (A1.4)
# ═══════════════════════════════════════════════════════════════════════

_AUDIT_CASES = {
    "FR-1": ["Ah, bonne question ! 😉 ", "Je suis HYBRIDE, l'assistant ", "IA de LotoIA. Le 7 est sorti 98 fois."],
    "FR-2": ["Ah, bonne question ! 😉 ", "Je suis HYBRIDE, l'assistant IA de LotoIA. Le 7 est sorti 98 fois."],
    "FR-4": ["Je suis HYBRIDE, l'assistant IA de Loto", "IA. Le 7 est sorti 98 fois."],
    "EN-1": ["I'm HYBRIDE", ", your LotoIA assistant. Number 7 came out 98 times."],
    "EN-3": ["Good question! ", "I am the assistant that reads the stats, and number 7 came out 98 times."],
    "FR-5": ["Voici [", "lien] ", "Je suis HYBRIDE et je lis les stats. Le 7 est chaud."],
    "DE-1": ["Gute Frage! 😉 ", "Ich bin der Assistent von LotoIA", " und die 7 kam 98-mal."],
}
_AUDIT_EXPECTED = {
    "FR-1": "Ah, bonne question ! 😉 Je suis HYBRIDE, l'assistant IA de LotoIA. Le 7 est sorti 98 fois.",
    "FR-2": "Ah, bonne question ! 😉 Je suis HYBRIDE, l'assistant IA de LotoIA. Le 7 est sorti 98 fois.",
    "FR-4": "Le 7 est sorti 98 fois.",
    "EN-1": "Number 7 came out 98 times.",
    "EN-3": "Good question! I am the assistant that reads the stats, and number 7 came out 98 times.",
    "FR-5": "Voici [lien] Je suis HYBRIDE et je lis les stats. Le 7 est chaud.",
    "DE-1": "Gute Frage! 😉 Ich bin der Assistent von LotoIA und die 7 kam 98-mal.",
}


@pytest.mark.parametrize("case", sorted(_AUDIT_CASES))
def test_tb_audit_case(case):
    chunks = _AUDIT_CASES[case]
    out = _stream(chunks)
    assert out == _clean_response("".join(chunks)) == _AUDIT_EXPECTED[case]


def test_tb_en1_log_has_whole_sentence(caplog):
    with caplog.at_level(logging.WARNING):
        _stream(_AUDIT_CASES["EN-1"])
    msgs = [r.getMessage() for r in caplog.records if "Anti-reintro stripped" in r.getMessage()]
    assert msgs == ["Anti-reintro stripped: I'm HYBRIDE, your LotoIA assistant."]


# ═══════════════════════════════════════════════════════════════════════
# T-C — latence
# ═══════════════════════════════════════════════════════════════════════

def test_tc_no_retention_without_verb():
    buf = StreamBuffer()
    assert buf.add_chunk("Le 7 est sorti 98 fois. ") == "Le 7 est sorti 98 fois. "
    assert buf.add_chunk("Écart : 12.\n") == "Écart : 12."  # \n de fin retenu (1.6.055, inchangé)
    assert buf.add_chunk("Bonne chance !") == "\nBonne chance !"
    assert buf.flush() == ""


def test_tc_mid_line_verb_never_held():
    buf = StreamBuffer()
    assert buf.add_chunk("Ah 😉 Je suis HYBRIDE") == "Ah 😉 Je suis HYBRIDE"
    assert buf.add_chunk(" et voilà.") == " et voilà."


def test_tc_ambiguous_prefix_released_as_soon_as_decided():
    buf = StreamBuffer()
    assert buf.add_chunk("Le 7.\nI") == "Le 7."  # « I » peut commencer « I am / I'm / Ich bin / Ik ben »
    assert buf.add_chunk("l est chaud.") == "\nIl est chaud."
    buf2 = StreamBuffer()
    assert buf2.add_chunk("Je suis") == ""
    assert buf2.add_chunk(" certain.") == "Je suis certain."  # échec certain dès « c » : libéré


# ═══════════════════════════════════════════════════════════════════════
# T-D — plafond 200 caractères (risque 2)
# ═══════════════════════════════════════════════════════════════════════

def test_td_cap_releases_without_reintro_nothing_lost():
    text = "Je suis HYBRIDE " + "x" * 250 + "\nSuite"
    buf = StreamBuffer()
    outs = [buf.add_chunk(c) for c in text]
    first = next(i for i, o in enumerate(outs) if o)
    assert first + 1 == _REINTRO_HOLD_CAP == 200
    assert outs[first] == text[:200]
    assert "".join(outs) + buf.flush() == text  # rien de perdu, aucun anti-réintro
    assert _stream([text]) == text  # même résultat en un seul morceau
    assert _clean_response(text) == "Suite"  # divergence assumée avec le texte entier (cas du plafond seul)


@pytest.mark.parametrize("k,removed", [(181, True), (182, False)])
def test_td_cap_boundary_independent_of_split(k, removed):
    text = "Je suis HYBRIDE " + "z" * k + ". Suite"
    m = _REINTRO_RE.search(text)
    assert (m.end() - m.start() < _REINTRO_HOLD_CAP) is removed
    expected = "Suite" if removed else text
    assert _stream([text]) == _stream(list(text)) == expected


# ═══════════════════════════════════════════════════════════════════════
# T-E / T-F — stream_and_respond
# ═══════════════════════════════════════════════════════════════════════

def _ctx(strict=False, meta=None):
    return {
        "system_prompt": "sys", "contents": [], "mode": "chat", "insult_prefix": "", "history": [],
        "lang": "en", "_http_client": MagicMock(), "gem_api_key": "", "_chat_meta": meta,
        "_strict_hallucination_block": strict,
    }


def _fake_stream(chunks, exc=None):
    async def _gen(*args, **kwargs):
        for c in chunks:
            yield c
        if exc:
            raise exc
    return _gen


async def _events(ctx, stream_fn):
    out = []
    async for ev in cpg.stream_and_respond(ctx, "FB", "[T]", "em", "en", "msg", "page", "chat", stream_fn=stream_fn):
        out.append(json.loads(ev[len("data: "):]))
    return out


@pytest.mark.asyncio
@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("case", ["EN-1", "EN-3", "FR-1", "FR-4"])
async def test_te_stream_and_respond_modes(strict, case):
    chunks = _AUDIT_CASES[case]
    with patch("services.chat_pipeline_gemini.log_from_meta") as mock_log:
        events = await _events(_ctx(strict), _fake_stream(chunks))
    shown = "".join(e["chunk"] for e in events if e["source"] == "gemini")
    assert shown == _clean_response("".join(chunks)) == _AUDIT_EXPECTED[case]
    assert mock_log.call_args.args[4] == shown  # response_preview = texte affiché


@pytest.mark.asyncio
async def test_tf_flush_releases_held_head():
    buf = StreamBuffer()
    assert buf.add_chunk("Je su") == ""
    assert buf.flush() == "Je su"
    buf2 = StreamBuffer()
    assert buf2.add_chunk("Le 7.\n\nI'm HYBRIDE") == "Le 7."
    assert buf2.flush() == ""  # auto-présentation en fin de flux : retirée comme sur le texte entier


@pytest.mark.asyncio
@pytest.mark.parametrize("strict", [False, True])
async def test_tf_exception_during_retention_single_fallback(strict):
    with patch("services.chat_pipeline_gemini.log_from_meta"):
        events = await _events(_ctx(strict), _fake_stream(["I'm HYBRIDE"], RuntimeError("boom")))
    assert [e["source"] for e in events] == ["fallback"]
    assert all("HYBRIDE" not in e["chunk"] for e in events)


# ═══════════════════════════════════════════════════════════════════════
# T-G — relance 429 de la génération SQL
# ═══════════════════════════════════════════════════════════════════════

def _err429():
    from google.genai import errors as genai_errors
    return genai_errors.ClientError(429, {"error": {"code": 429, "message": "x", "status": "RESOURCE_EXHAUSTED"}})


def _err500():
    from google.genai import errors as genai_errors
    return genai_errors.ServerError(500, {"error": {"code": 500, "message": "x", "status": "INTERNAL"}})


def _ok():
    resp = MagicMock()
    resp.text = "SELECT * FROM tirages LIMIT 10"
    resp.usage_metadata = None
    return resp


_GAMES = {
    "loto": (chat_sql, "load_prompt", "_generate_sql", "[TEXT-TO-SQL]", {}),
    "em": (chat_sql_em, "load_prompt_em", "_generate_sql_em", "[EM TEXT-TO-SQL]", {"lang": "en"}),
}
_START = 100.0


class _Env:
    def __init__(self):
        self.t = _START
        self.timeouts = []


@contextmanager
def _sql_env(mock_vertex_client, game, effects, *, t_after_429=_START + 0.3, jitter=0.5, sleep_hook=None,
             real_breaker=False):
    mod, loader, _, _, _ = _GAMES[game]
    env = _Env()
    if real_breaker:
        breaker = mod.gemini_breaker_sql  # vrai GeminiCircuitBreaker (B1 C6)
    else:
        breaker = MagicMock()
        breaker.state = "closed"
        breaker.OPEN = "open"
    env.breaker = breaker
    calls = {"n": 0}

    def clock():
        return env.t

    async def fake_sleep(delay):
        if sleep_hook:
            sleep_hook(env)
        env.t += delay

    async def spy_wait_for(coro, timeout):
        env.timeouts.append(timeout)
        return await coro

    async def gen_content(**kwargs):
        calls["n"] += 1
        eff = effects[calls["n"] - 1]
        if calls["n"] == 1:
            env.t = t_after_429  # instant où le 1er résultat (429) est constaté
        if isinstance(eff, BaseException):
            raise eff
        return eff

    with mock_vertex_client() as vc, \
         patch.object(mod, loader, return_value="prompt"), \
         patch.object(mod, "gemini_breaker_sql", breaker), \
         patch.object(mod, "_track_error") as track_err, \
         patch.object(mod, "_track_usage"), \
         patch.object(bcs, "_sql_clock", clock), \
         patch.object(bcs.random, "uniform", return_value=jitter), \
         patch.object(bcs.asyncio, "sleep", side_effect=fake_sleep) as sleep_mock, \
         patch.object(bcs.asyncio, "wait_for", side_effect=spy_wait_for):
        vc.client.aio.models.generate_content = AsyncMock(side_effect=gen_content)
        env.vc, env.track_err, env.sleep = vc, track_err, sleep_mock
        env.calls = calls
        yield env


async def _gen(game, box):
    mod, _, fn, _, extra = _GAMES[game]
    return await getattr(mod, fn)("q", None, None, None, started_at=_START, failure_box=box, **extra)


@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
async def test_tg_429_then_success(game, mock_vertex_client, caplog):
    box = {}
    with _sql_env(mock_vertex_client, game, [_err429(), _ok()]) as env, caplog.at_level(logging.WARNING):
        sql = await _gen(game, box)
    assert sql == "SELECT * FROM tirages LIMIT 10"
    assert env.calls["n"] == 2
    env.breaker._record_failure.assert_not_called()
    env.breaker._record_success.assert_called_once()
    env.track_err.assert_not_called()
    assert box == {}
    prefix = _GAMES[game][3]
    assert f"{prefix} [V129_1_RETRY] attempt=1/1 429, backoff=2.5s" in caplog.text
    assert env.timeouts[0] == 8.0
    # 2e tentative : min(8, restant − 0,5) ; restant après l'attente = 10 − (0,3 + 2,5) = 7,2
    assert env.timeouts[1] == pytest.approx(6.7)


@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
async def test_tg_429_twice_final_failure(game, mock_vertex_client, caplog):
    box = {}
    with _sql_env(mock_vertex_client, game, [_err429(), _err429()]) as env, caplog.at_level(logging.WARNING):
        sql = await _gen(game, box)
    assert sql is None
    assert env.calls["n"] == 2
    env.breaker._record_failure.assert_called_once()
    env.breaker._record_success.assert_not_called()
    env.track_err.assert_called_once()
    assert box == {"cause": "SqlVertex429"}
    assert f"{_GAMES[game][3]} Vertex 429 ResourceExhausted — fallback:" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
async def test_tg_500_no_retry(game, mock_vertex_client):
    box = {}
    with _sql_env(mock_vertex_client, game, [_err500(), _ok()]) as env:
        assert await _gen(game, box) is None
    assert env.calls["n"] == 1
    env.sleep.assert_not_called()
    env.breaker._record_failure.assert_called_once()
    assert box == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
async def test_tg_timeout_no_retry(game, mock_vertex_client):
    box = {}
    with _sql_env(mock_vertex_client, game, [asyncio.TimeoutError(), _ok()]) as env:
        assert await _gen(game, box) is None
    assert env.calls["n"] == 1
    env.sleep.assert_not_called()
    env.breaker._record_failure.assert_called_once()
    assert box == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
async def test_tg_breaker_open_during_backoff(game, mock_vertex_client):
    box = {}

    def open_breaker(env):
        env.breaker.state = "open"

    with _sql_env(mock_vertex_client, game, [_err429(), _ok()], sleep_hook=open_breaker) as env:
        assert await _gen(game, box) is None
    assert env.calls["n"] == 1  # pas de 2e appel
    env.breaker._record_failure.assert_not_called()
    env.track_err.assert_called_once()
    assert box == {"cause": "SqlVertex429"}


@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
async def test_tg_budget_below_3s_no_retry(game, mock_vertex_client):
    box = {}
    with _sql_env(mock_vertex_client, game, [_err429(), _ok()], t_after_429=_START + 7.5) as env:
        assert await _gen(game, box) is None
    assert env.calls["n"] == 1
    env.sleep.assert_not_called()
    env.breaker._record_failure.assert_called_once()
    env.track_err.assert_called_once()
    assert box == {"cause": "SqlVertex429"}


@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
async def test_tg_budget_exactly_3s_jitter_0_short_attempt(game, mock_vertex_client):
    """Risque 1 : à 3 s restantes la relance est autorisée, sa tentative est très courte (≤ 0,5 s)."""
    box = {}
    with _sql_env(mock_vertex_client, game, [_err429(), _ok()], t_after_429=_START + 7.0, jitter=0.0) as env:
        assert await _gen(game, box) == "SELECT * FROM tirages LIMIT 10"
    assert env.calls["n"] == 2
    assert 0 < env.timeouts[1] <= 0.5
    assert env.timeouts[1] == pytest.approx(0.5)


@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
async def test_tg_budget_3s_jitter_1_no_attempt_after_backoff(game, mock_vertex_client):
    box = {}
    with _sql_env(mock_vertex_client, game, [_err429(), _ok()], t_after_429=_START + 7.0, jitter=1.0) as env:
        assert await _gen(game, box) is None
    assert env.calls["n"] == 1  # délai ≤ 0 après l'attente : aucune tentative
    env.sleep.assert_called_once()
    env.breaker._record_failure.assert_called_once()
    env.track_err.assert_called_once()
    assert box == {"cause": "SqlVertex429"}


@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
@pytest.mark.parametrize("t429", [0.1, 1.0, 4.0, 6.5])
async def test_tg_second_attempt_within_budget(game, t429, mock_vertex_client):
    with _sql_env(mock_vertex_client, game, [_err429(), _ok()], t_after_429=_START + t429, jitter=0.7) as env:
        await _gen(game, {})
    assert env.calls["n"] == 2
    remaining_after_backoff = 10.0 - (t429 + 2.7)
    assert env.timeouts[1] <= remaining_after_backoff - 0.5 + 1e-9
    assert env.timeouts[1] <= 8.0


@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
async def test_tg_cancel_during_backoff_counts_nothing(game, mock_vertex_client):
    def cancel(env):
        raise asyncio.CancelledError()

    box = {}
    with _sql_env(mock_vertex_client, game, [_err429(), _ok()], sleep_hook=cancel) as env:
        with pytest.raises(asyncio.CancelledError):
            await _gen(game, box)
    env.breaker._record_failure.assert_not_called()
    env.track_err.assert_not_called()
    assert box == {}


def test_tg_constants_and_budget():
    assert bcs._SQL_GENERATE_BUDGET == cps._TIMEOUTS["sql_generate"] == 10
    assert (bcs._SQL_MAX_RETRIES_429, bcs._SQL_RETRY_BACKOFF_BASE, bcs._SQL_RETRY_JITTER_MAX) == (1, 2.0, 1.0)
    assert (bcs._SQL_RETRY_MIN_REMAINING, bcs._SQL_ATTEMPT_MARGIN, bcs._SQL_ATTEMPT_MAX) == (3.0, 0.5, 8.0)


@pytest.mark.asyncio
async def test_tg_run_text_to_sql_passes_start_and_box():
    seen = {}

    async def fake_gen(msg, client, key, **kwargs):
        seen.update(kwargs)
        return "NO_SQL"

    box = {}
    t_before = time.monotonic()
    await cps.run_text_to_sql(
        "fréquence du 7", MagicMock(), "", [], generate_sql_fn=fake_gen, validate_sql_fn=lambda s: True,
        ensure_limit_fn=lambda s: s, execute_sql_fn=AsyncMock(), format_result_fn=lambda r: "",
        max_per_session=10, log_prefix="[T]", force_sql=True, has_data_signal_fn=lambda m: True,
        continuation_mode=False, enrichment_context="", failure_box=box,
    )
    assert seen["failure_box"] is box
    assert t_before <= seen["started_at"] <= time.monotonic()


# ── Phase B (B1) — C3 libellé du timeout, C5 expiration réelle, C6 disjoncteur réel ──

@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
async def test_tg_timeout_label_first_attempt(game, mock_vertex_client, caplog):
    with _sql_env(mock_vertex_client, game, [asyncio.TimeoutError()]) as env, caplog.at_level(logging.WARNING):
        assert await _gen(game, {}) is None
    env.breaker._record_failure.assert_called_once()
    env.track_err.assert_called_once()
    assert f"{_GAMES[game][3]} Timeout Gemini Vertex (8.0s) — fallback" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
async def test_tg_timeout_label_second_attempt(game, mock_vertex_client, caplog):
    box = {}
    with _sql_env(mock_vertex_client, game, [_err429(), asyncio.TimeoutError()]) as env, \
         caplog.at_level(logging.WARNING):
        assert await _gen(game, box) is None
    assert env.calls["n"] == 2
    env.breaker._record_failure.assert_called_once()
    assert box == {}  # P4 : la cause finale est le timeout, pas le 429
    assert f"{_GAMES[game][3]} Timeout Gemini Vertex (6.7s) — fallback" in caplog.text


@pytest.mark.asyncio
async def test_tg_second_attempt_really_expires(mock_vertex_client, caplog):
    """R1 : vrai asyncio.wait_for ; seul le sommeil du backoff est neutralisé (helper commun : Loto suffit)."""
    env = _Env()
    breaker = MagicMock()
    breaker.state = "closed"
    breaker.OPEN = "open"
    calls = {"n": 0}

    async def gen_content(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            env.t = _START + 7.0  # 429 constaté à 3 s restantes
            raise _err429()
        await asyncio.Event().wait()  # tentative qui ne répond jamais (pas de sleep)

    async def fake_backoff(delay):
        env.t += delay  # 2,3 s → délai de tentative = 10 − 9,3 − 0,5 = 0,2 s

    box = {}
    t0 = time.monotonic()
    with mock_vertex_client() as vc, \
         patch.object(chat_sql, "load_prompt", return_value="prompt"), \
         patch.object(chat_sql, "gemini_breaker_sql", breaker), \
         patch.object(chat_sql, "_track_error") as track_err, \
         patch.object(chat_sql, "_track_usage"), \
         patch.object(bcs, "_sql_clock", lambda: env.t), \
         patch.object(bcs.random, "uniform", return_value=0.3), \
         patch.object(bcs.asyncio, "sleep", side_effect=fake_backoff), \
         caplog.at_level(logging.WARNING):
        vc.client.aio.models.generate_content = AsyncMock(side_effect=gen_content)
        sql = await chat_sql._generate_sql("q", None, None, None, started_at=_START, failure_box=box)
    elapsed = time.monotonic() - t0
    assert sql is None
    assert calls["n"] == 2
    breaker._record_failure.assert_called_once()
    track_err.assert_called_once()
    assert box == {}
    assert "[TEXT-TO-SQL] Timeout Gemini Vertex (0.2s) — fallback" in caplog.text
    assert 0.15 <= elapsed < 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize("game", sorted(_GAMES))
async def test_tg_real_breaker_opened_during_backoff(game, mock_vertex_client):
    """R2 : vrai gemini_breaker_sql ; ouvert pendant l'attente par son API existante (_record_failure × seuil)."""
    bk = _GAMES[game][0].gemini_breaker_sql
    saved = (bk._state, bk._failure_count, bk._opened_at)

    def open_breaker(env):
        for _ in range(bk._failure_threshold):
            bk._record_failure()

    box = {}
    try:
        bk.force_close()
        with _sql_env(mock_vertex_client, game, [_err429(), _ok()], sleep_hook=open_breaker,
                      real_breaker=True) as env:
            assert await _gen(game, box) is None
        assert env.calls["n"] == 1
        assert bk.state == bk.OPEN
        assert bk._failure_count == bk._failure_threshold  # aucun échec ajouté par le helper
        assert box == {"cause": "SqlVertex429"}
        env.track_err.assert_called_once()
    finally:
        bk._state, bk._failure_count, bk._opened_at = saved


# ── Phase B (B1) — C4 repli F05 par morceau (StreamBuffer._emit) ──

def test_f05_code_only_chunk_emits_fallback():
    from services.base_chat_utils import _CODE_FALLBACK
    buf = StreamBuffer()
    out = buf.add_chunk("```python\nx = 1\n```") + buf.flush()
    assert out == _CODE_FALLBACK["fr"]


def test_f05_code_then_text_emits_text():
    from services.base_chat_utils import _CODE_FALLBACK
    buf = StreamBuffer()
    out = buf.add_chunk("```python\nx = 1\n``` Voici la suite du texte.") + buf.flush()
    assert out.strip() == "Voici la suite du texte."
    assert _CODE_FALLBACK["fr"] not in out


# ═══════════════════════════════════════════════════════════════════════
# T-H — chat_log
# ═══════════════════════════════════════════════════════════════════════

def _meta(**extra):
    return {"phase": "SQL", "t0": time.monotonic(), "lang": "fr", **extra}


def test_th_log_from_meta_sql_cause():
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_lce:
        cpg.log_from_meta(_meta(sql_error_cause="SqlVertex429"), "loto", "fr", "q", "r")
    kw = mock_lce.call_args.kwargs
    assert kw["error_detail"] == "SqlVertex429" and kw["is_error"] is False


def test_th_real_error_keeps_its_own_detail():
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_lce:
        cpg.log_from_meta(_meta(sql_error_cause="SqlVertex429"), "loto", "fr", "q", "r",
                          is_error=True, error_detail="Timeout")
    kw = mock_lce.call_args.kwargs
    assert kw["error_detail"] == "Timeout" and kw["is_error"] is True


def test_th_error_without_detail_does_not_inherit_sql_cause():
    """B1 C2 (P1) : réponse finale en erreur sans error_detail → pas d'héritage de la cause SQL."""
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_lce:
        cpg.log_from_meta(_meta(sql_error_cause="SqlVertex429"), "loto", "fr", "q", "r", is_error=True)
    kw = mock_lce.call_args.kwargs
    assert kw["error_detail"] is None and kw["is_error"] is True


def test_th_no_cause_no_detail():
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_lce:
        cpg.log_from_meta(_meta(sql_error_cause=None), "loto", "fr", "q", "r")
    assert mock_lce.call_args.kwargs["error_detail"] is None


@pytest.mark.asyncio
async def test_th_stream_final_answer_logs_sql_cause():
    with patch("services.chat_pipeline_gemini.log_chat_exchange") as mock_lce:
        await _events(_ctx(meta=_meta(sql_error_cause="SqlVertex429")), _fake_stream(["Stats indisponibles."]))
    kw = mock_lce.call_args.kwargs
    assert kw["error_detail"] == "SqlVertex429" and kw["is_error"] is False


def test_th_chat_meta_carries_sql_error_cause():
    tree = ast.parse((ROOT / "services" / "chat_pipeline_shared.py").read_text(encoding="utf-8"))
    dicts = [n for n in ast.walk(tree) if isinstance(n, ast.Dict)
             and {"sql_status", "phase"} <= {k.value for k in n.keys if isinstance(k, ast.Constant)}]
    assert len(dicts) == 1
    assert "sql_error_cause" in {k.value for k in dicts[0].keys if isinstance(k, ast.Constant)}


@pytest.mark.asyncio
async def test_th_run_text_to_sql_real_generator_429_twice(mock_vertex_client):
    box = {}
    with mock_vertex_client() as vc, \
         patch.object(chat_sql, "load_prompt", return_value="prompt"), \
         patch.object(chat_sql, "_track_error"), \
         patch.object(bcs.asyncio, "sleep", new_callable=AsyncMock):
        vc.client.aio.models.generate_content = AsyncMock(side_effect=[_err429(), _err429()])
        enr, _, status = await cps.run_text_to_sql(
            "fréquence du 7", MagicMock(), "", [], generate_sql_fn=chat_sql._generate_sql,
            validate_sql_fn=lambda s: True, ensure_limit_fn=lambda s: s, execute_sql_fn=AsyncMock(),
            format_result_fn=lambda r: "", max_per_session=10, log_prefix="[T]", force_sql=True,
            has_data_signal_fn=lambda m: True, continuation_mode=False, enrichment_context="", failure_box=box,
        )
    chat_sql.gemini_breaker_sql.force_close()
    assert status == "ERROR"
    assert box == {"cause": "SqlVertex429"}


# ═══════════════════════════════════════════════════════════════════════
# T-I / T-J — ordinaux et séparateurs (pages EM rendues, 6 langues)
# ═══════════════════════════════════════════════════════════════════════

_EM_PAGES = {
    "statistiques": {"fr": "/euromillions/statistiques", "en": "/en/euromillions/statistics",
                     "es": "/es/euromillions/estadisticas", "pt": "/pt/euromillions/estatisticas",
                     "de": "/de/euromillions/statistiken", "nl": "/nl/euromillions/statistieken"},
    "paires": {"fr": "/euromillions/paires", "en": "/en/euromillions/pairs", "es": "/es/euromillions/pares",
               "pt": "/pt/euromillions/pares", "de": "/de/euromillions/paare", "nl": "/nl/euromillions/paren"},
}
_LOCALES = {"fr": "fr-FR", "en": "en-GB", "es": "es-ES", "pt": "pt-PT", "de": "de-DE", "nl": "nl-NL"}
_EXPECTED_FN = """function psRankOrdinal(n) {
            if (PS_LANG === 'en') {
                var m100 = n % 100, m10 = n % 10;
                var suf = (m100 >= 11 && m100 <= 13) ? 'th' : m10 === 1 ? 'st' : m10 === 2 ? 'nd' : m10 === 3 ? 'rd' : 'th';
                return n + '<sup>' + suf + '</sup>';
            }
            if (PS_LANG === 'es') return n + '.º';
            if (PS_LANG === 'pt') return n + '.ª';
            if (PS_LANG === 'de') return n + '.';
            if (PS_LANG === 'nl') return n + 'e';
            return n === 1 ? '1<sup>er</sup>' : n + '<sup>e</sup>';  // fr et langue inconnue
        }"""
_LOCALE_MAP_JS = ("var PS_LOCALE = {fr: 'fr-FR', en: 'en-GB', es: 'es-ES', pt: 'pt-PT', de: 'de-DE', "
                  "nl: 'nl-NL'}[PS_LANG] || 'fr-FR';")


@pytest.fixture(scope="module")
def em_client():
    with patch.dict(os.environ, {"DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb",
                                 "EM_PUBLIC_ACCESS": "true"}), \
         patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None), \
         patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None):
        import importlib
        import rate_limit as rl_mod
        importlib.reload(rl_mod)
        import middleware.em_access_control as _em_ac
        importlib.reload(_em_ac)
        import main as main_mod
        importlib.reload(main_mod)
        rl_mod.limiter.reset()
        rl_mod._api_hits.clear()
        yield TestClient(main_mod.app, raise_server_exceptions=False)


def _async_cm_conn():
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=None)
    cursor.fetchall = AsyncMock(return_value=[])

    @asynccontextmanager
    async def _cm():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn
    return _cm


_PAGE_CACHE: dict[str, str] = {}


def _page(client, path):
    if path not in _PAGE_CACHE:
        with patch("db_cloudsql.get_connection", _async_cm_conn()), \
             patch("db_cloudsql.async_fetchone", AsyncMock(return_value=None)):
            resp = client.get(path)
        assert resp.status_code == 200, f"{path} → {resp.status_code}"
        _PAGE_CACHE[path] = resp.text
    return _PAGE_CACHE[path]


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("page", sorted(_EM_PAGES))
def test_ti_em_ordinal_function_per_lang(em_client, page, lang):
    html = _page(em_client, _EM_PAGES[page][lang])
    assert f'window.LotoIA_lang="{lang}"' in html
    assert f'var PS_LANG = window.LotoIA_lang || "{lang}";' in html
    assert _LOCALE_MAP_JS in html
    fn = re.search(r"function psRankOrdinal\(n\) \{.*?\n        \}", html, re.DOTALL).group(0)
    assert fn == _EXPECTED_FN
    assert "var rankLabel = psRankOrdinal(d.rank);" in html
    assert "1<sup>re</sup>" not in html  # ZÉRO « 1re »


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("page", sorted(_EM_PAGES))
def test_tj_em_locale_separators(em_client, page, lang):
    html = _page(em_client, _EM_PAGES[page][lang])
    assert ".toLocaleString()" not in html
    assert html.count(".toLocaleString(PS_LOCALE)") == 6
    assert f"{lang}: '{_LOCALES[lang]}'" in html


@pytest.mark.parametrize("rel", ["ui/templates/em/statistiques.html", "ui/templates/em/paires.html"])
def test_tj_templates_source(rel):
    src = (ROOT / rel).read_text(encoding="utf-8")
    assert ".toLocaleString()" not in src
    assert "1<sup>re</sup>" not in src
    assert src.count("function psRankOrdinal(n)") == 1


@pytest.mark.parametrize("rel", ["ui/statistiques.html", "ui/paires.html"])
def test_ti_loto_pages_first_rank(rel):
    src = (ROOT / rel).read_text(encoding="utf-8")
    assert "data.rank === 1 ? '1<sup>er</sup>' : data.rank + '<sup>e</sup>'" in src
    assert "1<sup>re</sup>" not in src
    assert "toLocaleString('fr-FR')" in src


# ═══════════════════════════════════════════════════════════════════════
# Bump
# ═══════════════════════════════════════════════════════════════════════

def test_bump_1_6_078():
    from config.version import APP_VERSION, VERSION_DATE
    assert tuple(int(p) for p in APP_VERSION.split(".")) >= (1, 6, 78)
    assert VERSION_DATE >= "2026-11-26"
