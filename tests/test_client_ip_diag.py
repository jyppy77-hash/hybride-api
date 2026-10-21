"""
Tests — LOT 1.6.057 : diagnostic CLIENT_IP_DIAG (mesure de _GOOGLE_XFF_HOPS).

LOT 1.6.058 : get_client_ip / get_client_ip_from_scope appliquent hops[-_GOOGLE_XFF_HOPS] (N = 1,
tests/test_client_ip_selection.py) ; le diagnostic est conservé, désactivé par défaut (CLIENT_IP_DIAG=1).
"""

import re

import pytest

import utils
from utils import (
    _diag_enabled_from_env, _entry_kind, _host_kind, _ip_kind, _is_diag_probe, _parse_ip, _select_client_ip_candidate,
    get_client_ip_from_scope, log_client_ip_diag,
)

_IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_IPV6_RE = re.compile(r"[0-9a-fA-F]{0,4}:[0-9a-fA-F]{0,4}:")
_TEST_IPS = ("8.8.8.8", "9.9.9.9", "86.212.92.243", "2a00:1450:4007::1", "10.0.0.1", "35.191.0.1")


def _scope(xff=None, host="lotoia.fr", client=("9.9.9.9", 0), path="/accueil", query=b"", extra=()):
    headers = [(b"host", host.encode())] if host else []
    if xff is not None:
        for line in (xff if isinstance(xff, list) else [xff]):
            headers.append((b"x-forwarded-for", line.encode()))
    headers += [(k.encode(), v.encode()) for k, v in extra]
    return {"type": "http", "path": path, "query_string": query, "headers": headers, "client": client}


@pytest.fixture
def diag_on(monkeypatch):
    monkeypatch.setattr(utils, "_CLIENT_IP_DIAG", True)
    monkeypatch.setattr(utils, "_diag_counts", {"general": 0, "probe": 0})


def _diag_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("[CLIENT_IP_DIAG]")]


def _field(line, key):
    """Valeur du champ `key=valeur` d'une ligne [CLIENT_IP_DIAG]."""
    return re.search(rf"\b{key}=(\S+)", line).group(1)


class TestParseIp:

    @pytest.mark.parametrize("raw,expected", [
        ("8.8.8.8", "8.8.8.8"),
        ("  8.8.8.8 ", "8.8.8.8"),
        ("8.8.8.8:5678", "8.8.8.8"),
        ("[2a00:1450:4007::1]:443", "2a00:1450:4007::1"),
        ("[2a00:1450:4007::1]", "2a00:1450:4007::1"),
        ("[2a00:1450:4007::1", ""),
        ("2A00:1450:4007::1", "2a00:1450:4007::1"),
        ("::ffff:1.2.3.4", "1.2.3.4"),
        ("unknown", ""),
        ("", ""),
        ("999.1.1.1", ""),
    ])
    def test_parse_ip_normalizes(self, raw, expected):
        assert _parse_ip(raw) == expected


class TestKinds:

    @pytest.mark.parametrize("ip,kind", [
        ("", "empty"), ("testclient", "invalid"), ("8.8.8.8", "public"), ("10.0.0.1", "private"),
        ("127.0.0.1", "private"), ("169.254.1.1", "private"), ("2a00:1450:4007::1", "public"),
    ])
    def test_ip_kind(self, ip, kind):
        assert _ip_kind(ip) == kind

    @pytest.mark.parametrize("raw,kind", [
        ("", "empty"), ("   ", "empty"), ("unknown", "invalid"), ("testclient", "invalid"),
        (" 8.8.8.8:443 ", "public"), ("[2a00:1450:4007::1]:443", "public"), ("10.0.0.1", "private"),
    ])
    def test_entry_kind(self, raw, kind):
        assert _entry_kind(raw) == kind

    @pytest.mark.parametrize("host,kind", [
        ("lotoia.fr", "apex"), ("LOTOIA.FR:443", "apex"), ("www.lotoia.fr", "www"),
        ("hybride-api-eu-y3klofq25q-ew.a.run.app", "run_app"), ("localhost:8099", "other"), ("", "none"),
    ])
    def test_host_kind(self, host, kind):
        assert _host_kind(host) == kind

    @pytest.mark.parametrize("raw,enabled", [
        (None, False), ("", False), ("1", True), ("true", True), (" ON ", True), ("yes", True),
        ("0", False), ("false", False), ("NO", False), (" off ", False), ("2", False),
    ])
    def test_env_parsing(self, raw, enabled):
        assert _diag_enabled_from_env(raw) is enabled


class TestSelectClientIpCandidate:

    def test_n1_takes_last_entry(self):
        assert _select_client_ip_candidate("86.212.92.243, 8.8.8.8", "x", 1) == "8.8.8.8"

    def test_n2_takes_second_to_last(self):
        assert _select_client_ip_candidate("86.212.92.243, 8.8.8.8, 35.191.0.1", "x", 2) == "8.8.8.8"

    def test_forged_owner_first_is_never_selected(self):
        for hops in (1, 2):
            xff = "86.212.92.243, 8.8.8.8, 35.191.0.1"
            assert _select_client_ip_candidate(xff, "x", hops) != "86.212.92.243"

    def test_too_short_returns_empty(self):
        assert _select_client_ip_candidate("8.8.8.8", "x", 2) == ""

    def test_invalid_entry_returns_empty(self):
        assert _select_client_ip_candidate("8.8.8.8, unknown", "x", 1) == ""

    def test_no_xff_returns_fallback(self):
        assert _select_client_ip_candidate("", "testclient", 1) == "testclient"
        assert _select_client_ip_candidate("   ", "9.9.9.9", 2) == "9.9.9.9"

    def test_ipv6_port_and_spaces(self):
        assert _select_client_ip_candidate("1.1.1.1 ,  [2A00:1450:4007::1]:443 ", "x", 1) == "2a00:1450:4007::1"

    def test_hops_below_one_returns_empty(self):
        assert _select_client_ip_candidate("8.8.8.8", "x", 0) == ""


class TestScopeSelection:
    """LOT 1.6.058 : get_client_ip_from_scope = hops[-1], toutes les lignes XFF jointes dans l'ordre."""

    def test_single_line_returns_last_entry(self):
        assert get_client_ip_from_scope(_scope(xff="86.212.92.243, 8.8.8.8")) == "8.8.8.8"

    def test_single_entry(self):
        assert get_client_ip_from_scope(_scope(xff="8.8.8.8")) == "8.8.8.8"

    def test_several_lines_joined_in_order(self):
        assert get_client_ip_from_scope(_scope(xff=["1.1.1.1", "2.2.2.2, 8.8.8.8"])) == "8.8.8.8"

    def test_no_xff_returns_peer(self):
        assert get_client_ip_from_scope(_scope(xff=None, client=("9.9.9.9", 1234))) == "9.9.9.9"

    def test_no_xff_no_client_returns_empty(self):
        assert get_client_ip_from_scope(_scope(xff=None, client=None)) == ""


class TestProbeMarker:

    @pytest.mark.parametrize("path,query,expected", [
        ("/api/version", b"", False),
        ("/api/version", b"cidiag=1", True),
        ("/api/version", b"x=1&cidiag=1", True),
        ("/api/version", b"cidiag=0", False),
        ("/api/version", b"cidiag=10", False),
        ("/accueil", b"cidiag=1", False),
    ])
    def test_is_diag_probe(self, path, query, expected):
        assert _is_diag_probe(_scope(path=path, query=query)) is expected

    def test_missing_query_string_key(self):
        scope = _scope(path="/api/version")
        del scope["query_string"]
        assert _is_diag_probe(scope) is False

    def test_version_without_marker_uses_general_quota(self, diag_on, caplog):
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff="8.8.8.8", path="/api/version"))
        assert _field(_diag_lines(caplog)[0], "probe") == "False"
        assert utils._diag_counts == {"general": 1, "probe": 0}

    def test_version_with_marker_uses_probe_quota(self, diag_on, caplog):
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff="8.8.8.8", path="/api/version", query=b"cidiag=1"))
        assert _field(_diag_lines(caplog)[0], "probe") == "True"
        assert utils._diag_counts == {"general": 0, "probe": 1}

    def test_marker_does_not_change_candidates(self, diag_on, caplog):
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff="86.212.92.243, 8.8.8.8", path="/api/version"))
            log_client_ip_diag(_scope(xff="86.212.92.243, 8.8.8.8", path="/api/version", query=b"cidiag=1"))
        plain, marked = _diag_lines(caplog)
        assert plain.replace("probe=False", "probe=True") == marked


class TestDiagLog:

    def test_disabled_logs_nothing(self, monkeypatch, caplog):
        monkeypatch.setattr(utils, "_CLIENT_IP_DIAG", False)
        monkeypatch.setattr(utils, "_diag_counts", {"general": 0, "probe": 0})
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff="8.8.8.8"))
        assert _diag_lines(caplog) == []
        assert utils._diag_counts == {"general": 0, "probe": 0}

    def test_enabled_logs_one_line_with_fields(self, diag_on, caplog):
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff="86.212.92.243, 8.8.8.8, 10.0.0.1"))
        lines = _diag_lines(caplog)
        assert len(lines) == 1
        line = lines[0]
        assert _field(line, "host") == "apex"
        assert _field(line, "probe") == "False"
        assert _field(line, "xff_lines") == "1"
        assert _field(line, "xff_len") == "3"
        assert _field(line, "hop_kinds") == "public,public,private"
        assert _field(line, "cand_n1") == "private"
        assert _field(line, "cand_n2") == "public"
        # 1.6.058 : l'IP retenue est hops[-1] = candidate N = 1.
        assert _field(line, "same_as_current_n1") == "True"
        assert _field(line, "same_as_current_n2") == "False"
        assert _field(line, "peer") == "public"

    def test_normal_visitor_same_as_current(self, diag_on, caplog):
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff="8.8.8.8"))
        assert _field(_diag_lines(caplog)[0], "same_as_current_n1") == "True"

    def test_no_xff_uses_peer(self, diag_on, caplog):
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff=None, client=("testclient", 50000)))
        line = _diag_lines(caplog)[0]
        assert _field(line, "xff_len") == "0"
        assert _field(line, "hop_kinds") == "-"
        assert _field(line, "same_as_current_n1") == "True"
        assert _field(line, "peer") == "invalid"

    def test_hop_kinds_distinguish_empty_and_invalid(self, diag_on, caplog):
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff="unknown, , 8.8.8.8"))
        line = _diag_lines(caplog)[0]
        assert _field(line, "hop_kinds") == "invalid,empty,public"
        assert _field(line, "cand_n2") == "empty"

    def test_two_xff_lines_joined_in_order(self, diag_on, caplog):
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff=["1.1.1.1", "2.2.2.2, 8.8.8.8"]))
        line = _diag_lines(caplog)[0]
        assert _field(line, "xff_lines") == "2"
        assert _field(line, "xff_len") == "3"

    def test_cloudflare_and_origin_auth_headers_have_no_effect(self, diag_on, caplog):
        base = _scope(xff="86.212.92.243, 8.8.8.8", client=("173.245.48.1", 0))
        forged = _scope(xff="86.212.92.243, 8.8.8.8", client=("173.245.48.1", 0),
                        extra=[("cf-connecting-ip", "86.212.92.243"), ("x-origin-auth", "secret")])
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(base)
            log_client_ip_diag(forged)
        first, second = _diag_lines(caplog)
        assert first == second

    @pytest.mark.parametrize("host,kind", [
        ("lotoia.fr", "apex"), ("www.lotoia.fr", "www"),
        ("hybride-api-eu-y3klofq25q-ew.a.run.app", "run_app"), ("example.org", "other"),
    ])
    def test_host_classified(self, diag_on, caplog, host, kind):
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff="8.8.8.8", host=host))
        assert _field(_diag_lines(caplog)[0], "host") == kind

    def test_no_ip_in_message(self, diag_on, caplog):
        xff = ", ".join(_TEST_IPS)
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff=xff, client=("2a00:1450:4007::1", 0)))
            log_client_ip_diag(_scope(xff=None, client=("86.212.92.243", 0)))
            log_client_ip_diag(_scope(xff=xff, path="/api/version", query=b"cidiag=1"))
        lines = _diag_lines(caplog)
        assert len(lines) == 3
        for line in lines:
            assert not _IPV4_RE.search(line)
            assert not _IPV6_RE.search(line)
            assert not any(ip in line for ip in _TEST_IPS)

    def test_hop_kinds_truncated(self, diag_on, caplog):
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff=", ".join(["8.8.8.8"] * 50)))
        line = _diag_lines(caplog)[0]
        assert _field(line, "xff_len") == "50"
        assert _field(line, "hop_kinds").startswith("...,")
        assert _field(line, "hop_kinds").count(",") == utils._DIAG_HOP_KINDS_MAX

    def test_general_cap(self, diag_on, caplog):
        with caplog.at_level("INFO", logger="utils"):
            for _ in range(utils._DIAG_MAX_GENERAL + 5):
                log_client_ip_diag(_scope(xff="8.8.8.8"))
        assert len(_diag_lines(caplog)) == utils._DIAG_MAX_GENERAL

    def test_probe_quota_is_separate(self, diag_on, caplog):
        with caplog.at_level("INFO", logger="utils"):
            for _ in range(utils._DIAG_MAX_GENERAL + 5):
                log_client_ip_diag(_scope(xff="8.8.8.8", path="/api/version"))
            for _ in range(utils._DIAG_MAX_PROBE + 5):
                log_client_ip_diag(_scope(xff="8.8.8.8", path="/api/version", query=b"cidiag=1"))
        lines = _diag_lines(caplog)
        assert len(lines) == utils._DIAG_MAX_GENERAL + utils._DIAG_MAX_PROBE
        assert sum(_field(line, "probe") == "True" for line in lines) == utils._DIAG_MAX_PROBE
        assert sum(_field(line, "probe") == "False" for line in lines) == utils._DIAG_MAX_GENERAL

    def test_internal_error_is_swallowed(self, diag_on, caplog, monkeypatch):
        def _boom(scope):
            raise RuntimeError("x")
        monkeypatch.setattr(utils, "_xff_from_scope", _boom)
        with caplog.at_level("INFO", logger="utils"):
            log_client_ip_diag(_scope(xff="8.8.8.8"))
        assert _diag_lines(caplog) == ["[CLIENT_IP_DIAG] diag_error=RuntimeError"]
