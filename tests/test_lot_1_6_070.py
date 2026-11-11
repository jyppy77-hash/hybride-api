"""
Tests — Lot 1.6.070 (12/11/2026) : BOT_IPS — URL Google ipranges déplacées, sources user_triggered retirées.

  T1  les sources Google pointent sur /static/crawling/ipranges/ (plus aucune URL /static/search/apis/).
  T2  googlebot → common-crawlers.json ; google_special → special-crawlers.json.
  T3  user_triggered absentes de WHITELIST_JSON_SOURCES ET des sources attendues du widget (expected_sources).
  T4  sources attendues du widget = sources rafraîchies (ni fantôme, ni oubli) ; 7 sources.
  T5  refresh simulé : 7 appels, aucune URL user-triggered ni /search/apis/, 0 erreur.
  T6  version : plancher 1.6.070.
  T7  IPv6 : un ipv6Prefix simulé entre dans la liste blanche et is_whitelisted_bot le reconnaît.
  T8  échec d'une source de la liste blanche → ERROR ; échec d'une source de la liste noire → WARNING.

Les tests qui appellent refresh_from_remote sauvegardent puis restaurent l'état global du module
(listes fusionnées), pour ne dépendre d'aucun ordre d'exécution.
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import bot_ips
from config.bot_ips import (
    BLACKLIST_JSON_SOURCES,
    BLACKLIST_TEXT_SOURCES,
    WHITELIST_JSON_SOURCES,
    is_whitelisted_bot,
    refresh_from_remote,
)

pytestmark = pytest.mark.usefixtures("db_unavailable")

_GOOGLE_BASE = "https://developers.google.com/static/crawling/ipranges/"


@pytest.fixture
def bot_ips_state():
    """Sauvegarde / restaure l'état global de config.bot_ips ; vide les listes statiques pendant le test."""
    saved = (bot_ips._whitelist_networks, bot_ips._blacklist_networks, bot_ips._blacklist_ips)
    with patch.object(bot_ips, "_STATIC_WHITELIST_CIDRS", []), \
         patch.object(bot_ips, "_STATIC_BLACKLIST_CIDRS", []):
        yield
    bot_ips._whitelist_networks, bot_ips._blacklist_networks, bot_ips._blacklist_ips = saved


def _ok_client(prefixes, calls=None):
    """Client simulé : 200 pour toute URL, même JSON, liste texte de 119 IP."""
    async def fake_get(url, **kwargs):
        if calls is not None:
            calls.append(url)
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"prefixes": prefixes})
        resp.text = "\n".join(f"192.0.2.{i}" for i in range(1, 120))
        return resp

    client = AsyncMock()
    client.get = AsyncMock(side_effect=fake_get)
    return client


async def _expected_sources() -> list[str]:
    from services.bot_feeds_monitor import get_feeds_status
    with patch("db_cloudsql.async_fetchall", new=AsyncMock(return_value=[])):
        result = await get_feeds_status()
    return [f["source"] for f in result["feeds"]]


def test_t1_google_sources_new_path():
    google = {k: v for k, v in WHITELIST_JSON_SOURCES.items() if "developers.google.com" in v}
    assert set(google) == {"googlebot", "google_special"}
    for url in google.values():
        assert url.startswith(_GOOGLE_BASE)
    all_urls = [*WHITELIST_JSON_SOURCES.values(), *BLACKLIST_JSON_SOURCES.values(), *BLACKLIST_TEXT_SOURCES.values()]
    assert not any("/static/search/apis/" in u for u in all_urls)


def test_t2_google_file_names():
    assert WHITELIST_JSON_SOURCES["googlebot"] == _GOOGLE_BASE + "common-crawlers.json"
    assert WHITELIST_JSON_SOURCES["google_special"] == _GOOGLE_BASE + "special-crawlers.json"


@pytest.mark.asyncio
async def test_t3_user_triggered_absent_from_sources_and_expected():
    for name, url in WHITELIST_JSON_SOURCES.items():
        assert "user_triggered" not in name
        assert "user-triggered" not in url
    expected = await _expected_sources()
    assert not any("user_triggered" in s for s in expected)
    assert "google_user_triggered" not in expected
    assert "google_user_triggered2" not in expected


@pytest.mark.asyncio
async def test_t4_expected_sources_match_refresh_sources():
    expected = await _expected_sources()
    refreshed = [*WHITELIST_JSON_SOURCES, *BLACKLIST_JSON_SOURCES, *BLACKLIST_TEXT_SOURCES]
    assert sorted(expected) == sorted(refreshed)
    assert len(expected) == 7


@pytest.mark.asyncio
async def test_t5_refresh_calls_only_current_urls(bot_ips_state):
    calls: list[str] = []
    client = _ok_client([{"ipv4Prefix": "203.0.113.0/24"}, {"ipv4Prefix": "198.51.100.0/24"},
                         {"ipv6Prefix": "2001:db8::/32"}], calls)
    stats = await refresh_from_remote(client)
    assert stats["errors"] == []
    assert len(calls) == 7
    assert not any("user-triggered" in u or "/search/apis/" in u for u in calls)


def test_t6_app_version():
    from config.version import APP_VERSION, VERSION_DATE
    assert tuple(int(p) for p in APP_VERSION.split(".")) >= (1, 6, 70)
    assert VERSION_DATE >= "2026-11-12"


@pytest.mark.asyncio
async def test_t7_ipv6_prefix_whitelisted(bot_ips_state):
    client = _ok_client([{"ipv4Prefix": "203.0.113.0/24"}, {"ipv6Prefix": "2001:db8::/32"}])
    stats = await refresh_from_remote(client)
    assert stats["errors"] == []
    assert any(net.version == 6 for net in bot_ips._whitelist_networks)
    assert is_whitelisted_bot("2001:db8::1") is True
    assert is_whitelisted_bot("203.0.113.7") is True
    assert is_whitelisted_bot("2001:db9::1") is False
    assert is_whitelisted_bot("192.0.2.1") is False


@pytest.mark.asyncio
async def test_t8_whitelist_failure_error_blacklist_failure_warning(bot_ips_state, caplog):
    client = AsyncMock()
    client.get = AsyncMock(side_effect=Exception("network error"))
    with caplog.at_level(logging.WARNING, logger="config.bot_ips"):
        await refresh_from_remote(client)
    failed = [r for r in caplog.records if r.name == "config.bot_ips" and "fetch failed" in r.getMessage()]
    wl = [r for r in failed if r.getMessage().startswith("[BOT_IPS] Whitelist ")]
    bl = [r for r in failed if r.getMessage().startswith("[BOT_IPS] Blacklist ")]
    assert len(wl) == len(WHITELIST_JSON_SOURCES)
    assert len(bl) == len(BLACKLIST_JSON_SOURCES) + len(BLACKLIST_TEXT_SOURCES)
    assert all(r.levelno == logging.ERROR for r in wl)
    assert all(r.levelno == logging.WARNING for r in bl)
