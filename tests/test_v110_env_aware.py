"""V110 env-aware activation — verifies CONFIG_SATURATION_PERSISTENT_ENABLED parsing.

These tests target the _env_bool helper directly (deterministic, no module
re-import) plus 1 smoke test that LOTO_CONFIG/EM_CONFIG default to False when
the var is absent (CI default behavior).
"""
import importlib

import pytest

from config.engine import _env_bool, LOTO_CONFIG, EM_CONFIG


class TestEnvBool:
    """Edge cases of _env_bool helper."""

    def test_returns_default_when_var_absent(self, monkeypatch):
        monkeypatch.delenv("V110_TEST_VAR", raising=False)
        assert _env_bool("V110_TEST_VAR", False) is False
        assert _env_bool("V110_TEST_VAR", True) is True

    def test_returns_false_when_var_empty(self, monkeypatch):
        """Empty string is set (not None) → strict parsing → False regardless of default."""
        monkeypatch.setenv("V110_TEST_VAR", "")
        assert _env_bool("V110_TEST_VAR", False) is False
        assert _env_bool("V110_TEST_VAR", True) is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "True", "1", "yes", "YES", "on", "ON"])
    def test_truthy_values_return_true(self, monkeypatch, value):
        monkeypatch.setenv("V110_TEST_VAR", value)
        assert _env_bool("V110_TEST_VAR", False) is True
        assert _env_bool("V110_TEST_VAR", True) is True

    @pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off", "tru", "random", " "])
    def test_non_truthy_values_return_false(self, monkeypatch, value):
        """Strict truthy semantics: any non-truthy explicit value returns False
        even if default=True (fail-closed for feature flags)."""
        monkeypatch.setenv("V110_TEST_VAR", value)
        assert _env_bool("V110_TEST_VAR", False) is False
        assert _env_bool("V110_TEST_VAR", True) is False

    def test_strip_whitespace(self, monkeypatch):
        monkeypatch.setenv("V110_TEST_VAR", "  true  ")
        assert _env_bool("V110_TEST_VAR", False) is True


class TestModuleLoadDefaults:
    """Smoke: LOTO_CONFIG and EM_CONFIG resolve to False at CI module-load
    when CONFIG_SATURATION_PERSISTENT_ENABLED is not set (the CI default).
    """

    def test_loto_config_default_false(self):
        assert LOTO_CONFIG.saturation_persistent_enabled is False

    def test_em_config_default_false(self):
        assert EM_CONFIG.saturation_persistent_enabled is False

    def test_reload_with_env_set_yields_true(self, monkeypatch):
        """Re-import config.engine with the var set → both configs become True.
        Restores import state at teardown via monkeypatch + manual reload.
        """
        monkeypatch.setenv("CONFIG_SATURATION_PERSISTENT_ENABLED", "true")
        import config.engine as engine_mod
        reloaded = importlib.reload(engine_mod)
        try:
            assert reloaded.LOTO_CONFIG.saturation_persistent_enabled is True
            assert reloaded.EM_CONFIG.saturation_persistent_enabled is True
        finally:
            monkeypatch.delenv("CONFIG_SATURATION_PERSISTENT_ENABLED", raising=False)
            importlib.reload(engine_mod)  # restore default state for other tests
