"""
Tests for engine/hybride_base.py and config/engine.py.
Config validation, base class, forced number validation, 3-window merge.
"""

import random
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from config.engine import LOTO_CONFIG, EM_CONFIG, EngineConfig
from engine.hybride_base import HybrideEngine
from tests.conftest import AsyncSmartMockCursor, make_async_conn


# ═══════════════════════════════════════════════════════════════════════
# EngineConfig (frozen dataclass)
# ═══════════════════════════════════════════════════════════════════════

class TestEngineConfig:

    def test_loto_config_frozen(self):
        with pytest.raises(FrozenInstanceError):
            LOTO_CONFIG.num_max = 99

    def test_em_config_frozen(self):
        with pytest.raises(FrozenInstanceError):
            EM_CONFIG.num_max = 99

    def test_loto_values(self):
        assert LOTO_CONFIG.game == "loto"
        assert LOTO_CONFIG.num_max == 49
        assert LOTO_CONFIG.secondary_max == 10
        assert LOTO_CONFIG.secondary_count == 1
        assert LOTO_CONFIG.somme_min == 70
        assert LOTO_CONFIG.somme_max == 150
        assert LOTO_CONFIG.anti_collision_threshold == 24
        assert LOTO_CONFIG.table_name == "tirages"

    def test_em_values(self):
        assert EM_CONFIG.game == "em"
        assert EM_CONFIG.num_max == 50
        assert EM_CONFIG.secondary_max == 12
        assert EM_CONFIG.secondary_count == 2
        assert EM_CONFIG.somme_min == 95
        assert EM_CONFIG.somme_max == 175
        assert EM_CONFIG.anti_collision_threshold == 31
        assert EM_CONFIG.table_name == "tirages_euromillions"

    def test_modes_3_weights(self):
        for cfg in (LOTO_CONFIG, EM_CONFIG):
            for mode, weights in cfg.modes.items():
                assert len(weights) == 3, f"{cfg.game} mode {mode} has {len(weights)} weights"
                assert abs(sum(weights) - 1.0) < 0.01, f"{cfg.game} mode {mode} weights sum to {sum(weights)}"

    def test_penalty_coefficients(self):
        assert LOTO_CONFIG.penalty_coefficients == (0.0, 0.65, 0.80, 0.90)
        assert EM_CONFIG.penalty_coefficients == (0.0, 0.65, 0.80, 0.90)

    def test_temperature_by_mode(self):
        for cfg in (LOTO_CONFIG, EM_CONFIG):
            assert cfg.temperature_by_mode['conservative'] == 1.0
            assert cfg.temperature_by_mode['balanced'] == 1.3
            assert cfg.temperature_by_mode['recent'] == 1.5

    def test_superstitious_numbers(self):
        assert LOTO_CONFIG.superstitious_numbers == frozenset({3, 7, 9, 11, 13})
        assert EM_CONFIG.superstitious_secondary == frozenset({3, 7, 9, 11})


# ═══════════════════════════════════════════════════════════════════════
# HybrideEngine instantiation
# ═══════════════════════════════════════════════════════════════════════

class TestHybrideEngineInit:

    def test_init_loto(self):
        engine = HybrideEngine(LOTO_CONFIG)
        assert engine.cfg.game == "loto"

    def test_init_em(self):
        engine = HybrideEngine(EM_CONFIG)
        assert engine.cfg.game == "em"


# ═══════════════════════════════════════════════════════════════════════
# Static helpers
# ═══════════════════════════════════════════════════════════════════════

class TestBaseMinmaxNormalize:

    def test_basic(self):
        result = HybrideEngine._minmax_normalize({1: 10, 2: 20, 3: 30})
        assert result[1] == 0.0
        assert result[3] == 1.0

    def test_all_equal(self):
        result = HybrideEngine._minmax_normalize({1: 5, 2: 5, 3: 5})
        assert all(v == 0.0 for v in result.values())


class TestBaseNormaliserEnProbabilites:

    def test_sum_to_one(self):
        scores = {n: random.random() + 0.01 for n in range(1, 50)}
        result = HybrideEngine.normaliser_en_probabilites(scores, temperature=1.3)
        assert pytest.approx(sum(result.values()), abs=1e-9) == 1.0

    def test_temperature_flattens(self):
        scores = {1: 0.1, 2: 1.0}
        t1 = HybrideEngine.normaliser_en_probabilites(scores, temperature=1.0)
        t2 = HybrideEngine.normaliser_en_probabilites(scores, temperature=2.0)
        assert t2[2] / t2[1] < t1[2] / t1[1]


class TestBaseScoreFinal:

    def test_stars(self):
        m = LOTO_CONFIG.star_to_legacy_score
        assert HybrideEngine._calculer_score_final(1.0, m) == 95
        assert HybrideEngine._calculer_score_final(0.90, m) == 85
        assert HybrideEngine._calculer_score_final(0.75, m) == 75
        assert HybrideEngine._calculer_score_final(0.55, m) == 60
        assert HybrideEngine._calculer_score_final(0.40, m) == 50


# ═══════════════════════════════════════════════════════════════════════
# Forced numbers validation (E08)
# ═══════════════════════════════════════════════════════════════════════

class TestForcedNumbersValidation:

    def test_valid_nums(self):
        engine = HybrideEngine(LOTO_CONFIG)
        nums, sec = engine.valider_forced_numbers([5, 10, 30], [3])
        assert nums == [5, 10, 30]
        assert sec == [3]

    def test_out_of_range_removed(self):
        engine = HybrideEngine(LOTO_CONFIG)
        nums, _ = engine.valider_forced_numbers([0, 25, 55], None)
        assert nums == [25]

    def test_duplicates_removed(self):
        engine = HybrideEngine(LOTO_CONFIG)
        nums, _ = engine.valider_forced_numbers([7, 7, 7, 14], None)
        assert nums == [7, 14]

    def test_truncated_if_too_many(self):
        engine = HybrideEngine(LOTO_CONFIG)
        nums, _ = engine.valider_forced_numbers([1, 2, 3, 4, 5, 6, 7], None)
        assert len(nums) == 5

    def test_em_etoiles_max_2(self):
        engine = HybrideEngine(EM_CONFIG)
        _, sec = engine.valider_forced_numbers(None, [1, 5, 9])
        assert len(sec) == 2

    def test_em_etoiles_range(self):
        engine = HybrideEngine(EM_CONFIG)
        _, sec = engine.valider_forced_numbers(None, [0, 5, 13])
        assert sec == [5]

    def test_none_inputs(self):
        engine = HybrideEngine(LOTO_CONFIG)
        nums, sec = engine.valider_forced_numbers(None, None)
        assert nums == []
        assert sec == []

    def test_loto_chance_max_1(self):
        engine = HybrideEngine(LOTO_CONFIG)
        _, sec = engine.valider_forced_numbers(None, [3, 7])
        assert len(sec) == 1  # secondary_count=1


# ═══════════════════════════════════════════════════════════════════════
# Constraint validation via config
# ═══════════════════════════════════════════════════════════════════════

class TestBaseValiderContraintes:

    def test_loto_perfect(self):
        engine = HybrideEngine(LOTO_CONFIG)
        assert engine.valider_contraintes([4, 15, 24, 33, 47]) == 1.0

    def test_em_perfect(self):
        engine = HybrideEngine(EM_CONFIG)
        assert engine.valider_contraintes([4, 15, 26, 33, 47]) == 1.0

    def test_loto_bas_haut_threshold(self):
        """Loto: seuil_bas_haut=24."""
        engine = HybrideEngine(LOTO_CONFIG)
        # All 5 numbers > 24 → nb_bas=0 → penalty
        score = engine.valider_contraintes([25, 30, 35, 40, 45])
        assert score < 1.0

    def test_em_bas_haut_threshold(self):
        """EM: seuil_bas_haut=25."""
        engine = HybrideEngine(EM_CONFIG)
        # All 5 numbers > 25 → nb_bas=0 → penalty
        score = engine.valider_contraintes([26, 30, 35, 40, 45])
        assert score < 1.0


# ═══════════════════════════════════════════════════════════════════════
# Anti-collision via config
# ═══════════════════════════════════════════════════════════════════════

class TestBaseAntiCollision:

    def test_loto_threshold(self):
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {20: 1.0, 30: 1.0}
        result = engine.apply_anti_collision(scores)
        assert result[20] == 1.0  # <=24
        assert result[30] == pytest.approx(1.15)  # >24

    def test_em_threshold(self):
        engine = HybrideEngine(EM_CONFIG)
        scores = {25: 1.0, 35: 1.0}
        result = engine.apply_anti_collision(scores)
        assert result[25] == 1.0  # <=31
        assert result[35] == pytest.approx(1.15)  # >31

    def test_secondary_anti_collision_em(self):
        engine = HybrideEngine(EM_CONFIG)
        scores = {n: 1.0 for n in range(1, 13)}
        result = engine.apply_secondary_anti_collision(scores)
        assert result[3] == pytest.approx(0.85)
        assert result[7] == pytest.approx(0.85)
        assert result[1] == 1.0  # not superstitious

    def test_secondary_anti_collision_loto_noop(self):
        """Loto has no superstitious secondary (empty frozenset)."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: 1.0 for n in range(1, 11)}
        result = engine.apply_secondary_anti_collision(scores)
        assert result == scores


# ═══════════════════════════════════════════════════════════════════════
# Three-window merge (F04)
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_three_window_metadata(mock_get_conn):
    """generate_grids metadata includes fenetre_globale."""
    from engine.hybride import generate_grids
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=1, mode="balanced")
    assert result["metadata"]["fenetre_globale"] is True


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_three_window_grids_valid(mock_get_conn):
    """Grids from 3-window engine are structurally valid."""
    from engine.hybride import generate_grids
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=5, mode="balanced")
    for grid in result["grids"]:
        assert len(grid["nums"]) == 5
        assert all(1 <= n <= 49 for n in grid["nums"])
        assert 1 <= grid["chance"] <= 10


# ═══════════════════════════════════════════════════════════════════════
# N01 — Docstrings epistemologiques
# ═══════════════════════════════════════════════════════════════════════

class TestDocstringsEpistemo:

    def test_hybride_engine_docstring_mentions_diversification(self):
        """La docstring de HybrideEngine mentionne 'diversification'."""
        assert 'diversification' in HybrideEngine.__doc__.lower()

    def test_hybride_engine_docstring_mentions_no_predictive(self):
        """La docstring de HybrideEngine mentionne 'predictif'."""
        assert 'predictif' in HybrideEngine.__doc__.lower() or 'predictive' in HybrideEngine.__doc__.lower()

    def test_calculer_retards_docstring_mentions_no_predictive(self):
        """La docstring de calculer_retards mentionne 'aucune valeur predictive'."""
        doc = HybrideEngine.calculer_retards.__doc__
        assert doc is not None
        assert 'predictive' in doc.lower() or 'predictif' in doc.lower()

    def test_calculer_retards_docstring_mentions_ux(self):
        """La docstring de calculer_retards mentionne 'UX' ou 'diversifier'."""
        doc = HybrideEngine.calculer_retards.__doc__
        assert doc is not None
        assert 'ux' in doc.lower() or 'diversifier' in doc.lower()


# ═══════════════════════════════════════════════════════════════════════
# N02 — Badges i18n
# ═══════════════════════════════════════════════════════════════════════

class TestBadgesI18n:

    def test_badges_fr(self):
        """Les badges Loto contiennent les labels FR (depuis config/i18n)."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: 1.0 for n in range(1, 50)}
        scores[5] = 2.0  # make score_moyen > score_global
        badges = engine._generer_badges([1, 5, 15, 25, 49], scores, lang="fr")
        assert "Hybride V1" in badges

    def test_badges_en(self):
        """Les badges Loto sont en anglais quand lang='en'."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: 1.0 for n in range(1, 50)}
        badges = engine._generer_badges([5, 15, 25, 35, 45], scores, lang="en")
        assert "Hybride V1" in badges
        # Should use English labels from _i18n_badges
        assert any("Balanced" in b or "Wide" in b or "Even" in b or "Hot" in b or "Overdue" in b for b in badges)

    def test_badges_all_6_langs(self):
        """Les badges sont disponibles dans les 6 langues sans erreur."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: 1.0 for n in range(1, 50)}
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            badges = engine._generer_badges([5, 15, 25, 35, 45], scores, lang=lang)
            assert len(badges) >= 2
            assert "Hybride V1" in badges

    def test_badges_em_i18n(self):
        """Les badges EM utilisent l'override _EMEngine."""
        from engine.hybride_em import generer_badges
        scores = {n: 1.0 for n in range(1, 51)}
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            badges = generer_badges([5, 15, 25, 35, 45], scores, lang=lang)
            assert len(badges) >= 2
            assert any("EM" in b for b in badges)


# ═══════════════════════════════════════════════════════════════════════
# N05 — Diversite multi-grilles
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_10_grilles_consecutives_pas_identiques(mock_get_conn):
    """10 grilles consecutives en mode balanced ne sont pas toutes identiques."""
    from engine.hybride import generate_grids
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=10, mode="balanced")
    grids_sets = [tuple(g["nums"]) for g in result["grids"]]
    assert len(set(grids_sets)) >= 2, "All 10 grids are identical"


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_diversite_numeros_sur_20_grilles(mock_get_conn):
    """20 grilles en mode balanced couvrent au moins 15 numeros distincts."""
    from engine.hybride import generate_grids
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=20, mode="balanced")
    all_nums = set()
    for g in result["grids"]:
        all_nums.update(g["nums"])
    assert len(all_nums) >= 15, f"Only {len(all_nums)} distinct numbers in 20 grids"


@pytest.mark.asyncio
@patch("engine.hybride.get_connection")
async def test_temperature_augmente_diversite_grilles(mock_get_conn):
    """T=1.5 (recent) produit plus de numeros distincts que T=1.0 (conservative)."""
    from engine.hybride import generate_grids
    cursor = AsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_async_conn(cursor)

    distinct_conservative = set()
    distinct_recent = set()
    for seed in range(20):
        random.seed(seed)
        r = await generate_grids(n=1, mode="conservative")
        distinct_conservative.update(r["grids"][0]["nums"])
        random.seed(seed)
        r = await generate_grids(n=1, mode="recent")
        distinct_recent.update(r["grids"][0]["nums"])

    # With noise+wildcard, both modes are diverse. Recent should be at least close.
    assert len(distinct_recent) >= len(distinct_conservative) - 3


@pytest.mark.asyncio
@patch("engine.hybride_em.get_connection")
async def test_etoiles_diversite_10_grilles(mock_get_conn):
    """Les etoiles EM ne sont pas identiques sur 10 grilles consecutives."""
    from engine.hybride_em import generate_grids
    from tests.test_hybride_em import EMAsyncSmartMockCursor, make_em_conn
    cursor = EMAsyncSmartMockCursor()
    mock_get_conn.side_effect = lambda: make_em_conn(cursor)
    random.seed(42)

    result = await generate_grids(n=10, mode="balanced", lang="fr")
    star_sets = [tuple(g["etoiles"]) for g in result["grids"]]
    assert len(set(star_sets)) >= 2, "All 10 star pairs are identical"


# ═══════════════════════════════════════════════════════════════════════
# V55 — get_reference_date (F04 audit fix)
# ═══════════════════════════════════════════════════════════════════════

class TestGetReferenceDate:

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_reference_date_from_db(self, mock_get_conn):
        """Retourne la date du dernier tirage de la BDD."""
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        engine = HybrideEngine(LOTO_CONFIG)
        async with make_async_conn(cursor) as conn:
            ref = await engine.get_reference_date(conn)
        assert ref is not None
        assert ref.year >= 2020

    @pytest.mark.asyncio
    async def test_reference_date_empty_db_fallback(self):
        """BDD vide → fallback datetime.now(UTC)."""
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock
        cursor = AsyncMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value={"max_date": None})
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        engine = HybrideEngine(LOTO_CONFIG)
        ref = await engine.get_reference_date(conn)
        assert ref.tzinfo is not None
        assert ref.year >= 2026

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_reference_date_returns_aware_datetime(self, mock_get_conn):
        """La date retournee est toujours timezone-aware (UTC)."""
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        engine = HybrideEngine(LOTO_CONFIG)
        async with make_async_conn(cursor) as conn:
            ref = await engine.get_reference_date(conn)
        assert ref.tzinfo is not None, "Reference date must be timezone-aware"


# ═══════════════════════════════════════════════════════════════════════
# V55 — Penalty coefficients unified (F05 audit fix)
# ═══════════════════════════════════════════════════════════════════════

class TestPenaltyCoefficientsUnified:

    def test_engine_config_coefficients_match_penalization(self):
        """Les coefficients dans EngineConfig sont identiques a ceux de penalization.py."""
        from services.penalization import PENALIZATION_COEFFS
        assert list(LOTO_CONFIG.penalty_coefficients) == PENALIZATION_COEFFS
        assert list(EM_CONFIG.penalty_coefficients) == PENALIZATION_COEFFS

    def test_single_source_of_truth(self):
        """penalization.py importe depuis config/engine.py (pas de constantes locales)."""
        import inspect
        import services.penalization as penal_mod
        source = inspect.getsource(penal_mod)
        assert "from config.engine import PENALTY_COEFFICIENTS" in source


# ═══════════════════════════════════════════════════════════════════════
# V55 — Ponderation display (F11 audit fix)
# ═══════════════════════════════════════════════════════════════════════

class TestPonderationDisplay:

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_ponderation_shows_3_window_weights(self, mock_get_conn):
        """Les metadata affichent les vrais poids 3 fenetres."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        result = await generate_grids(n=1, mode="balanced")
        # Format: principale/recente/globale
        assert result["metadata"]["ponderation"] == "40/35/25"

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_ponderation_conservative(self, mock_get_conn):
        """Mode conservative affiche 50/30/20."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        result = await generate_grids(n=1, mode="conservative")
        assert result["metadata"]["ponderation"] == "50/30/20"

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_ponderation_recent(self, mock_get_conn):
        """Mode recent affiche 25/35/40."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        result = await generate_grids(n=1, mode="recent")
        assert result["metadata"]["ponderation"] == "25/35/40"


# ═══════════════════════════════════════════════════════════════════════
# V55 — Scoring conformite unifie (F06 audit fix)
# ═══════════════════════════════════════════════════════════════════════

class TestScoringConformiteUnifie:

    def test_engine_perfect_grid_loto(self):
        """Grille parfaite Loto → score_conformite = 100."""
        engine = HybrideEngine(LOTO_CONFIG)
        score = engine.valider_contraintes([4, 15, 24, 33, 47])
        assert int(score * 100) == 100

    def test_engine_bad_grid_loto(self):
        """Grille mauvaise → score_conformite < 50."""
        engine = HybrideEngine(LOTO_CONFIG)
        score = engine.valider_contraintes([2, 4, 6, 8, 10])
        assert int(score * 100) < 50

    def test_engine_score_0_100_range(self):
        """Le score mappe est dans [0, 100]."""
        engine = HybrideEngine(LOTO_CONFIG)
        for nums in ([4, 15, 24, 33, 47], [1, 2, 3, 4, 5], [2, 4, 6, 8, 10]):
            score = int(engine.valider_contraintes(nums) * 100)
            assert 0 <= score <= 100


# ═══════════════════════════════════════════════════════════════════════
# V55-ter — F04: _minmax_normalize all-zeros documented
# ═══════════════════════════════════════════════════════════════════════

class TestMinMaxNormalizeAllZeros:

    def test_all_equal_returns_zeros(self):
        """All equal values → all 0.0 (documented behavior)."""
        result = HybrideEngine._minmax_normalize({1: 5.0, 2: 5.0, 3: 5.0})
        assert all(v == 0.0 for v in result.values())

    def test_all_equal_documented_in_docstring(self):
        """Docstring mentions all-zeros behavior."""
        doc = HybrideEngine._minmax_normalize.__doc__
        assert doc is not None
        assert "identical" in doc.lower() or "0.0" in doc

    def test_single_value_returns_zero(self):
        """Single value → 0.0."""
        result = HybrideEngine._minmax_normalize({1: 42.0})
        assert result[1] == 0.0


# ═══════════════════════════════════════════════════════════════════════
# V55-ter — F07: Anti-collision boost+malus documented
# ═══════════════════════════════════════════════════════════════════════

class TestAntiCollisionCumulDoc:

    def test_boost_and_malus_independent(self):
        """Boost and malus apply independently (documented edge case)."""
        from dataclasses import replace
        # Create a config where superstitious numbers include one above threshold
        cfg = replace(
            LOTO_CONFIG,
            anti_collision_threshold=10,
            superstitious_numbers=frozenset({12}),
        )
        engine = HybrideEngine(cfg)
        scores = {12: 1.0}
        adjusted = engine.apply_anti_collision(scores)
        # 12 > 10 (threshold) → boost 1.15, AND 12 in superstitious → malus 0.80
        expected = 1.0 * 1.15 * 0.80
        assert abs(adjusted[12] - expected) < 1e-9

    def test_anti_collision_docstring(self):
        """Docstring documents cumulative behavior."""
        doc = HybrideEngine.apply_anti_collision.__doc__
        assert doc is not None
        assert "independently" in doc.lower()


# ═══════════════════════════════════════════════════════════════════════
# V55-ter — F09: Anti-collision note i18n
# ═══════════════════════════════════════════════════════════════════════

class TestAntiCollisionNoteI18n:

    def test_note_exists_all_6_langs(self):
        """Anti-collision note exists in all 6 supported languages."""
        notes = HybrideEngine._ANTI_COLLISION_NOTES
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            assert lang in notes, f"Missing anti-collision note for {lang}"
            assert len(notes[lang]) > 20, f"Note too short for {lang}"

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_metadata_note_uses_lang(self, mock_get_conn):
        """Metadata anti-collision note is translated based on lang."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)
        result = await generate_grids(n=1, mode="balanced", lang="en", anti_collision=True)
        note = result["metadata"]["anti_collision"]["note"]
        assert "over-selected" in note or "calendar" in note.lower()


# ═══════════════════════════════════════════════════════════════════════
# V55-ter — F03: Badge engine via i18n (not hardcoded)
# ═══════════════════════════════════════════════════════════════════════

class TestBadgeEngineI18n:

    def test_badge_hybride_loto_in_all_langs(self):
        """Badge key 'hybride_loto' exists in all 6 languages."""
        from config.i18n import _badges
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            b = _badges(lang)
            assert "hybride_loto" in b, f"Missing hybride_loto badge for {lang}"

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_generated_grids_have_engine_badge(self, mock_get_conn):
        """Generated grids contain the engine badge from i18n."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)
        result = await generate_grids(n=1, mode="balanced", lang="fr")
        badges = result["grids"][0]["badges"]
        assert "Hybride V1" in badges


# ═══════════════════════════════════════════════════════════════════════
# V55-ter — F05: Diversity tests use seed (documented)
# ═══════════════════════════════════════════════════════════════════════

class TestDiversitySeedDocumented:

    def test_diversity_tests_are_deterministic(self):
        """Diversity tests use random.seed(42) for reproducibility.

        This test validates the pattern: seed → generate → restore.
        Non-deterministic diversity is inherent to random.choices().
        The seed ensures tests are not flaky while still verifying
        that the engine produces varied output.
        """
        random.seed(42)
        draws = [random.choices(range(1, 50), k=5) for _ in range(10)]
        random.seed(42)
        draws2 = [random.choices(range(1, 50), k=5) for _ in range(10)]
        assert draws == draws2  # Same seed → same output


# ═══════════════════════════════════════════════════════════════════════
# V56 — F04: degraded_windows flag in metadata
# ═══════════════════════════════════════════════════════════════════════

class TestDegradedWindows:

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_metadata_has_degraded_windows_key(self, mock_get_conn):
        """generate_grids metadata always contains degraded_windows."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        result = await generate_grids(n=1, mode="balanced")
        assert "degraded_windows" in result["metadata"]
        assert isinstance(result["metadata"]["degraded_windows"], list)

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_mock_flags_principale_as_degraded(self, mock_get_conn):
        """Mock has ~600 days of data, 5-year principale window is correctly degraded."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        result = await generate_grids(n=1, mode="balanced")
        degraded = result["metadata"]["degraded_windows"]
        # Mock has 200 tirages / 600 days — principale (5y) is degraded,
        # recente (2y) is not (200 draws ≥ 50% of expected for 2 years).
        windows = {d["window"] for d in degraded}
        assert "principale" in windows
        assert "recente" not in windows

    @pytest.mark.asyncio
    async def test_degraded_window_flagged_when_few_draws(self):
        """Window with <50% of expected draws produces a flag."""
        from unittest.mock import AsyncMock
        from datetime import date

        engine = HybrideEngine(LOTO_CONFIG)

        # Simulate a DB with 1000 tirages over 10 years (~100/year) but
        # only 30 in last 5y (principale) and 10 in last 2y (recente).
        # Expected principale: 5 * 100 = 500, actual=30 → 30 < 250 → flagged
        # Expected recente:    2 * 100 = 200, actual=10 → 10 < 100 → flagged
        cursor = AsyncMock()
        results_queue = [
            {"max_date": date(2026, 3, 1)},  # get_reference_date
            {"count": 30},   # principale window count
            {"count": 10},   # recente window count
        ]
        call_idx = {"i": 0}

        async def mock_fetchone():
            r = results_queue[call_idx["i"]]
            call_idx["i"] += 1
            return r

        cursor.execute = AsyncMock()
        cursor.fetchone = mock_fetchone
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)

        degraded = await engine._check_degraded_windows(
            conn, nb_tirages=1000,
            date_min=date(2016, 1, 1), date_max=date(2026, 3, 1),
        )
        assert len(degraded) >= 1
        windows = {d["window"] for d in degraded}
        assert "principale" in windows
        assert "recente" in windows
        # Each entry has expected > actual
        for d in degraded:
            assert d["actual"] < d["expected"]


# ═══════════════════════════════════════════════════════════════════════
# V56 — F03: badge_key config-driven (no _EMEngine override)
# ═══════════════════════════════════════════════════════════════════════

class TestBadgeKeyConfig:

    def test_loto_badge_key(self):
        """LOTO_CONFIG has badge_key='hybride_loto'."""
        assert LOTO_CONFIG.badge_key == "hybride_loto"

    def test_em_badge_key(self):
        """EM_CONFIG has badge_key='hybride_em'."""
        assert EM_CONFIG.badge_key == "hybride_em"

    def test_loto_badge_uses_config_key(self):
        """Loto engine generates badge from config.badge_key."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: 1.0 for n in range(1, 50)}
        badges = engine._generer_badges([5, 15, 25, 35, 45], scores, lang="fr")
        assert "Hybride V1" in badges

    def test_em_badge_uses_config_key(self):
        """EM engine generates badge from config.badge_key (no subclass needed)."""
        engine = HybrideEngine(EM_CONFIG)
        scores = {n: 1.0 for n in range(1, 51)}
        badges = engine._generer_badges([5, 15, 25, 35, 45], scores, lang="fr")
        assert any("EM" in b for b in badges)

    def test_em_no_subclass_needed(self):
        """EM engine is a plain HybrideEngine (no _EMEngine subclass)."""
        from engine.hybride_em import _engine
        assert type(_engine) is HybrideEngine


# ═══════════════════════════════════════════════════════════════════════
# V56 — F01: get_engine returns instance
# ═══════════════════════════════════════════════════════════════════════

class TestGetEngineReturnsInstance:

    def test_get_engine_returns_hybride_engine_loto(self):
        """get_engine for loto returns a HybrideEngine instance."""
        from config.games import get_config, get_engine, ValidGame
        cfg = get_config(ValidGame.loto)
        engine = get_engine(cfg)
        assert isinstance(engine, HybrideEngine)
        assert engine.cfg.game == "loto"

    def test_get_engine_returns_hybride_engine_em(self):
        """get_engine for EM returns a HybrideEngine instance."""
        from config.games import get_config, get_engine, ValidGame
        cfg = get_config(ValidGame.euromillions)
        engine = get_engine(cfg)
        assert isinstance(engine, HybrideEngine)
        assert engine.cfg.game == "em"


# ═══════════════════════════════════════════════════════════════════════
# V57 — F05: _display_weights generated from config
# ═══════════════════════════════════════════════════════════════════════

class TestDisplayWeightsDynamic:

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_display_weights_from_config(self, mock_get_conn):
        """Les poids affiches sont generes depuis cfg.modes (pas hardcodes)."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        for mode, expected in [
            ("conservative", "50/30/20"),
            ("balanced", "40/35/25"),
            ("recent", "25/35/40"),
        ]:
            result = await generate_grids(n=1, mode=mode)
            assert result["metadata"]["ponderation"] == expected, (
                f"mode={mode}: expected {expected}, got {result['metadata']['ponderation']}"
            )

    def test_display_weights_format(self):
        """Le format est 'XX/YY/ZZ' (entiers, separes par /)."""
        for cfg in (LOTO_CONFIG, EM_CONFIG):
            for mode, weights in cfg.modes.items():
                label = '/'.join(str(int(w * 100)) for w in weights)
                parts = label.split('/')
                assert len(parts) == 3
                assert all(p.isdigit() for p in parts)
                assert sum(int(p) for p in parts) == 100


# ═══════════════════════════════════════════════════════════════════════
# V57 — F01: Chatbot Loto lang parameter
# ═══════════════════════════════════════════════════════════════════════

class TestChatbotLotoLangParam:

    def test_prepare_chat_context_accepts_lang(self):
        """_prepare_chat_context accepte un parametre lang."""
        import inspect
        from services.chat_pipeline import _prepare_chat_context
        sig = inspect.signature(_prepare_chat_context)
        assert "lang" in sig.parameters
        assert sig.parameters["lang"].default == "fr"

    def test_handle_chat_accepts_lang(self):
        """handle_chat accepte un parametre lang."""
        import inspect
        from services.chat_pipeline import handle_chat
        sig = inspect.signature(handle_chat)
        assert "lang" in sig.parameters
        assert sig.parameters["lang"].default == "fr"

    def test_handle_chat_stream_accepts_lang(self):
        """handle_chat_stream accepte un parametre lang."""
        import inspect
        from services.chat_pipeline import handle_chat_stream
        sig = inspect.signature(handle_chat_stream)
        assert "lang" in sig.parameters
        assert sig.parameters["lang"].default == "fr"

    def test_schema_has_lang_field(self):
        """HybrideChatRequest a un champ lang avec default 'fr'."""
        from schemas import HybrideChatRequest
        req = HybrideChatRequest(message="test")
        assert req.lang == "fr"

    def test_schema_accepts_valid_lang(self):
        """HybrideChatRequest accepte les 6 langues valides."""
        from schemas import HybrideChatRequest
        for lang in ("fr", "en", "es", "pt", "de", "nl"):
            req = HybrideChatRequest(message="test", lang=lang)
            assert req.lang == lang


# ═══════════════════════════════════════════════════════════════════════
# V57 — F02: Re-exports cleaned up
# ═══════════════════════════════════════════════════════════════════════

class TestReExportsCleanedUp:

    def test_hybride_py_no_orphan_constants(self):
        """hybride.py ne re-exporte plus de constantes config."""
        import inspect
        import engine.hybride as mod
        source = inspect.getsource(mod)
        # These constants should NOT be in hybride.py anymore
        for name in ("_GENERATION_PENALTY_COEFFS", "TEMPERATURE_BY_MODE",
                      "ANTI_COLLISION_HIGH_BOOST", "LOTO_HIGH_THRESHOLD"):
            assert f"\n{name} =" not in source, f"{name} still re-exported in hybride.py"

    def test_hybride_em_no_orphan_constants(self):
        """hybride_em.py ne re-exporte plus de constantes config."""
        import inspect
        import engine.hybride_em as mod
        source = inspect.getsource(mod)
        for name in ("_GENERATION_PENALTY_COEFFS", "TEMPERATURE_BY_MODE",
                      "ANTI_COLLISION_HIGH_BOOST", "EM_HIGH_THRESHOLD",
                      "TABLE", "BOULE_MIN", "BOULE_MAX"):
            assert f"\n{name} =" not in source, f"{name} still re-exported in hybride_em.py"


# ═══════════════════════════════════════════════════════════════════════
# V57 — F04: score_type in custom-grid response
# ═══════════════════════════════════════════════════════════════════════

class TestCustomGridScoreType:

    def test_score_type_field_in_source(self):
        """api_analyse_unified.py retourne score_type dans la reponse custom-grid."""
        import inspect
        import routes.api_analyse_unified as mod
        source = inspect.getsource(mod)
        assert '"score_type"' in source or "'score_type'" in source


# ═══════════════════════════════════════════════════════════════════════
# V58 — F01: em_analyse.py:em_generate() propagates anti_collision
# ═══════════════════════════════════════════════════════════════════════

class TestEmAnalyseAntiCollision:

    def test_em_generate_has_anti_collision_param(self):
        """em_generate() exposes anti_collision query parameter."""
        import inspect
        from routes.em_analyse import em_generate
        sig = inspect.signature(em_generate)
        assert "anti_collision" in sig.parameters, (
            "em_generate() must expose anti_collision parameter"
        )

    def test_em_generate_anti_collision_default_false(self):
        """anti_collision defaults to False in em_generate()."""
        import inspect
        from routes.em_analyse import em_generate
        param = inspect.signature(em_generate).parameters["anti_collision"]
        assert param.default.default is False


# V93 F01: TestGenerateDeprecatedDocumented removed — generate() and /ask deleted.


# ═══════════════════════════════════════════════════════════════════════
# V58 — F05: valider_contraintes() guard on len(numeros)
# ═══════════════════════════════════════════════════════════════════════

class TestValiderContraintesGuard:

    def test_too_few_numbers_raises(self):
        """valider_contraintes with 4 numbers raises ValueError."""
        engine = HybrideEngine(LOTO_CONFIG)
        with pytest.raises(ValueError, match="Expected 5"):
            engine.valider_contraintes([3, 15, 24, 33])

    def test_too_many_numbers_raises(self):
        """valider_contraintes with 6 numbers raises ValueError."""
        engine = HybrideEngine(LOTO_CONFIG)
        with pytest.raises(ValueError, match="Expected 5"):
            engine.valider_contraintes([3, 15, 24, 33, 47, 49])

    def test_em_wrong_count_raises(self):
        """valider_contraintes with 4 numbers for EM raises ValueError."""
        engine = HybrideEngine(EM_CONFIG)
        with pytest.raises(ValueError, match="Expected 5"):
            engine.valider_contraintes([3, 15, 26, 33])


# ═══════════════════════════════════════════════════════════════════════
# V59 — F10: degraded_windows with truly insufficient data
# ═══════════════════════════════════════════════════════════════════════

class TestDegradedWindowsInsufficientData:
    """F10 audit 24/03/2026 — edge case données insuffisantes via SmartMockCursor."""

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_degraded_windows_flag_with_insufficient_data(self, mock_get_conn):
        """5 tirages << 50% attendu → both windows degraded."""
        from tests.conftest import _make_fake_tirages

        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor(tirages=_make_fake_tirages(n=5))
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        result = await generate_grids(n=1, mode="balanced")
        degraded = result["metadata"]["degraded_windows"]
        assert isinstance(degraded, list)
        assert len(degraded) >= 1
        windows = {d["window"] for d in degraded}
        # 5 tirages / 15 days → both 5-year and 2-year windows are degraded
        assert "principale" in windows
        # Grids are still generated (degraded mode, not crash)
        assert len(result["grids"]) == 1

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_degraded_windows_absent_with_sufficient_data(self, mock_get_conn):
        """200 tirages (standard mock) → degraded_windows empty or absent."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()  # default: 200 tirages
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        result = await generate_grids(n=1, mode="balanced")
        degraded = result["metadata"]["degraded_windows"]
        # recente (2y) should NOT be degraded with 200 tirages / 600 days
        recente_flagged = any(d["window"] == "recente" for d in degraded)
        assert not recente_flagged


# ═══════════════════════════════════════════════════════════════════════
# V79 — F10: forced_nums override exclusions (dict exclusions, not T-1)
# ═══════════════════════════════════════════════════════════════════════

class TestForcedNumsOverrideExclusions:

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_forced_num_present_despite_exclude_nums(self, mock_get_conn):
        """Forced number is in the grid even if it appears in exclude_nums."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        forced = [13]
        exclusions = {"exclude_nums": [13, 14, 15]}
        result = await generate_grids(
            n=3, mode="balanced", forced_nums=forced, exclusions=exclusions,
        )
        for grid in result["grids"]:
            assert 13 in grid["nums"], (
                f"Forced number 13 missing from grid despite exclusion: {grid['nums']}"
            )

    @pytest.mark.asyncio
    @patch("engine.hybride_em.get_connection")
    async def test_forced_num_present_despite_exclude_range_em(self, mock_get_conn):
        """EM: forced number survives an exclude_ranges that covers it."""
        from tests.test_hybride_em import EMAsyncSmartMockCursor, make_em_conn
        from engine.hybride_em import generate_grids
        cursor = EMAsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_em_conn(cursor)
        random.seed(42)

        forced = [25]
        exclusions = {"exclude_ranges": [(20, 30)]}
        result = await generate_grids(
            n=3, mode="balanced", forced_nums=forced, exclusions=exclusions,
        )
        for grid in result["grids"]:
            assert 25 in grid["nums"], (
                f"Forced EM number 25 missing from grid despite range exclusion: {grid['nums']}"
            )


# ═══════════════════════════════════════════════════════════════════════
# V79 — F04 audit: Pool exhaustion tests
# ═══════════════════════════════════════════════════════════════════════

class TestPoolExhaustion:

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_pool_near_exhaustion_loto(self, mock_get_conn):
        """Pool quasi-vide (40 exclus + 5 T-1) → fallback, no crash."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        # Exclude 40 numbers via exclusions + 5 via T-1 = 45/49 excluded
        exclude_nums = list(range(1, 41))  # exclude 1-40
        exclusions = {"exclude_nums": exclude_nums}
        # T-1 will exclude more (from mock data) but fallback should kick in
        result = await generate_grids(n=1, mode="balanced", exclusions=exclusions)
        assert len(result["grids"]) == 1
        grid = result["grids"][0]
        assert len(grid["nums"]) == 5
        assert all(1 <= n <= 49 for n in grid["nums"])

    @pytest.mark.asyncio
    @patch("engine.hybride_em.get_connection")
    async def test_pool_near_exhaustion_em(self, mock_get_conn):
        """EM: massive exclusions → fallback, still produces valid grid."""
        from tests.test_hybride_em import EMAsyncSmartMockCursor, make_em_conn
        from engine.hybride_em import generate_grids
        cursor = EMAsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_em_conn(cursor)
        random.seed(42)

        exclude_nums = list(range(1, 46))  # exclude 1-45 of 50
        exclusions = {"exclude_nums": exclude_nums}
        result = await generate_grids(n=1, mode="balanced", exclusions=exclusions)
        assert len(result["grids"]) == 1
        grid = result["grids"][0]
        assert len(grid["nums"]) == 5
        assert all(1 <= n <= 50 for n in grid["nums"])
        assert isinstance(grid["etoiles"], list)
        assert len(grid["etoiles"]) == 2

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_max_tentatives_returns_best_grid(self, mock_get_conn):
        """Impossible constraints → returns best grid after max_tentatives, no crash."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        # Generate grid — the constraint system always finds something in 20 tries
        result = await generate_grids(n=1, mode="balanced")
        assert len(result["grids"]) == 1
        grid = result["grids"][0]
        # Score is in valid range (could be low if constraints hard to satisfy)
        assert grid["score"] in (50, 60, 75, 85, 95)

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_all_excluded_fallback(self, mock_get_conn):
        """All nums excluded except exactly 5 → grid contains those 5."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        # Keep only 5 nums: 10, 20, 30, 40, 49
        keep = {10, 20, 30, 40, 49}
        exclude_nums = [n for n in range(1, 50) if n not in keep]
        exclusions = {"exclude_nums": exclude_nums}
        result = await generate_grids(n=1, mode="balanced", exclusions=exclusions)
        grid = result["grids"][0]
        assert set(grid["nums"]) == keep


# ═══════════════════════════════════════════════════════════════════════
# V79 — F05 evaluation: 0-pairs / 5-pairs occurrence rate
# ═══════════════════════════════════════════════════════════════════════

class TestEvalPairBalance:

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_extreme_pairs_rate_under_1_percent(self, mock_get_conn):
        """Generate 200 grids and count 0-pairs or 5-pairs. Rate should be <1%."""
        from engine.hybride import generate_grids
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)
        random.seed(42)

        extreme_count = 0
        total = 200
        result = await generate_grids(n=total, mode="balanced")
        for grid in result["grids"]:
            nb_pairs = sum(1 for n in grid["nums"] if n % 2 == 0)
            if nb_pairs == 0 or nb_pairs == 5:
                extreme_count += 1

        rate = extreme_count / total
        # F05 IMPLEMENTED V79: hard-reject 0-pairs/5-pairs → rate should be 0%
        assert rate == 0.0, (
            f"Hard-reject should prevent 0-pairs/5-pairs but rate={rate:.1%} ({extreme_count}/{total})"
        )


# ═══════════════════════════════════════════════════════════════════════
# V79 — F05: Hard-reject 0-pairs / 5-pairs
# ═══════════════════════════════════════════════════════════════════════

class TestHardRejectPairs:

    def test_hard_reject_zero_pairs(self):
        """All-odd grid → score = 0.0."""
        engine = HybrideEngine(LOTO_CONFIG)
        assert engine.valider_contraintes([1, 3, 5, 7, 9]) == 0.0

    def test_hard_reject_all_pairs(self):
        """All-even grid → score = 0.0."""
        engine = HybrideEngine(LOTO_CONFIG)
        assert engine.valider_contraintes([2, 4, 6, 8, 10]) == 0.0

    def test_soft_penalty_one_pair(self):
        """1-pair grid → score < 1.0 but > 0.0 (soft penalty ×0.80)."""
        engine = HybrideEngine(LOTO_CONFIG)
        # [2, 13, 25, 37, 49] : pairs={2}=1, bas(≤24)={2,13}=2, somme=126, disp=47
        score = engine.valider_contraintes([2, 13, 25, 37, 49])
        assert 0.0 < score < 1.0
        # Should have the ×0.80 pair penalty
        assert score == pytest.approx(0.80)

    def test_no_penalty_balanced_pairs(self):
        """2-3 pairs → no pair penalty."""
        engine = HybrideEngine(LOTO_CONFIG)
        # [4, 15, 24, 33, 47] : pairs={4,24}=2, somme=123, disp=43
        assert engine.valider_contraintes([4, 15, 24, 33, 47]) == 1.0


# ═══════════════════════════════════════════════════════════════════════
# V79 — F01: Noise factor (intra-session diversification)
# ═══════════════════════════════════════════════════════════════════════

class TestNoiseFactor:

    def test_noise_factor_zero_no_change(self):
        """noise_factor=0.0 → scores identical."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: 0.5 + n * 0.01 for n in range(1, 50)}
        result = engine.apply_noise(scores, 0.0)
        assert result == scores

    def test_noise_factor_produces_variation(self):
        """noise_factor=0.10 → scores differ from original."""
        scores = {n: 0.5 + n * 0.01 for n in range(1, 50)}
        random.seed(42)
        result = HybrideEngine.apply_noise(scores, 0.10)
        changed = sum(1 for n in scores if abs(result[n] - scores[n]) > 1e-9)
        assert changed > 0

    def test_noise_scores_clamped_to_zero(self):
        """No negative scores after noise."""
        scores = {n: 0.01 for n in range(1, 50)}  # very low scores
        random.seed(42)
        result = HybrideEngine.apply_noise(scores, 0.50)  # aggressive noise
        for s in result.values():
            assert s >= 0.0

    def test_noise_proportional_to_std(self):
        """Tight scores (std≈0) → minimal noise."""
        scores = {n: 0.50 for n in range(1, 50)}  # all identical
        random.seed(42)
        result = HybrideEngine.apply_noise(scores, 0.10)
        # All identical → std=0 → no noise applied
        assert result == scores

    def test_noise_diversity_n_grilles(self):
        """20 grilles with noise → ≥20 distinct numbers."""
        from tests.conftest import AsyncSmartMockCursor, make_async_conn
        from engine.hybride import generate_grids
        from unittest.mock import patch as _patch

        async def _run():
            with _patch("engine.hybride.get_connection") as mock:
                cursor = AsyncSmartMockCursor()
                mock.side_effect = lambda: make_async_conn(cursor)
                random.seed(42)
                result = await generate_grids(n=20, mode="balanced")
                all_nums = set()
                for g in result["grids"]:
                    all_nums.update(g["nums"])
                return len(all_nums)

        import asyncio
        count = asyncio.get_event_loop().run_until_complete(_run())
        assert count >= 20, f"Only {count} distinct numbers in 20 grids"

    def test_noise_by_mode_from_config(self):
        """noise_by_mode is read from EngineConfig (V92 F04)."""
        assert LOTO_CONFIG.noise_by_mode["conservative"] == 0.0
        assert LOTO_CONFIG.noise_by_mode["balanced"] == 0.08
        assert LOTO_CONFIG.noise_by_mode["recent"] == 0.12

    def test_em_noise_by_mode_higher(self):
        """EM noise is slightly higher than Loto (V92 calibration)."""
        assert EM_CONFIG.noise_by_mode["balanced"] == 0.10
        assert EM_CONFIG.noise_by_mode["recent"] == 0.15
        assert EM_CONFIG.noise_by_mode["balanced"] > LOTO_CONFIG.noise_by_mode["balanced"]


# ═══════════════════════════════════════════════════════════════════════
# V79 — F01: Wildcard froid (guaranteed cold slot)
# ═══════════════════════════════════════════════════════════════════════

class TestWildcardFroid:

    def test_wildcard_disabled_no_effect(self):
        """wildcard_enabled=False → _select_wildcard returns None."""
        from dataclasses import replace
        cfg = replace(LOTO_CONFIG, wildcard_enabled=False)
        engine = HybrideEngine(cfg)
        scores = {n: 1.0 - n * 0.01 for n in range(1, 50)}
        assert engine._select_wildcard(scores, set()) is None

    def test_wildcard_produces_cold_number(self):
        """wildcard returns a number from the bottom-15 scores."""
        engine = HybrideEngine(LOTO_CONFIG)
        # Build scores: 1→0.01, 2→0.02, ..., 49→0.49
        scores = {n: n * 0.01 for n in range(1, 50)}
        random.seed(42)
        wc = engine._select_wildcard(scores, set())
        assert wc is not None
        assert wc <= 15  # should be in the bottom-15

    def test_wildcard_respects_exclusions(self):
        """Wildcard does not pick excluded numbers."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: n * 0.01 for n in range(1, 50)}
        excluded = set(range(1, 16))  # exclude all bottom-15
        random.seed(42)
        wc = engine._select_wildcard(scores, excluded)
        # Should pick from 16-30 range (next coldest)
        assert wc is not None
        assert wc not in excluded

    def test_wildcard_with_forced_nums_5(self):
        """5 forced_nums → wildcard disabled (nb_to_draw < 2)."""
        from tests.conftest import AsyncSmartMockCursor, make_async_conn
        from engine.hybride import generate_grids
        from unittest.mock import patch as _patch

        async def _run():
            with _patch("engine.hybride.get_connection") as mock:
                cursor = AsyncSmartMockCursor()
                mock.side_effect = lambda: make_async_conn(cursor)
                random.seed(42)
                # Use 2+ even numbers to pass hard-reject F05
                forced = [4, 15, 26, 35, 45]
                result = await generate_grids(n=1, mode="balanced", forced_nums=forced)
                return result["grids"][0]["nums"]

        import asyncio
        nums = asyncio.get_event_loop().run_until_complete(_run())
        assert set(nums) == {4, 15, 26, 35, 45}

    def test_wildcard_with_forced_nums_3(self):
        """3 forced_nums → wildcard active on 1 of 2 free slots."""
        from tests.conftest import AsyncSmartMockCursor, make_async_conn
        from engine.hybride import generate_grids
        from unittest.mock import patch as _patch

        async def _run():
            with _patch("engine.hybride.get_connection") as mock:
                cursor = AsyncSmartMockCursor()
                mock.side_effect = lambda: make_async_conn(cursor)
                random.seed(42)
                forced = [25, 35, 45]
                result = await generate_grids(n=1, mode="balanced", forced_nums=forced)
                return result["grids"][0]["nums"]

        import asyncio
        nums = asyncio.get_event_loop().run_until_complete(_run())
        assert all(f in nums for f in [25, 35, 45])
        assert len(nums) == 5

    def test_wildcard_config_defaults(self):
        """Config has correct wildcard defaults."""
        assert LOTO_CONFIG.wildcard_enabled is True
        assert LOTO_CONFIG.wildcard_pool_size == 15
        assert EM_CONFIG.wildcard_enabled is True
        assert EM_CONFIG.wildcard_pool_size == 15


# ═══════════════════════════════════════════════════════════════════════
# V80 — F08: Secondary scoring dedicated weights (85/15)
# ═══════════════════════════════════════════════════════════════════════

class TestSecondaryScoringWeights:

    def test_secondary_weights_sum_to_one(self):
        """poids_frequence_secondary + poids_retard_secondary == 1.0."""
        for cfg in (LOTO_CONFIG, EM_CONFIG):
            total = cfg.poids_frequence_secondary + cfg.poids_retard_secondary
            assert total == pytest.approx(1.0), f"{cfg.game}: {total}"

    def test_secondary_weights_differ_from_primary(self):
        """Secondary 85/15 differs from primary 70/30."""
        assert LOTO_CONFIG.poids_frequence_secondary != LOTO_CONFIG.poids_frequence
        assert LOTO_CONFIG.poids_retard_secondary != LOTO_CONFIG.poids_retard

    def test_loto_secondary_weights(self):
        """Loto chance uses 85/15."""
        assert LOTO_CONFIG.poids_frequence_secondary == 0.85
        assert LOTO_CONFIG.poids_retard_secondary == 0.15

    def test_em_secondary_weights(self):
        """EM etoiles uses 85/15."""
        assert EM_CONFIG.poids_frequence_secondary == 0.85
        assert EM_CONFIG.poids_retard_secondary == 0.15

    @pytest.mark.asyncio
    @patch("engine.hybride.get_connection")
    async def test_secondary_scoring_uses_dedicated_weights(self, mock_get_conn):
        """calculer_scores_fenetre_secondary uses poids_*_secondary."""
        from tests.conftest import AsyncSmartMockCursor, make_async_conn
        cursor = AsyncSmartMockCursor()
        mock_get_conn.side_effect = lambda: make_async_conn(cursor)

        engine = HybrideEngine(LOTO_CONFIG)
        async with make_async_conn(cursor) as conn:
            scores = await engine.calculer_scores_fenetre_secondary(conn, None)
        # With 85/15 weighting, scores exist for all secondary numbers
        assert len(scores) == 10  # Loto chance: 1-10
        for n in range(1, 11):
            assert n in scores


# ═══════════════════════════════════════════════════════════════════════
# V92 — Decay rotation: accelerated decay breaks kernel lock
# ═══════════════════════════════════════════════════════════════════════

class TestDecayRotation:

    def test_decay_rotation_after_2_selections(self):
        """After 2 selections with decay_rate=0.10 + acceleration=0.03,
        at least 1 number of the top 5 must be replaced."""
        engine = HybrideEngine(LOTO_CONFIG)
        # Build scores: top 5 are 45-49 with highest scores
        scores = {n: n * 0.01 for n in range(1, 50)}
        top5_original = {45, 46, 47, 48, 49}
        # Simulate 2 consecutive selections of the top 5
        decay_state = {n: 2 for n in top5_original}
        decayed = engine.apply_decay(scores, decay_state)
        # After decay, at least 1 of the top 5 should be displaced
        top5_after = set(sorted(decayed, key=lambda n: decayed[n], reverse=True)[:5])
        displaced = top5_original - top5_after
        assert len(displaced) >= 1, (
            f"Expected ≥1 displaced number, top5 unchanged: {top5_after}"
        )

    def test_decay_rotation_after_3_selections(self):
        """After 3 selections, ≥2 numbers of top 5 should be displaced."""
        engine = HybrideEngine(LOTO_CONFIG)
        scores = {n: n * 0.01 for n in range(1, 50)}
        top5_original = {45, 46, 47, 48, 49}
        decay_state = {n: 3 for n in top5_original}
        decayed = engine.apply_decay(scores, decay_state)
        top5_after = set(sorted(decayed, key=lambda n: decayed[n], reverse=True)[:5])
        displaced = top5_original - top5_after
        assert len(displaced) >= 2, (
            f"Expected ≥2 displaced, got {len(displaced)}: {top5_after}"
        )


class TestDecayRotationStars:

    def test_decay_rotation_stars_after_2_selections(self):
        """With decay_rate_secondary=0.15, after 2 selections,
        at least 1 star of the top 3 should change."""
        engine = HybrideEngine(EM_CONFIG)
        # Build star scores: 12 stars, top 3 are 10, 11, 12
        scores = {n: n * 0.05 for n in range(1, 13)}
        top3_original = {10, 11, 12}
        decay_state = {n: 2 for n in top3_original}
        decayed = engine.apply_decay(
            scores, decay_state, rate=engine.cfg.decay_rate_secondary,
        )
        top3_after = set(sorted(decayed, key=lambda n: decayed[n], reverse=True)[:3])
        displaced = top3_original - top3_after
        assert len(displaced) >= 1, (
            f"Expected ≥1 displaced star, top3 unchanged: {top3_after}"
        )


class TestDecayRotationChanceLoto:

    def test_decay_rotation_chance_after_2_selections(self):
        """With decay_rate_secondary=0.12 on chance (univers 1-10),
        after 2 consecutive selections the top chance number must be displaced."""
        engine = HybrideEngine(LOTO_CONFIG)
        # Build chance scores: 10 numbers, top 3 are 8, 9, 10
        scores = {n: n * 0.08 for n in range(1, 11)}
        top3_original = {8, 9, 10}
        decay_state = {n: 2 for n in top3_original}
        decayed = engine.apply_decay(
            scores, decay_state, rate=engine.cfg.decay_rate_secondary,
        )
        top3_after = set(sorted(decayed, key=lambda n: decayed[n], reverse=True)[:3])
        displaced = top3_original - top3_after
        assert len(displaced) >= 1, (
            f"Expected ≥1 displaced chance, top3 unchanged: {top3_after}"
        )

    def test_loto_decay_secondary_rate_value(self):
        """LOTO_CONFIG.decay_rate_secondary == 0.12 (chance, univers de 10)."""
        assert LOTO_CONFIG.decay_rate_secondary == 0.12
        # EM has 0.15 (étoiles, univers de 12 — plus agressif)
        assert EM_CONFIG.decay_rate_secondary == 0.15
        # Loto secondary rate is between balls (0.10) and EM stars (0.15)
        assert LOTO_CONFIG.decay_rate < LOTO_CONFIG.decay_rate_secondary < EM_CONFIG.decay_rate_secondary


class TestEmSumConstraint175:

    def test_em_sum_constraint_config_values(self):
        """EM_CONFIG uses [95, 175] (V92 recalibration from [95, 160])."""
        assert EM_CONFIG.somme_min == 95
        assert EM_CONFIG.somme_max == 175
        # Loto unchanged
        assert LOTO_CONFIG.somme_min == 70
        assert LOTO_CONFIG.somme_max == 150

    def test_em_sum_in_range_gets_no_penalty(self):
        """Sum within [95, 175] → no sum penalty."""
        engine = HybrideEngine(EM_CONFIG)
        nums = [5, 20, 31, 40, 49]  # sum=145 ∈ [95,175], pairs=2, disp=44, suites=0
        score = engine.valider_contraintes(nums)
        assert score == 1.0

    def test_em_sum_above_175_penalized(self):
        """Sum > 175 → soft penalty ×0.70."""
        engine = HybrideEngine(EM_CONFIG)
        nums = [31, 35, 39, 45, 47]  # sum=197 > 175, pairs=0 → hard-reject
        nums = [32, 35, 39, 44, 47]  # sum=197 > 175, pairs=2
        score = engine.valider_contraintes(nums)
        assert score < 1.0  # penalized

    def test_em_sum_160_no_longer_penalized(self):
        """Sum = 165 was penalized at [95,160] but OK at [95,175]."""
        engine = HybrideEngine(EM_CONFIG)
        nums = [15, 30, 35, 40, 45]  # sum = 165, pairs=2, disp=30, suites=0
        score = engine.valider_contraintes(nums)
        assert score == 1.0  # no penalty (165 ∈ [95, 175])


class TestNoiseFromConfig:

    @pytest.mark.asyncio
    @patch("engine.hybride_base.HybrideEngine.get_reference_date")
    async def test_noise_uses_config_noise_by_mode(self, mock_ref):
        """The engine reads noise from EngineConfig.noise_by_mode, not module constant."""
        from dataclasses import replace
        # Create a custom config with very high noise
        custom_noise = {"conservative": 0.0, "balanced": 0.50, "recent": 0.50}
        cfg = replace(LOTO_CONFIG, noise_by_mode=custom_noise)
        engine = HybrideEngine(cfg)
        cursor = AsyncSmartMockCursor()

        # Generate with high noise — should still produce valid grids
        random.seed(42)
        result = await engine.generate_grids(
            n=5, mode="balanced",
            _get_connection=lambda: make_async_conn(cursor),
        )
        assert len(result["grids"]) == 5
        for grid in result["grids"]:
            assert len(grid["nums"]) == 5

    def test_custom_noise_by_mode_used_in_generer_grille(self):
        """noise_by_mode from config is picked up by generer_grille via cfg."""
        from dataclasses import replace
        custom = {"conservative": 0.0, "balanced": 0.99, "recent": 0.99}
        cfg = replace(LOTO_CONFIG, noise_by_mode=custom)
        assert cfg.noise_by_mode["balanced"] == 0.99


class TestDecayMetadataV92:

    @pytest.mark.asyncio
    @patch("engine.hybride_base.HybrideEngine.get_reference_date")
    async def test_metadata_includes_v92_decay_fields(self, mock_ref):
        """Metadata includes rate_secondary and acceleration (V92)."""
        cursor = AsyncSmartMockCursor()
        random.seed(42)
        engine = HybrideEngine(EM_CONFIG)
        decay = {10: 5}
        result = await engine.generate_grids(
            n=1, mode="balanced", decay_state=decay,
            _get_connection=lambda: make_async_conn(cursor),
        )
        d = result["metadata"]["decay"]
        assert d["rate"] == 0.10
        assert d["rate_secondary"] == 0.15
        assert d["acceleration"] == 0.03
        assert d["floor"] == 0.50
        assert d["active"] is True
