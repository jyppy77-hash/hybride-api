"""V127 — Tests parsing OWNER_IPV6 avec séparateur `|` (multi-IP).

Audit V126.1 : `middleware/em_access_control.py` produisait 8 warnings/24h
"Invalid OWNER_IPV6=...|...". Fix V127 = délégation à utils.is_owner_ip
(single source of truth, supporte déjà `|` depuis V113).
"""

import importlib
import logging
import os

import pytest


def _reload_modules_with_env(env: dict):
    """Recharge utils + em_access_control avec un env var custom."""
    for k, v in env.items():
        os.environ[k] = v
    import utils
    import middleware.em_access_control as em_mod
    importlib.reload(utils)
    importlib.reload(em_mod)
    return utils, em_mod


@pytest.fixture
def reset_env():
    saved = {k: os.environ.get(k) for k in ("OWNER_IP", "OWNER_IPV6")}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import utils
    import middleware.em_access_control as em_mod
    importlib.reload(utils)
    importlib.reload(em_mod)


def test_pipe_separator_no_warning_at_import(reset_env, caplog):
    """V127 : `OWNER_IPV6="ip1|ip2"` → aucun warning au reload."""
    with caplog.at_level(logging.WARNING):
        _reload_modules_with_env({
            "OWNER_IPV6": "2a01:cb05:8700:5900|2a01:cb09:8047:361e",
        })
    # Aucun "Invalid OWNER_IPV6" dans les logs
    assert not any("Invalid OWNER_IPV6" in rec.message for rec in caplog.records)


def test_em_owner_ip_matches_first_segment(reset_env):
    _, em_mod = _reload_modules_with_env({
        "OWNER_IPV6": "2a01:cb05:8700:5900|2a01:cb09:8047:361e",
    })
    # IP dans le premier /64
    assert em_mod.is_owner_ip("2a01:cb05:8700:5900::abcd:1234") is True


def test_em_owner_ip_matches_second_segment(reset_env):
    _, em_mod = _reload_modules_with_env({
        "OWNER_IPV6": "2a01:cb05:8700:5900|2a01:cb09:8047:361e",
    })
    # IP dans le deuxième /64
    assert em_mod.is_owner_ip("2a01:cb09:8047:361e::dead:beef") is True


def test_em_owner_ip_rejects_non_owner_v6(reset_env):
    _, em_mod = _reload_modules_with_env({
        "OWNER_IPV6": "2a01:cb05:8700:5900|2a01:cb09:8047:361e",
    })
    # IP /64 non-owner
    assert em_mod.is_owner_ip("2001:db8::1") is False


def test_em_owner_ip_loopback_always_owner(reset_env):
    _, em_mod = _reload_modules_with_env({
        "OWNER_IPV6": "2a01:cb05:8700:5900",
    })
    assert em_mod.is_owner_ip("127.0.0.1") is True
    assert em_mod.is_owner_ip("::1") is True
