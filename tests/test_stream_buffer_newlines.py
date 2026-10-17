"""1.6.055 — 2a : StreamBuffer ne perd plus les sauts de ligne en bord de morceau.

Avant : _clean_response faisait strip('\\n\\r') sur CHAQUE morceau du flux → les \\n
situés en bord de morceau disparaissaient ("Fréquence : 98\\nÉcart" → "98Écart").
Après : le strip des bords est fait une seule fois pour toute la réponse.
Les espaces de bord restent conservés (pas de retour du collage "Jene").
"""

import random
from itertools import pairwise

import pytest

from services.base_chat_utils import StreamBuffer, _clean_response


def _stream(chunks):
    buf = StreamBuffer()
    out = "".join(buf.add_chunk(c) for c in chunks)
    return out + buf.flush()


# ── Cas ciblés ──────────────────────────────────────────────────────────

def test_newline_at_chunk_end_kept():
    assert _stream(["Fréquence : 98\n", "Écart : 12"]) == "Fréquence : 98\nÉcart : 12"


def test_three_dates_keep_their_lines():
    assert _stream(["2025-12-14\n", "2025-11-30\n", "2025-11-16"]) == "2025-12-14\n2025-11-30\n2025-11-16"


def test_leading_newlines_of_response_dropped():
    assert _stream(["\n\nBonjour"]) == "Bonjour"


def test_trailing_newlines_dropped_at_flush():
    assert _stream(["fin\n\n"]) == "fin"


def test_newline_runs_across_chunks_collapsed():
    assert _stream(["a\n\n", "\nb"]) == "a\n\nb"


def test_newline_only_chunk_kept_between_texts():
    assert _stream(["Ligne 1", "\n", "Ligne 2"]) == "Ligne 1\nLigne 2"


def test_newline_only_first_chunk_dropped():
    assert _stream(["\n", "\n", "Bonjour"]) == "Bonjour"


def test_edge_spaces_kept_no_word_collage():
    assert _stream(["Je ", "ne peux ", "pas"]) == "Je ne peux pas"


def test_double_space_across_chunks_collapsed():
    assert _stream(["Le ", " numéro"]) == "Le numéro"


def test_tag_between_newlines_removed_and_lines_kept():
    # ≡ _clean_response du texte complet : le tag retiré laisse ses deux \n
    assert _stream(["Total : 3\n", "[SESSION]", "\nSuite"]) == "Total : 3\n\nSuite"
    assert _clean_response("Total : 3\n[SESSION]\nSuite") == "Total : 3\n\nSuite"


def test_buffer_reusable_state_reset_after_flush():
    buf = StreamBuffer()
    assert buf.add_chunk("a\n") == "a"
    assert buf.flush() == ""


def test_clean_response_default_still_strips_edges():
    assert _clean_response("\n\nHello\n") == "Hello"
    assert _clean_response("\nHello\n", strip_edges=False) == "\nHello\n"


# ── Équivalence : concaténation du flux == _clean_response(texte complet) ──

_RESPONSES = [
    "Le 7 est sorti 98 fois.\nÉcart actuel : 12 tirages.\n\nC'est un numéro **chaud**.",
    "\n\nVoici les 3 derniers tirages :\n- 2025-12-14 : 3 12 25 33 41\n- 2025-11-30 : 1 8 19 27 45\n",
    "Fréquence : 98\nÉcart : 12\nClassement : 23\n\n\n\nBonne chance !",
    "[RÉSULTAT SQL]\nLe numéro 22 est sorti 104 fois depuis novembre 2019.",
    "Je ne peux pas prédire les tirages.  Le hasard reste le hasard.\n\nJoue avec modération.",
    "Here are the hot numbers:\n\n1. 7 (120 draws)\n2. 14 (110 draws)\n3. 23 (100 draws)",
    "Los números más frecuentes son 7, 14 y 23.\n\nRecuerda: el azar no tiene memoria.",
    "Os números mais frequentes são 7, 14 e 23.\n\n\nJoga com moderação.",
    "Die häufigsten Zahlen sind 7, 14 und 23.\nViel Glück!\n\n",
    "De vaakst getrokken nummers zijn 7, 14 en 23.\n\nSpeel verantwoord.",
    "Analyse de ta grille :\n[ANALYSE DE GRILLE — 5 12 23 34 45]\nSomme : 119\nPairs : 2\n\nConformité correcte.",
    "Ligne A\n\n\n\n\nLigne B\n \nLigne C",
    "Texte avec [crochet simple] conservé.\nEt une suite.",
    "Comparaison :\n[COMPARAISON SUR PÉRIODE — 12 vs 45]\n12 : 30 fois\n45 : 28 fois[/COMPARAISON]\n\nFin.",
    "Un  texte   avec    des espaces   multiples\net des retours.",
    "Prochain tirage : lundi.\n[PROCHAIN TIRAGE]\nDate du prochain tirage : lundi 19/10/2026\n\nÀ bientôt.",
    "Mot中文 supprimé\n\nSuite après caractères 漢字 non latins.",
    "Le numéro chance le plus sorti est le 3.\n\n\n\n",
    "\n- 7\n- 14\n- 23\n- 31\n- 45\n\nCes numéros sont les plus fréquents.",
    "Dernière sortie : 29 septembre 2026\nÉcart moyen : 9,8 tirages\n\nPériode analysée : 4 novembre 2019 au 14 octobre 2026.",
]


def _random_split(text: str, rng: random.Random) -> list[str]:
    if len(text) < 2:
        return [text]
    n_cuts = rng.randint(1, min(12, len(text) - 1))
    cuts = sorted(rng.sample(range(1, len(text)), n_cuts))
    bounds = [0, *cuts, len(text)]
    return [text[a:b] for a, b in pairwise(bounds)]


def test_equivalence_corpus_size():
    assert len(_RESPONSES) == 20


@pytest.mark.parametrize("idx", range(len(_RESPONSES)))
def test_stream_equals_clean_response_on_random_splits(idx):
    """20 réponses × 10 découpages aléatoires (graine fixe) = 200 découpages."""
    text = _RESPONSES[idx]
    expected = _clean_response(text)
    rng = random.Random(1655 * 100 + idx)
    for _ in range(10):
        chunks = _random_split(text, rng)
        assert _stream(chunks) == expected, chunks


@pytest.mark.parametrize("idx", range(len(_RESPONSES)))
def test_stream_equals_clean_response_char_by_char(idx):
    """Découpage extrême : un caractère par morceau."""
    text = _RESPONSES[idx]
    assert _stream(list(text)) == _clean_response(text)
