"""
Tests — LOT 1.6.058 : IP du client = entrée de X-Forwarded-For ajoutée par le Google Front End.

Mesure 1.6.057 (staging 20/10, prod 21/10, identique sur lotoia.fr et run.app) : N = 1 → hops[-1].
Preuve de la faille corrigée (staging 19/10) : /admin via run.app → 302 avec X-Forwarded-For = IP owner.
"""

from ipaddress import ip_network

import pytest
from unittest.mock import MagicMock

from starlette.datastructures import Headers

import utils
from utils import get_client_ip, get_client_ip_from_scope

_OWNER = "86.212.92.243"
_REAL = "8.8.8.8"
_PEER = "9.9.9.9"


def _lines(xff):
    return [] if xff is None else (xff if isinstance(xff, list) else [xff])


def _request(xff=None, client=_PEER, extra=(), path="/accueil"):
    """Request simulée avec de vrais Headers Starlette (plusieurs lignes X-Forwarded-For possibles)."""
    raw = [(b"x-forwarded-for", line.encode("latin-1")) for line in _lines(xff)]
    raw += [(k.encode("latin-1"), v.encode("latin-1")) for k, v in extra]
    req = MagicMock()
    req.headers = Headers(raw=raw)
    req.url.path = path
    if client is None:
        req.client = None
    else:
        req.client = MagicMock()
        req.client.host = client
    return req


def _scope(xff=None, client=_PEER, extra=()):
    headers = [(b"x-forwarded-for", line.encode("latin-1")) for line in _lines(xff)]
    headers += [(k.encode("latin-1"), v.encode("latin-1")) for k, v in extra]
    return {"type": "http", "path": "/accueil", "headers": headers,
            "client": (client, 0) if client is not None else None}


def _both(xff=None, client=_PEER, extra=()):
    """(get_client_ip, get_client_ip_from_scope) sur les mêmes entrées."""
    return get_client_ip(_request(xff, client, extra)), get_client_ip_from_scope(_scope(xff, client, extra))


def _client_ip_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("[CLIENT_IP]")]


@pytest.fixture(autouse=True)
def _reset_unusable_counter(monkeypatch):
    monkeypatch.setattr(utils, "_xff_unusable_count", 0)


@pytest.fixture
def owner_ip(monkeypatch):
    monkeypatch.setattr(utils, "_OWNER_EXACT", {"127.0.0.1", "::1", _OWNER})


class TestSelection:

    def test_measured_hops(self):
        assert utils._GOOGLE_XFF_HOPS == 1

    def test_normal_visitor_unchanged(self):
        assert _both(_REAL) == (_REAL, _REAL)

    def test_forged_one_entry_returns_right(self):
        # Le client envoie « X-Forwarded-For: <owner> », Google ajoute l'IP réelle à droite.
        assert _both(f"{_OWNER}, {_REAL}") == (_REAL, _REAL)

    def test_forged_two_entries_returns_right(self):
        assert _both(f"{_OWNER}, 1.1.1.1, {_REAL}") == (_REAL, _REAL)

    def test_two_lines_joined_in_order(self):
        assert _both([_OWNER, f"1.1.1.1, {_REAL}"]) == (_REAL, _REAL)
        assert _both([f"{_OWNER}, 1.1.1.1", _REAL]) == (_REAL, _REAL)

    @pytest.mark.parametrize("raw", [
        "2a01:cb05:8700:5900:0000:0000:0000:0001", "2A01:CB05:8700:5900::1", "2a01:cb05:8700:5900::1",
        "[2a01:cb05:8700:5900::1]:443",
    ])
    def test_ipv6_normalized(self, raw):
        assert _both(f"{_OWNER}, {raw}") == ("2a01:cb05:8700:5900::1", "2a01:cb05:8700:5900::1")

    def test_ipv4_mapped_normalized(self):
        assert _both(f"{_OWNER}, ::ffff:8.8.8.8") == (_REAL, _REAL)

    @pytest.mark.parametrize("xff", [f"{_REAL}, unknown", f"{_REAL}, ", f"{_REAL}, 999.1.1.1", "unknown", ","])
    def test_unusable_right_entry_returns_empty(self, xff):
        # Jamais une valeur fournie par le client, jamais le pair TCP (réécrit en XFF[0] par uvicorn).
        assert _both(xff) == ("", "")

    def test_fewer_entries_than_hops_returns_empty(self, monkeypatch):
        monkeypatch.setattr(utils, "_GOOGLE_XFF_HOPS", 2)
        assert _both(_REAL) == ("", "")
        assert _both(f"{_OWNER}, {_REAL}, 35.191.0.1") == (_REAL, _REAL)

    def test_absent_returns_peer(self):
        assert _both(None) == (_PEER, _PEER)

    def test_blank_returns_peer(self):
        assert _both("") == (_PEER, _PEER)
        assert _both("   ") == (_PEER, _PEER)

    def test_absent_testclient(self):
        assert _both(None, client="testclient") == ("testclient", "testclient")

    def test_absent_no_client(self):
        assert _both(None, client=None) == ("", "")

    def test_cf_connecting_ip_and_origin_auth_ignored(self):
        extra = [("cf-connecting-ip", _OWNER), ("x-origin-auth", "secret"), ("x-real-ip", _OWNER)]
        assert _both(_REAL, extra=extra) == (_REAL, _REAL)
        assert _both(None, extra=extra) == (_PEER, _PEER)

    @pytest.mark.parametrize("xff", [
        None, "", _REAL, f"{_OWNER}, {_REAL}", [_OWNER, _REAL], [f"{_OWNER}, 1.1.1.1", _REAL],
        "unknown", f"{_REAL}, ", " [2a00:1450:4007::1]:443 ", "::ffff:1.2.3.4", "2A00:1450:4007::0001",
    ])
    @pytest.mark.parametrize("client", [_PEER, "testclient", None])
    def test_parity_request_and_scope(self, xff, client):
        a, b = _both(xff, client)
        assert a == b


class TestUnusableLog:

    def test_logged_without_ip(self, caplog):
        with caplog.at_level("WARNING", logger="utils"):
            get_client_ip(_request(f"{_OWNER}, unknown"))
        lines = _client_ip_lines(caplog)
        assert lines == ["[CLIENT_IP] xff_unusable reason=invalid xff_len=2 hops=1"]

    def test_too_short_reason(self, monkeypatch, caplog):
        monkeypatch.setattr(utils, "_GOOGLE_XFF_HOPS", 2)
        with caplog.at_level("WARNING", logger="utils"):
            get_client_ip_from_scope(_scope(_REAL))
        assert _client_ip_lines(caplog) == ["[CLIENT_IP] xff_unusable reason=too_short xff_len=1 hops=2"]

    def test_capped_per_process(self, caplog):
        with caplog.at_level("WARNING", logger="utils"):
            for _ in range(utils._XFF_UNUSABLE_LOG_MAX + 5):
                get_client_ip_from_scope(_scope("unknown"))
        assert len(_client_ip_lines(caplog)) == utils._XFF_UNUSABLE_LOG_MAX

    def test_valid_or_absent_not_logged(self, caplog):
        with caplog.at_level("WARNING", logger="utils"):
            _both(_REAL)
            _both(None)
            _both(None, client=None)
        assert _client_ip_lines(caplog) == []


class TestCallersNonRegression:

    def test_check_admin_ip_forged_owner_refused(self, owner_ip):
        from routes.admin_helpers import check_admin_ip
        resp = check_admin_ip(_request(f"{_OWNER}, {_REAL}", client=_OWNER, path="/admin"))
        assert resp is not None and resp.status_code == 403

    def test_check_admin_ip_owner_appended_by_google_allowed(self, owner_ip):
        from routes.admin_helpers import check_admin_ip
        assert check_admin_ip(_request(f"1.1.1.1, {_OWNER}", path="/admin")) is None

    def test_check_admin_ip_unusable_xff_refused(self, owner_ip):
        from routes.admin_helpers import check_admin_ip
        resp = check_admin_ip(_request(f"{_OWNER}, unknown", client=_OWNER, path="/admin"))
        assert resp is not None and resp.status_code == 403

    @pytest.mark.parametrize("raw", [
        "2a01:cb05:8700:5900:180b:4c1b:2226:7349", "2A01:CB05:8700:5900:0000:0000:0000:0001",
        "[2a01:cb05:8700:5900::1]:443",
    ])
    def test_owner_ipv6_prefix_appended_by_google_is_owner(self, monkeypatch, raw):
        # OWNER_IPV6 = préfixes /64 séparés par | : la forme normalisée (compressée) reste dans le réseau.
        monkeypatch.setattr(utils, "_owner_nets_v6", [ip_network("2a01:cb05:8700:5900::/64")])
        assert utils.is_owner_ip(get_client_ip(_request(f"{_REAL}, {raw}")))
        assert utils.is_owner_ip(get_client_ip_from_scope(_scope(f"{_REAL}, {raw}")))

    def test_owner_ipv6_prefix_forged_left_is_not_owner(self, monkeypatch):
        monkeypatch.setattr(utils, "_owner_nets_v6", [ip_network("2a01:cb05:8700:5900::/64")])
        forged = f"2a01:cb05:8700:5900:180b:4c1b:2226:7349, {_REAL}"
        assert not utils.is_owner_ip(get_client_ip(_request(forged, client="2a01:cb05:8700:5900::1")))
        assert not utils.is_owner_ip(get_client_ip_from_scope(_scope(forged, client="2a01:cb05:8700:5900::1")))

    def test_ipv4_mapped_owner_compared_as_ipv4(self, owner_ip):
        # ::ffff:a.b.c.d est ramenée à a.b.c.d : comparée à OWNER_IP (IPv4), plus jamais aux préfixes IPv6.
        assert get_client_ip(_request(f"{_REAL}, ::ffff:{_OWNER}")) == _OWNER
        assert utils.is_owner_ip(get_client_ip(_request(f"{_REAL}, ::ffff:{_OWNER}")))

    def test_check_admin_ip_testclient_still_allowed(self):
        from routes.admin_helpers import check_admin_ip
        assert check_admin_ip(_request(None, client="testclient", path="/admin")) is None

    def test_ip_ban_extract_uses_right_entry(self):
        # ip_ban : bans, auto-ban et liste blanche / noire BOT_IPS utilisent cette IP.
        from middleware.ip_ban import _extract_client_ip
        assert _extract_client_ip(_request(f"{_OWNER}, {_REAL}")) == _REAL
        assert _extract_client_ip(_request(None, client="testclient")) == ""

    def test_rate_limit_key_uses_right_entry(self):
        from rate_limit import _get_real_ip, limiter
        assert _get_real_ip(_request(f"{_OWNER}, {_REAL}")) == _REAL
        # Deux visiteurs qui forgent la même valeur gardent des clés distinctes.
        assert _get_real_ip(_request(f"{_OWNER}, 1.1.1.1")) != _get_real_ip(_request(f"{_OWNER}, 2.2.2.2"))
        assert limiter._key_func is _get_real_ip

    def test_em_access_control_forged_owner_not_owner(self, owner_ip):
        from middleware.em_access_control import get_client_ip as em_get_client_ip, is_owner_ip
        assert not is_owner_ip(em_get_client_ip(_request(f"{_OWNER}, {_REAL}")))
        assert is_owner_ip(em_get_client_ip(_request(f"1.1.1.1, {_OWNER}")))

    @pytest.mark.parametrize("module,attr", [
        ("rate_limit", "get_client_ip"),
        ("routes.api_chat", "get_client_ip"),
        ("routes.api_chat_em", "get_client_ip"),
        ("routes.api_chat_unified", "get_client_ip"),
        ("routes.api_contact", "get_client_ip"),
        ("routes.api_ratings", "get_client_ip"),
        ("routes.api_track", "_get_client_ip"),
        ("routes.api_sponsor_track", "_get_client_ip"),
    ])
    def test_callers_use_shared_function(self, module, attr):
        # Limite chat 70/h (check_chat_rate), contact, votes, suivi sponsor : pas de lecture XFF locale.
        # Comparaison par module + nom : d'autres tests rechargent utils (importlib.reload).
        import importlib
        func = getattr(importlib.import_module(module), attr)
        assert (func.__module__, func.__qualname__) == ("utils", "get_client_ip")


class TestUmamiOwnerFilter:

    async def _body(self, xff):
        from main import UmamiOwnerFilterMiddleware
        html = b"<html><head></head><body>x</body></html>"

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"text/html; charset=utf-8")]})
            await send({"type": "http.response.body", "body": html})

        sent = []

        async def send(message):
            sent.append(message)

        async def receive():
            return {"type": "http.request"}

        # scope["client"] = XFF[0] : ce que fait uvicorn --forwarded-allow-ips='*'.
        scope = _scope(xff, client=xff.split(",")[0].strip(),
                       extra=[("user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")])
        await UmamiOwnerFilterMiddleware(app)(scope, receive, send)
        return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")

    @pytest.mark.asyncio
    async def test_forged_owner_not_flagged(self, owner_ip):
        assert b"__OWNER__" not in await self._body(f"{_OWNER}, {_REAL}")

    @pytest.mark.asyncio
    async def test_owner_appended_by_google_flagged(self, owner_ip):
        assert b"__OWNER__" in await self._body(f"1.1.1.1, {_OWNER}")
