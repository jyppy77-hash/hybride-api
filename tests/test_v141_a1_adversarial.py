"""V141 A.1 — Tests adversarial (issus de docs/_v140_simulation.py).

Couvre 2 catégories du rapport V140 Phase 2.5 :
- Catégorie F (tag leak) : 7 tests F1-F7 — fix BUG #3 _clean_response regex
- BONUS 2 (_FACTUAL_TAGS) : 6 tests — fix HR6 / BUG #8

V141 A.3 ajouts :
- L6-F01 : invariant fonctionnel — chaque _FACTUAL_TAGS strippé via _clean_response
- L5-F02 : invariant structurel — cross-réf _FACTUAL_TAGS ↔ _INTERNAL_TAGS_PATTERNS

Refs:
- docs/AUDIT_V140_PHASE2_5_TESTS_ADVERSARIAL.md
- docs/_v140_simulation.py (script reproductible)
"""
import re

import pytest

from services.base_chat_utils import _INTERNAL_TAGS_PATTERNS, _clean_response
from services.chat_pipeline_gemini import _FACTUAL_TAGS


# ════════════════════════════════════════════════════════════════════
# CATÉGORIE F — Tag leak _clean_response (7 tests)
# Fix BUG #3 : regex `_clean_response` ne strippait pas les tags fermants `[/...]`
# ════════════════════════════════════════════════════════════════════


class TestV141F_TagLeak:
    """V141 A.1 — Catégorie F : tag leak via `_clean_response`.

    Le pattern global `\\[/[A-ZÀ-Ü0-9 _\\-—.À-ſ]+\\]` strip tous les tags
    fermants `[/XYZ]`. Couvre `[/RÉSULTAT TIRAGE]`, `[/GRILLE GÉNÉRÉE PAR HYBRIDE]`,
    `[/DONNÉES TEMPS RÉEL]`, `[/BREAKDOWN — Critères]`, etc.
    """

    def test_v141_f1_tag_fermant_grille_strippe(self):
        """F1 — Tag fermant [/GRILLE GÉNÉRÉE PAR HYBRIDE] doit être strippé."""
        cleaned = _clean_response(
            "Voici votre grille [GRILLE GÉNÉRÉE PAR HYBRIDE] qui est super "
            "[/GRILLE GÉNÉRÉE PAR HYBRIDE] cool"
        )
        assert "[/GRILLE" not in cleaned
        assert "[GRILLE" not in cleaned

    def test_v141_f2_tag_fermant_donnees_temps_reel_strippe(self):
        """F2 — Tag fermant [/DONNÉES TEMPS RÉEL] doit être strippé."""
        cleaned = _clean_response(
            "Stats du 42 [DONNÉES TEMPS RÉEL] freq=95 [/DONNÉES TEMPS RÉEL] voilà"
        )
        assert "[/DONNÉES" not in cleaned
        assert "[DONNÉES" not in cleaned

    def test_v141_f3_tag_fermant_resultat_tirage_strippe(self):
        """F3 — Tag fermant [/RÉSULTAT TIRAGE] doit être strippé."""
        cleaned = _clean_response(
            "Tirage [RÉSULTAT TIRAGE] 1-2-3-4-5 [/RÉSULTAT TIRAGE] OK"
        )
        assert "[/RÉSULTAT" not in cleaned
        assert "[RÉSULTAT" not in cleaned

    def test_v141_f4_tag_fermant_colle_sans_espace(self):
        """F4 — Cas terrain H4 du 06/05/2026 — tag fermant collé sans espace."""
        cleaned = _clean_response(
            "Pas de souci ! Voici[/GRILLE GÉNÉRÉE PAR HYBRIDE]Hybride V1"
        )
        assert "[/GRILLE" not in cleaned
        assert "Hybride V1" in cleaned

    def test_v141_f5_tags_internes_breakdown_contraintes(self):
        """F5 — Tags internes BREAKDOWN + CONTRAINTES UTILISATEUR strippés."""
        cleaned = _clean_response(
            "Réponse [BREAKDOWN — Critères] détails [CONTRAINTES UTILISATEUR] xy"
        )
        assert "[BREAKDOWN" not in cleaned
        assert "[CONTRAINTES" not in cleaned

    def test_v141_f6_tag_contexte_continuation_strippe(self):
        """F6 — Tag CONTEXTE CONTINUATION strippé (déjà OK V125, régression check)."""
        cleaned = _clean_response("Voici [CONTEXTE CONTINUATION] résumé")
        assert "[CONTEXTE CONTINUATION" not in cleaned

    def test_v141_f7_tag_chiffres_exacts_isole_strippe(self):
        """F7 — Tag CHIFFRES EXACTS isolé strippé (V141 A.1 nouveau pattern)."""
        cleaned = _clean_response("Stats [CHIFFRES EXACTS] visible")
        assert "[CHIFFRES EXACTS" not in cleaned

    def test_v141_f02a_tag_fermant_lowercase_ascii_strippe(self):
        """F02a (V141 A.3) — Tag fermant lowercase ASCII pure strippé (BUG LATENT V141 A.1)."""
        cleaned = _clean_response(
            "Tirage [result tirage] 1-2-3-4-5 [/result tirage] OK"
        )
        assert "[/result" not in cleaned, (
            "Pattern L255 V141 A.1 ne strippait pas tags lowercase ASCII (cf. fix V141 A.3)"
        )

    def test_v141_f02b_tag_fermant_mixed_case_strippe(self):
        """F02b (V141 A.3) — Tag fermant mixed case strippé (BUG LATENT V141 A.1)."""
        cleaned = _clean_response(
            "Voici [Analyse Partielle] détails [/Analyse Partielle] fin"
        )
        assert "[/Analyse" not in cleaned, (
            "Pattern L255 V141 A.1 ne strippait pas tags mixed case (cf. fix V141 A.3)"
        )


# ════════════════════════════════════════════════════════════════════
# BONUS 2 — _FACTUAL_TAGS coverage (6 tests parametric + count + V99)
# Fix HR6 / BUG #8 : _FACTUAL_TAGS ne couvrait que 3/15 tags réels
# ════════════════════════════════════════════════════════════════════


class TestV141FactualTags:
    """V141 A.1 — extension _FACTUAL_TAGS de 3 → 15 tags.

    Phases 2 / 3 / 3-bis / P / EVAL / 0-bis / G tournaient à T=0.6 sur du
    contexte chiffré factuel. Avec V141 A.1, T=0.2 (factuel) sur ces phases.
    """

    def test_v141_factual_tags_count_minimum(self):
        """V141 A.1 — _FACTUAL_TAGS couvre minimum 15 tags."""
        assert len(_FACTUAL_TAGS) >= 15, (
            f"_FACTUAL_TAGS doit contenir ≥15 tags après V141 A.1, "
            f"trouvé {len(_FACTUAL_TAGS)}: {_FACTUAL_TAGS}"
        )

    def test_v141_factual_tags_v99_originaux_preserves(self):
        """V99 originaux préservés — non-régression."""
        for v99_tag in ("[RÉSULTAT TIRAGE", "[RÉSULTAT SQL", "[DONNÉES TEMPS RÉEL"):
            assert v99_tag in _FACTUAL_TAGS, (
                f"Tag V99 {v99_tag!r} doit être préservé dans _FACTUAL_TAGS"
            )

    @pytest.mark.parametrize("tag", [
        "[ANALYSE DE GRILLE",
        "[ÉVALUATION GRILLE UTILISATEUR",
        "[CLASSEMENT",
        "[COMPARAISON",
        "[NUMÉROS",
        "[COMPARAISON SUR PÉRIODE",
        "[FRÉQUENCE SUR LA PÉRIODE",
        "[PROGRESSION",
        "[CORRÉLATIONS DE PAIRES",
        "[CORRÉLATIONS DE TRIPLETS",
        "[PROCHAIN TIRAGE",
        "[GRILLE GÉNÉRÉE PAR HYBRIDE",
    ])
    def test_v141_factual_tag_present(self, tag):
        """V141 A.1 — chaque tag factuel injecté est présent dans _FACTUAL_TAGS."""
        assert tag in _FACTUAL_TAGS, (
            f"Tag {tag!r} doit être dans _FACTUAL_TAGS pour T=0.2 sur phase associée"
        )

    def test_v141_factual_tags_substring_match_logic(self):
        """V141 A.1 — vérifier que la logique substring match fonctionne.

        `any(tag in enrichment ...)` doit matcher `[CLASSEMENT - Top 10...]`
        avec `tag = '[CLASSEMENT'`.
        """
        enrichment = "[CLASSEMENT - Top 10 numéros chance les plus fréquents]\n..."
        is_factual = any(tag in enrichment for tag in _FACTUAL_TAGS)
        assert is_factual, "Substring match doit reconnaître [CLASSEMENT - Top..."

    def test_v141_factual_tags_non_factual_message_skip(self):
        """V141 A.1 — message conversationnel sans tag → False (T=0.6 reste)."""
        enrichment = "Pas de tag factuel ici. Juste de la conversation."
        is_factual = any(tag in enrichment for tag in _FACTUAL_TAGS)
        assert not is_factual, "Message conversationnel ne doit PAS matcher _FACTUAL_TAGS"


# ════════════════════════════════════════════════════════════════════
# BONUS — Tag fermant `[/GRILLE GÉNÉRÉE PAR HYBRIDE]` injecté en Phase G
# Fix A4 — _format_generation_context Loto + EM
# ════════════════════════════════════════════════════════════════════


class TestV141A4_TagFermantPhaseG:
    """V141 A.1 — A4 : tag fermant systématique en Phase G Loto + EM."""

    def test_v141_a4_loto_tag_fermant_present(self):
        """A4 Loto — _format_generation_context produit `[/GRILLE GÉNÉRÉE PAR HYBRIDE]`."""
        from services.chat_utils import _format_generation_context
        grid_data = {
            "nums": [1, 12, 23, 34, 45],
            "chance": 7,
            "score": 85,
            "badges": ["balanced"],
            "mode": "balanced",
        }
        result = _format_generation_context(grid_data)
        assert "[GRILLE GÉNÉRÉE PAR HYBRIDE]" in result
        assert "[/GRILLE GÉNÉRÉE PAR HYBRIDE]" in result

    def test_v141_a4_em_tag_fermant_present(self):
        """A4 EM — _format_generation_context_em produit `[/GRILLE GÉNÉRÉE PAR HYBRIDE]`."""
        from services.chat_utils_em import _format_generation_context_em
        grid_data = {
            "nums": [3, 9, 25, 40, 47],
            "etoiles": [1, 11],
            "score": 90,
            "badges": ["balanced"],
            "mode": "balanced",
        }
        result = _format_generation_context_em(grid_data)
        assert "[GRILLE GÉNÉRÉE PAR HYBRIDE]" in result
        assert "[/GRILLE GÉNÉRÉE PAR HYBRIDE]" in result

    def test_v141_a4_loto_tag_fermant_strippe_par_clean_response(self):
        """A4 + A2 intégration — tag fermant injecté Phase G + strippé _clean_response."""
        from services.chat_utils import _format_generation_context
        grid_data = {
            "nums": [1, 12, 23, 34, 45],
            "chance": 7,
            "score": 85,
            "badges": ["balanced"],
            "mode": "balanced",
        }
        gen_ctx = _format_generation_context(grid_data)
        # Simuler une fuite si Gemini réémet le tag dans sa réponse
        cleaned = _clean_response(f"Voici la grille : {gen_ctx}\n\nC'est une bonne grille !")
        assert "[/GRILLE" not in cleaned
        assert "[GRILLE GÉNÉRÉE" not in cleaned
        assert "C'est une bonne grille" in cleaned


# ════════════════════════════════════════════════════════════════════
# V141 A.3 — L6-F01 Invariant : tous les _FACTUAL_TAGS sont strippés
# par _clean_response (defense-in-depth, régression coverage exhaustive)
# ════════════════════════════════════════════════════════════════════


def _build_factual_exemplar(tag_prefix: str) -> str:
    """V141 A.3 — exemplar strippable pour un prefix _FACTUAL_TAGS.

    `[NUMÉROS]` seul n'est PAS strippé (regex `internal_tags` exige
    suffixe `CHAUDS?|FROIDS?` cf. base_chat_utils.py L228). Tous les
    autres prefixes acceptent `]` direct via `[^\\]]*\\]`.
    """
    if tag_prefix == "[NUMÉROS":
        return "[NUMÉROS CHAUDS]"
    return f"{tag_prefix}]"


class TestV141A3_InvariantFactualTagsStripped:
    """V141 A.3 — Invariant L6-F01 : chaque tag de `_FACTUAL_TAGS`
    doit être strippé par `_clean_response` (régression coverage).

    Source unique de vérité = tuple `_FACTUAL_TAGS` exposée par
    `services.chat_pipeline_gemini`. Si un tag est ajouté à
    `_FACTUAL_TAGS` sans pattern correspondant dans `internal_tags`
    de `_clean_response`, ce test parametric le détecte automatiquement.
    """

    @pytest.mark.parametrize(
        "tag_prefix",
        list(_FACTUAL_TAGS),
        ids=lambda t: t.lstrip("[").replace(" ", "_"),
    )
    def test_v141_a3_invariant_factual_tag_is_stripped(self, tag_prefix):
        """V141 A.3 — chaque _FACTUAL_TAGS prefix est strippé par _clean_response."""
        exemplar = _build_factual_exemplar(tag_prefix)
        text = f"Réponse utile {exemplar} contenu visible"
        cleaned = _clean_response(text)
        assert tag_prefix not in cleaned, (
            f"Tag factuel {tag_prefix!r} doit être strippé via exemplar {exemplar!r}, "
            f"mais reste dans : {cleaned!r}"
        )
        assert "contenu visible" in cleaned


# ════════════════════════════════════════════════════════════════════
# V141 A.3 — L5-F02 Invariant STRUCTUREL : cross-référence
# `_FACTUAL_TAGS` ↔ `_INTERNAL_TAGS_PATTERNS` (sans `_clean_response`)
# ════════════════════════════════════════════════════════════════════


# Whitelist documentée des mismatches structurels intentionnels.
# Toute entrée ici doit avoir une justification explicite + tracé audit.
_KNOWN_STRUCTURAL_MISMATCHES = {
    "[NUMÉROS": (
        "Pattern internal_tags L228 exige suffixe `CHAUDS?|FROIDS?` "
        "(cf. base_chat_utils.py). Exemplar minimal `[NUMÉROS]` ne "
        "matche pas, comportement intentionnel pour éviter de stripper "
        "des tags factuels malformés (ex: `[NUMÉROS]` seul = malformé)."
    ),
}


class TestV141A3_StructuralFactualTagsCoverage:
    """V141 A.3 — Invariant L5-F02 : chaque tag de `_FACTUAL_TAGS`
    a un pattern miroir dans `_INTERNAL_TAGS_PATTERNS` (cross-référence
    structurelle des 2 listes, SANS appel à `_clean_response`).

    Distinct d'Item 3 (test fonctionnel via `_clean_response`) :
    - Item 3 = behavior test (avec exemplar adapté)
    - Item 4 = structural test (cross-réf brute des 2 listes)
    """

    @pytest.mark.parametrize(
        "tag_prefix",
        list(_FACTUAL_TAGS),
        ids=lambda t: t.lstrip("[").replace(" ", "_"),
    )
    def test_v141_a3_structural_factual_tag_has_mirror_pattern(self, tag_prefix):
        """V141 A.3 — chaque _FACTUAL_TAGS prefix a un pattern miroir
        dans _INTERNAL_TAGS_PATTERNS (sauf mismatches whitelistés)."""
        if tag_prefix in _KNOWN_STRUCTURAL_MISMATCHES:
            pytest.skip(_KNOWN_STRUCTURAL_MISMATCHES[tag_prefix])
        exemplar = f"{tag_prefix}]"
        matched_patterns = [
            p for p in _INTERNAL_TAGS_PATTERNS if re.search(p, exemplar)
        ]
        assert matched_patterns, (
            f"_FACTUAL_TAGS contient {tag_prefix!r} mais aucun pattern "
            f"dans _INTERNAL_TAGS_PATTERNS ne matche l'exemplar minimal "
            f"{exemplar!r}. Ajouter un pattern à _INTERNAL_TAGS_PATTERNS, "
            f"retirer de _FACTUAL_TAGS, ou whitelister dans "
            f"_KNOWN_STRUCTURAL_MISMATCHES avec justification."
        )

    def test_v141_a3_structural_known_mismatches_documented(self):
        """V141 A.3 — chaque mismatch whitelisté est dans `_FACTUAL_TAGS`
        (anti-drift de la whitelist : si on retire un tag de _FACTUAL_TAGS,
        on doit aussi retirer de la whitelist)."""
        orphans = set(_KNOWN_STRUCTURAL_MISMATCHES.keys()) - set(_FACTUAL_TAGS)
        assert not orphans, (
            f"_KNOWN_STRUCTURAL_MISMATCHES contient des entrées orphelines "
            f"(absentes de _FACTUAL_TAGS) : {orphans}. Retirer de la whitelist."
        )
