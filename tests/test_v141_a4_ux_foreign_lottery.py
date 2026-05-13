"""V141 A.4 UX Fix 2 — Tests adversarial loteries étrangères (Phase OUT_OF_SCOPE_LOTTERY).

Couvre 5 catégories :
- A. Détection positive ~20 patterns (Afrique/US/Europe/Amériques/EuroMillions/catch-all)
- B. Non-régression Phase A argent légitime (~7 tests)
- C. Cross-sell module-aware EM↔Loto (~4 tests)
- D. i18n 6 langues OUT_OF_SCOPE_LOTTERY (~3 tests)
- E. Cas terrain user sénégalais 12/05/2026 22:33-22:35 (~2 tests)

Total : ~30 tests pytest, scope direct sur `chat_detectors._detect_foreign_lottery`
et `_get_foreign_lottery_response` (pas de pipeline complet — couvert tests intégration séparés).

Refs:
- docs/MEMORY.md §9 (V141 A.4 UX Fixes backlog)
- Cas terrain : prompt session 13/05/2026 (user sénégalais frustré, vote 1*)
"""

import pytest

from services.chat_detectors import (
    _detect_foreign_lottery,
    _get_foreign_lottery_response,
    _detect_argent,
)


# ════════════════════════════════════════════════════════════════════
# A. Détection positive loteries étrangères
# ════════════════════════════════════════════════════════════════════


class TestV141A4_DetectionAfrique:
    """A.1 — Loteries Afrique francophone (SENLOTO/LONASE/LONACI/PMUC/MDJS)."""

    @pytest.mark.parametrize("message,expected_tokens", [
        ("Quels sont les numéros gagnants du senloto ?", ("senloto",)),
        ("Stats lonase Sénégal", ("lonase",)),
        # LONACI match peut être 'lonaci' OU 'loterie cote d'ivoire' (catch-all) — les deux sont OK
        ("Loterie Cote d'Ivoire LONACI résultats", ("lonaci", "cote", "loterie")),
        ("PMUC Cameroun résultats du jour", ("pmuc",)),
        ("Loto MDJS Maroc tirage", ("mdjs", "loto maroc")),
    ])
    def test_v141_a4_afrique_lotteries_detected(self, message, expected_tokens):
        result = _detect_foreign_lottery(message)
        assert result is not None, f"Failed to detect lottery in: {message!r}"
        assert any(t in result.lower() for t in expected_tokens), (
            f"Expected one of {expected_tokens} in {result!r}"
        )


class TestV141A4_DetectionInternational:
    """A.2 — Loteries US / UK / Australie (PowerBall/MegaMillions/UK/Oz Lotto)."""

    @pytest.mark.parametrize("message,expected_token", [
        ("PowerBall numbers tonight", "powerball"),
        ("Mega Millions latest draw", "mega"),
        ("UK Lotto results yesterday", "uk lotto"),
        ("Oz Lotto Australia jackpot", "oz lotto"),
    ])
    def test_v141_a4_international_lotteries_detected(self, message, expected_token):
        result = _detect_foreign_lottery(message)
        assert result is not None, f"Failed to detect lottery in: {message!r}"
        assert expected_token.lower() in result.lower()


class TestV141A4_DetectionEurope:
    """A.3 — Loteries Europe hors France (Italie/Espagne/Suisse/Belgique)."""

    @pytest.mark.parametrize("message,expected_token", [
        ("Lotto Italia frequenze ultime", "lotto italia"),
        ("Bonoloto España estadísticas", "bonoloto"),
        ("El Gordo Navidad résultats", "el gordo"),
        ("La Primitiva números ganadores", "la primitiva"),
        ("Swiss Lotto Schweiz Statistiken", "swiss"),
        ("Loto belgique numéros samedi", "loto belgique"),
    ])
    def test_v141_a4_europe_lotteries_detected(self, message, expected_token):
        result = _detect_foreign_lottery(message)
        assert result is not None, f"Failed to detect lottery in: {message!r}"
        assert expected_token.lower() in result.lower()


class TestV141A4_DetectionAmericas:
    """A.4 — Loteries Canada / Amériques (Lotto Max/6-49/Mega-Sena)."""

    @pytest.mark.parametrize("message,expected_token", [
        ("Lotto Max Canada résultats", "lotto max"),
        ("Lotto 6/49 numbers Saturday", "lotto 6"),
        ("Mega-Sena Brasil resultados de hoje", "mega"),
    ])
    def test_v141_a4_americas_lotteries_detected(self, message, expected_token):
        result = _detect_foreign_lottery(message)
        assert result is not None, f"Failed to detect lottery in: {message!r}"
        assert expected_token.lower() in result.lower()


class TestV141A4_DetectionEuroMillions:
    """A.5 — EuroMillions matché (cross-sell potentiel selon module courant)."""

    @pytest.mark.parametrize("message", [
        "Stats euromillions tirage hier",
        "EuroMillions numéros vendredi",
        "euro millions numbers tonight",
    ])
    def test_v141_a4_euromillions_detected(self, message):
        result = _detect_foreign_lottery(message)
        assert result is not None, f"Failed to detect EuroMillions in: {message!r}"
        # Normalize: spaces and dashes removed for matching
        norm = result.lower().replace(" ", "").replace("-", "")
        assert "euromillion" in norm


class TestV141A4_DetectionCatchAll:
    """A.6 — Catch-all 'loto + pays étranger' (Maroc/Tunisie/Belgique...)."""

    @pytest.mark.parametrize("message", [
        "Quels numéros au Loto Maroc ?",
        "Loto Tunisie statistiques",
        "Loto Algérie résultats",
        "Loterie Espagne tirage",
    ])
    def test_v141_a4_catchall_loto_country_detected(self, message):
        result = _detect_foreign_lottery(message)
        assert result is not None, f"Failed to detect lottery in: {message!r}"


# ════════════════════════════════════════════════════════════════════
# B. Non-régression Phase A argent légitime
# ════════════════════════════════════════════════════════════════════


class TestV141A4_NonRegressionLegitimateLoto:
    """B.1 — Messages Loto FR légitimes ne doivent PAS être matchés foreign."""

    @pytest.mark.parametrize("message", [
        "J'ai gagné 100 euros au loto",
        "Combien on peut gagner avec 5 numéros",
        "Top 5 numéros sortis cette année",
        "Analyse ma grille 1-18-20-28-32",
        "Quels numéros du tirage de samedi",
        "Statistiques fréquence du numéro 7",
        "Devenir riche au loto possible ?",
    ])
    def test_v141_a4_legitimate_loto_fr_not_foreign(self, message):
        """Aucun de ces messages légitimes ne doit déclencher OUT_OF_SCOPE_LOTTERY."""
        result = _detect_foreign_lottery(message)
        assert result is None, (
            f"False positive: {message!r} matched as foreign lottery: {result!r}"
        )


class TestV141A4_ArgentDefenseInDepth:
    """B.2 — _detect_argent doit retourner False si loterie étrangère détectée."""

    def test_v141_a4_argent_skip_on_foreign_lottery(self):
        """Cas terrain : 'jackpot' seul match Phase A argent (faux positif).
        Avec defense-in-depth V141 A.4, présence 'senloto' → False (skip Phase A).
        """
        msg = "Connaissais tu senloto jackpot lonase Sénégal"
        assert _detect_argent(msg, "fr") is False

    def test_v141_a4_argent_legitimate_still_detected(self):
        """Phase A doit toujours fonctionner sans loterie étrangère présente."""
        # "devenir riche" matche _ARGENT_PHRASES['fr']
        result = _detect_argent("Devenir riche au loto, possible ?", "fr")
        assert result is True

    def test_v141_a4_argent_no_crash_empty(self):
        """Pas de crash sur message vide ou minuscule."""
        assert _detect_argent("", "fr") is False
        assert _detect_argent("ok", "fr") is False


# ════════════════════════════════════════════════════════════════════
# C. Cross-sell EM ↔ Loto module-aware
# ════════════════════════════════════════════════════════════════════


class TestV141A4_CrossSellEMLoto:
    """C.1 — Cross-sell entre modules LotoIA (EM ↔ Loto FR)."""

    def test_v141_a4_cross_sell_em_from_loto_module(self):
        """User sur module Loto pose Q EM → cross-sell vers /euromillions."""
        resp = _get_foreign_lottery_response(
            "euromillions", lang="fr", current_module="loto"
        )
        assert "/euromillions" in resp
        assert "EuroMillions" in resp or "euromillion" in resp.lower()

    def test_v141_a4_cross_sell_loto_from_em_module(self):
        """User sur module EM pose Q Loto FR → cross-sell vers /loto."""
        resp = _get_foreign_lottery_response(
            "loto français", lang="fr", current_module="em"
        )
        assert "/loto" in resp
        assert "FDJ" in resp or "français" in resp.lower()

    def test_v141_a4_no_response_em_on_em_module(self):
        """User sur module EM pose Q euromillions → None (same-module, pas de routage)."""
        resp = _get_foreign_lottery_response(
            "euromillions", lang="fr", current_module="em"
        )
        # V141 A.4 — same module = None signal pour fall-through pipeline normal
        assert resp is None

    def test_v141_a4_no_response_loto_fr_on_loto_module(self):
        """User sur module Loto pose Q loto français → None (same-module)."""
        resp = _get_foreign_lottery_response(
            "loto français", lang="fr", current_module="loto"
        )
        assert resp is None

    def test_v141_a4_foreign_lottery_no_cross_sell(self):
        """User Loto + senloto → out-of-scope, pas cross-sell."""
        resp = _get_foreign_lottery_response(
            "senloto", lang="fr", current_module="loto"
        )
        assert "/euromillions" not in resp
        assert "/loto" not in resp
        # Réponse out-of-scope doit mentionner le nom de la loterie
        assert "Senloto" in resp or "senloto" in resp.lower()


# ════════════════════════════════════════════════════════════════════
# D. i18n 6 langues OUT_OF_SCOPE_LOTTERY
# ════════════════════════════════════════════════════════════════════


class TestV141A4_ForeignLotteryI18n:
    """D.1 — Réponses OUT_OF_SCOPE_LOTTERY sur 6 langues."""

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_v141_a4_response_not_empty_per_lang(self, lang):
        """Chaque langue retourne une réponse non vide (≥ 50 chars)."""
        resp = _get_foreign_lottery_response(
            "powerball", lang=lang, current_module="loto"
        )
        assert isinstance(resp, str)
        assert len(resp) > 50, f"Response too short for lang={lang}: {resp!r}"

    @pytest.mark.parametrize("lang", ["fr", "en", "es", "pt", "de", "nl"])
    def test_v141_a4_placeholder_replaced(self, lang):
        """Placeholder {lottery} doit être remplacé par le nom matché."""
        resp = _get_foreign_lottery_response(
            "powerball", lang=lang, current_module="loto"
        )
        assert "{lottery}" not in resp
        assert "Powerball" in resp or "powerball" in resp.lower()

    def test_v141_a4_unknown_lang_fallback_fr(self):
        """Langue inconnue → fallback FR."""
        resp = _get_foreign_lottery_response(
            "powerball", lang="xx", current_module="loto"
        )
        assert isinstance(resp, str)
        assert len(resp) > 50
        # Indices français présents
        assert "HYBRIDE" in resp


# ════════════════════════════════════════════════════════════════════
# E. Cas terrain user sénégalais 12/05/2026 22:33-22:35
# ════════════════════════════════════════════════════════════════════


class TestV141A4_CasTerrainSenegal:
    """E.1 — Cas reproductible : user sénégalais frustré (Bug 2 origine, vote 1*).

    Refs :
    - 22:33:16 : 'Connaissais tu senloto jackpot lonase Sénégal'
    - 22:33:52 : 'Peux tu analyse des résultats de senloto jackpot lonase Sénégal'
    - 22:35:18 : 'Je n ai pas de questions sur loto français mais sur senloto jackpot lonase Sénégal'

    AVANT V141 A.4 : bot répond 3× 'argent c'est pas mon rayon' (faux positif Phase A
    sur 'jackpot') → user abandonne + vote 1 étoile.
    APRÈS V141 A.4 : `_detect_foreign_lottery` match 'senloto'/'lonase' → routing
    OUT_OF_SCOPE_LOTTERY → réponse adaptée 'HYBRIDE spécialisé Loto français'.
    """

    @pytest.mark.parametrize("message", [
        "Connaissais tu senloto jackpot lonase Sénégal",
        "Peux tu analyse des résultats de senloto jackpot lonase Sénégal",
        "Je n' ai pas de questions sur loto français mais sur senloto jackpot lonase Sénégal",
    ])
    def test_v141_a4_senegal_user_routed_out_of_scope(self, message):
        """Les 3 questions doivent matcher loterie étrangère (senloto/lonase)."""
        result = _detect_foreign_lottery(message)
        assert result is not None
        # Match doit être un token loterie Afrique francophone
        assert any(token in result.lower() for token in ["senloto", "lonase"]), (
            f"Expected senloto/lonase token, got: {result!r}"
        )

    def test_v141_a4_senegal_user_argent_short_circuit(self):
        """Defense-in-depth Phase A : 'jackpot' présent mais Phase A skip → False."""
        msg = "Connaissais tu senloto jackpot lonase Sénégal"
        assert _detect_argent(msg, "fr") is False, (
            "BUG : Phase A argent ne doit PAS matcher si loterie étrangère détectée"
        )


# ════════════════════════════════════════════════════════════════════
# F. Phase E2 — Pipeline integration (V141 A.4 patch regex extension)
# ════════════════════════════════════════════════════════════════════
# Tests ajoutés post-diagnostic 13/05/2026 13:48 (smoke local Jyppy).
# Bug détecté : "donne moi les numéros pour le loto anglais" → phase=SQL
# au lieu de OUT_OF_SCOPE_LOTTERY car regex incomplète (no anglais/british).
# Fix : extension regex +28 adjectifs FR + 8 patterns EN.
# ════════════════════════════════════════════════════════════════════


class TestV141A4_PipelineIntegration:
    """F.1 — Reproduction cas terrain + adjectifs nationalité étendus."""

    @pytest.mark.parametrize("message", [
        # Cas terrain reproduit 13/05/2026 13:48 smoke local Jyppy
        "donne moi les numéros pour le loto anglais",
        "donne moi les numéros pour le loto britannique",
        "give me numbers for british lotto",
    ])
    def test_v141_a4_cas_terrain_loto_anglais_detected(self, message):
        """Cas terrain : 'loto anglais' DOIT matcher (sinon phase=SQL fallback Gemini)."""
        result = _detect_foreign_lottery(message)
        assert result is not None, (
            f"BUG cas terrain : {message!r} non matché → routing OUT_OF_SCOPE_LOTTERY skipped"
        )

    @pytest.mark.parametrize("message,expected_token", [
        # Adjectifs FR ajoutés V141 A.4 patch
        ("loto britannique numéros", "britannique"),
        ("loto allemand stats", "allemand"),
        ("loto américain résultats", "am"),  # américain
        ("loto japonais tirage", "japonais"),
        ("loto irlandais", "irlandais"),
        ("loto polonais combien", "polonais"),
        # Patterns EN ajoutés V141 A.4 patch
        ("british lotto results", "british"),
        ("english lotto winners", "english"),
        ("american lottery numbers", "american"),
        ("irish lotto Saturday", "irish"),
    ])
    def test_v141_a4_new_adjectives_detected(self, message, expected_token):
        """Nouveaux adjectifs FR + patterns EN ajoutés via patch regex."""
        result = _detect_foreign_lottery(message)
        assert result is not None, f"Pattern manquant pour {message!r}"
        assert expected_token.lower() in result.lower(), (
            f"Expected token {expected_token!r} in match {result!r}"
        )


class TestV141A4_PipelineResponseTemplate:
    """F.2 — Vérifie que cas terrain → réponse template (PAS Gemini grille HYBRIDE)."""

    def test_v141_a4_cas_terrain_response_uses_template(self):
        """Cas terrain 'loto anglais' → template out-of-scope (latence <100ms attendue prod)."""
        msg = "donne moi les numéros pour le loto anglais"
        match = _detect_foreign_lottery(msg)
        assert match is not None
        resp = _get_foreign_lottery_response(match, lang="fr", current_module="loto")
        assert resp is not None
        # Template doit contenir signature HYBRIDE
        assert "HYBRIDE" in resp
        # Doit indiquer Loto français comme spécialité
        assert "Loto français" in resp or "loto fr" in resp.lower()
        # Ne doit PAS contenir des numéros tirés (signature grille HYBRIDE)
        assert "tirage" not in resp.lower() or "★" not in resp


class TestV141A4_PipelineNonRegression:
    """F.3 — Non-régression : messages Loto FR légitimes ne déclenchent PAS OUT_OF_SCOPE."""

    @pytest.mark.parametrize("message", [
        "j'ai gagné 100 euros au loto",  # Phase A légitime
        "donne moi les numéros du loto",  # Génération grille normale
        "quels numéros pour le tirage de samedi",  # Phase T
        "stats du numéro 7 sur les 100 derniers tirages",  # Phase 1
        "top 5 numéros sortis cette année",  # Phase 3
        "analyse ma grille 1-18-20-28-32",  # Phase 2
    ])
    def test_v141_a4_no_regression_legit_loto_fr(self, message):
        """Aucun de ces messages ne doit matcher OUT_OF_SCOPE_LOTTERY."""
        result = _detect_foreign_lottery(message)
        assert result is None, (
            f"REGRESSION : {message!r} matché en foreign lottery: {result!r}"
        )


class TestV141A4_PipelineCfgWiring:
    """F.4 — Vérifie que cfg dict expose detect_foreign_lottery au pipeline."""

    def test_v141_a4_loto_cfg_wires_foreign_lottery(self):
        """cfg Loto doit exposer detect_foreign_lottery + get_foreign_lottery_response."""
        from services.chat_pipeline import _build_loto_config
        cfg = _build_loto_config()
        assert callable(cfg.get("detect_foreign_lottery")), (
            "cfg Loto missing detect_foreign_lottery — pipeline ne routera pas"
        )
        assert callable(cfg.get("get_foreign_lottery_response")), (
            "cfg Loto missing get_foreign_lottery_response"
        )

    def test_v141_a4_em_cfg_wires_foreign_lottery(self):
        """cfg EM doit exposer detect_foreign_lottery + get_foreign_lottery_response."""
        from services.chat_pipeline_em import _build_em_config
        cfg = _build_em_config()
        assert callable(cfg.get("detect_foreign_lottery")), (
            "cfg EM missing detect_foreign_lottery — pipeline ne routera pas"
        )
        assert callable(cfg.get("get_foreign_lottery_response")), (
            "cfg EM missing get_foreign_lottery_response"
        )

    def test_v141_a4_loto_cfg_game_identity(self):
        """cfg Loto a game='loto' (utilisé pour cross-sell EM↔Loto)."""
        from services.chat_pipeline import _build_loto_config
        cfg = _build_loto_config()
        assert cfg.get("game") == "loto"

    def test_v141_a4_em_cfg_game_identity(self):
        """cfg EM a game='em' (utilisé pour cross-sell EM↔Loto)."""
        from services.chat_pipeline_em import _build_em_config
        cfg = _build_em_config()
        assert cfg.get("game") == "em"
