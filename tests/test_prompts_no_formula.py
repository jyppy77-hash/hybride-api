"""
Tests — Correctif formule du chatbot (24/10/2026).

Décision Jyppy : aucune formule, aucun poids, aucun pourcentage de pondération dans le
chatbot. Les 7 prompts chargés en prod (Loto FR + EuroMillions × 6 langues) :
  TF1 — ne contiennent plus de pondération chiffrée ni d'invitation à donner une formule ;
  TF2 — contiennent la consigne anti-formule et le texte figé, dans leur langue ;
  TF3 — se chargent toujours via le loader de prod.
Hors périmètre : prompts/chatbot/prompt_hybride_em*.txt (non chargés).
"""
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

_ACTIVE_PROMPTS = {
    "loto_fr": "prompts/chatbot/prompt_hybride.txt",
    "em_fr": "prompts/em/fr/prompt_hybride_em.txt",
    "em_en": "prompts/em/en/prompt_hybride_em.txt",
    "em_es": "prompts/em/es/prompt_hybride_em.txt",
    "em_pt": "prompts/em/pt/prompt_hybride_em.txt",
    "em_de": "prompts/em/de/prompt_hybride_em.txt",
    "em_nl": "prompts/em/nl/prompt_hybride_em.txt",
}

# TF1 — pondération chiffrée (précis : ne touche pas « 100% gratuit », « 68% », « 150 mots »…)
_FORBIDDEN_WEIGHTS = [
    r"\b0[.,](?:42|28)\b",                                  # coefficients développés
    r"\b0[.,]\d\s*[×x*]",                                   # « 0.7 × », « 0,3 x »
    r"\b(?:70/30|60/40|40/60|50/30/20|40/35/25|25/35/40)\b",  # modes / fenêtres
    r"\(\s*\d{1,2}\s*%\s*\)",                               # « (60%) »
    r"\bScore\s*\(\s*n\s*\)",
    r"\bScore\s*=",
    r"\b(?:FL|FC|LF|SF|KF|LH|KH)\s*\(\s*n\s*\)",
]

# TF1 — invitations à livrer une formule (anciens blocs, 6 langues)
_FORBIDDEN_INVITATIONS = [
    r"VRAIES formules", r"livre de maths", r"formule condensée",
    r"REAL formulas", r"maths textbook", r"Condensed formula",
    r"fórmulas y ecuaciones REALES", r"libro de matemáticas", r"Fórmula condensada",
    r"fórmulas e equações REAIS", r"livro de matemática",
    r"ECHTEN Formeln", r"Mathematik-Lehrbuch", r"Komprimierte Formel",
    r"ECHTE formules", r"wiskundeboek", r"Verkorte formule",
]

# Ajouts interdits (consigne Jyppy)
_FORBIDDEN_WORDING = [
    r"strictement aléatoire", r"strictly random", r"estrictamente aleatori",
    r"estritamente aleatóri", r"streng zufällig", r"strikt willekeurig",
    r"ne peut pas modifier les numéros",
]

# TF2 — texte figé, par langue
_FIXED_TEXT = {
    "fr": ("Le générateur est aléatoire, pondéré par l'historique des tirages (fréquences et retards) "
           "et par des règles d'équilibre ; cette pondération ne change pas les chances de gain. "
           "Les numéros sont choisis par le moteur statistique, sans IA générative ; "
           "l'IA rédige uniquement les commentaires et explications."),
    "en": ("The generator is random, weighted by the draw history (frequencies and gaps) and by balance "
           "rules; this weighting does not change the chances of winning. The numbers are chosen by the "
           "statistical engine, without generative AI; the AI only writes the comments and explanations."),
    "es": ("El generador es aleatorio, ponderado por el historial de sorteos (frecuencias y retrasos) y por "
           "reglas de equilibrio; esta ponderación no cambia las probabilidades de ganar. Los números los "
           "elige el motor estadístico, sin IA generativa; la IA solo redacta los comentarios y las "
           "explicaciones."),
    "pt": ("O gerador é aleatório, ponderado pelo histórico dos sorteios (frequências e atrasos) e por regras "
           "de equilíbrio; esta ponderação não altera as probabilidades de ganhar. Os números são escolhidos "
           "pelo motor estatístico, sem IA generativa; a IA apenas redige os comentários e as explicações."),
    "de": ("Der Generator arbeitet zufällig, gewichtet nach der Ziehungshistorie (Häufigkeiten und Rückstände) "
           "und nach Ausgleichsregeln; diese Gewichtung ändert nichts an den Gewinnchancen. Die Zahlen werden "
           "von der statistischen Engine ausgewählt, ohne generative KI; die KI verfasst nur die Kommentare und "
           "Erklärungen."),
    "nl": ("De generator is willekeurig, gewogen op basis van de trekkingsgeschiedenis (frequenties en "
           "achterstanden) en evenwichtsregels; deze weging verandert niets aan de winkansen. De nummers "
           "worden gekozen door de statistische motor, zonder generatieve AI; de AI schrijft alleen de "
           "commentaren en uitleg."),
}

# TF2 — consigne « aucune formule / aucun chiffre », par langue
_NO_FORMULA_RULE = {
    "fr": "Ne donne AUCUNE formule et AUCUN chiffre de pondération",
    "en": "Give NO formula and NO weighting figure",
    "es": "No des NINGUNA fórmula ni NINGUNA cifra de ponderación",
    "pt": "Não dês NENHUMA fórmula nem NENHUM valor de ponderação",
    "de": "Gib KEINE Formel und KEINE Gewichtungszahl an",
    "nl": "Geef GEEN formule en GEEN wegingscijfer",
}


def _lang(key: str) -> str:
    return key.split("_")[1]


def _read(rel: str) -> str:
    return (_REPO / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("key", list(_ACTIVE_PROMPTS))
class TestNoWeightingInPrompts:

    def test_no_numeric_weighting(self, key):
        """TF1 — aucune pondération chiffrée."""
        text = _read(_ACTIVE_PROMPTS[key])
        for pattern in _FORBIDDEN_WEIGHTS:
            m = re.search(pattern, text)
            assert not m, f"{key}: pondération chiffrée « {m.group(0)} » ({pattern})"

    def test_no_formula_invitation(self, key):
        """TF1 — aucune invitation à donner une formule."""
        text = _read(_ACTIVE_PROMPTS[key])
        for pattern in _FORBIDDEN_INVITATIONS:
            assert not re.search(pattern, text, re.IGNORECASE), f"{key}: invitation « {pattern} »"

    def test_no_forbidden_wording(self, key):
        text = _read(_ACTIVE_PROMPTS[key])
        for pattern in _FORBIDDEN_WORDING:
            assert not re.search(pattern, text, re.IGNORECASE), f"{key}: formulation interdite « {pattern} »"

    def test_anti_formula_rule_present(self, key):
        """TF2 — consigne anti-formule + texte figé dans la langue du prompt."""
        text = _read(_ACTIVE_PROMPTS[key])
        lang = _lang(key)
        assert _NO_FORMULA_RULE[lang] in text, f"{key}: consigne anti-formule absente"
        assert _FIXED_TEXT[lang] in text, f"{key}: texte figé absent ou modifié"


class TestPromptsStillLoad:
    """TF3 — les prompts se chargent via le loader de prod et portent la consigne."""

    def test_loto_prompt_loads(self):
        from services.prompt_loader import load_prompt
        text = load_prompt("CHATBOT")
        assert text and _FIXED_TEXT["fr"] in text

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_em_prompt_loads(self, lang):
        from services.prompt_loader import load_prompt_em
        text = load_prompt_em("prompt_hybride_em", lang)
        assert text and _FIXED_TEXT[lang] in text
