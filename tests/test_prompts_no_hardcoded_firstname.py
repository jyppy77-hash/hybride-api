"""1.6.055 — Point A : aucun prénom codé en dur dans les prompts.

Cas terrain : l'exemple « je m'appelle Marco » du prompt FR faisait appeler
l'utilisateur « Marco ». Pas de liste de prénoms : on bloque la forme
« je m'appelle <Mot capitalisé> » (6 langues) et le prénom fautif. Les prompts
citent légitimement l'éditeur (Jean-Philippe Godard / EmovisIA), non concerné.
"""

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent / "prompts"
_PROMPTS = sorted(_ROOT.rglob("*.txt"))

_SELF_INTRO_RE = re.compile(
    r"(?:je m['’]appelle|my name is|me llamo|chamo-me|ich hei(?:ß|ss)e|ik heet|mijn naam is)"
    r"\s+[\"'«]?\s*(?P<name>[^\s\"'»,.;:!?]+)",
    re.IGNORECASE,
)


def _hardcoded_names(text: str) -> list[str]:
    """Mots capitalisés (hors placeholder entre crochets) après une formule d'auto-présentation."""
    return [
        m.group("name") for m in _SELF_INTRO_RE.finditer(text)
        if m.group("name")[:1].isupper() and not m.group("name").startswith("[")
    ]


def test_prompts_found():
    assert len(_PROMPTS) > 50


@pytest.mark.parametrize("path", _PROMPTS, ids=lambda p: p.relative_to(_ROOT).as_posix())
def test_no_hardcoded_firstname_example(path):
    text = path.read_text(encoding="utf-8")
    assert not _hardcoded_names(text), f"{path}: {_hardcoded_names(text)}"
    assert not re.search(r"\bMarco\b", text), path


def test_detector_catches_the_old_example():
    assert _hardcoded_names('s\'il dit "je m\'appelle Marco", tu DOIS') == ["Marco"]
    assert _hardcoded_names("my name is Anna") == ["Anna"]
    assert _hardcoded_names('s\'il dit "je m\'appelle [prénom]"') == []
    assert _hardcoded_names("je m'appelle comment ?") == []
