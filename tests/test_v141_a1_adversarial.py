"""V141 A.1 — Tests adversarial (issus de docs/_v140_simulation.py).

Couvre 2 catégories du rapport V140 Phase 2.5 :
- Catégorie F (tag leak) : 7 tests F1-F7 — fix BUG #3 _clean_response regex
- BONUS 2 (_FACTUAL_TAGS) : 6 tests — fix HR6 / BUG #8

Refs:
- docs/AUDIT_V140_PHASE2_5_TESTS_ADVERSARIAL.md
- docs/_v140_simulation.py (script reproductible)
"""
import pytest

from services.base_chat_utils import _clean_response
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
