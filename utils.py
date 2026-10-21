"""
Shared utilities — used across routes, middleware, and main.py.
"""

import logging
import os
import secrets
from ipaddress import ip_address, ip_network

from fastapi import Request

# ── Owner IP detection (single source of truth) ─────────────────────────────
# IPv4: exact match.  IPv6: CIDR /64 (handles privacy extensions).
# Aligned with middleware/ip_ban.py logic.

_OWNER_IP_RAW = os.environ.get("OWNER_IP", "").strip()
_OWNER_IPV6_RAW = os.environ.get("OWNER_IPV6", "").strip()

# V113: support pipe-separated multi-IP (e.g. "ip1|ip2|ip3")
# V114: support CIDR notation for IPv4 (e.g. "92.184.0.0/16")
_OWNER_EXACT: set[str] = {"127.0.0.1", "::1"}
_owner_nets_v4: list = []
for _ip in _OWNER_IP_RAW.split("|"):
    _ip = _ip.strip()
    if not _ip:
        continue
    if "/" in _ip:
        try:
            _owner_nets_v4.append(ip_network(_ip, strict=False))
        except ValueError:
            import logging as _logging
            _logging.getLogger(__name__).warning("Invalid CIDR in OWNER_IP: %s", _ip)
    else:
        _OWNER_EXACT.add(_ip)

_owner_nets_v6: list = []
for _v6_raw in _OWNER_IPV6_RAW.split("|"):
    _v6_raw = _v6_raw.strip()
    if not _v6_raw:
        continue
    # V127 — Try full IPv6 form first (ip_network strict=False truncates to /64).
    # Handles both full address "2a01:cb05:...:7349" and /64 prefix "2a01:cb05:8700:5900".
    try:
        _owner_nets_v6.append(ip_network(f"{_v6_raw}/64", strict=False))
        continue
    except ValueError:
        pass
    # Fallback: short prefix like "2a01:cb05:8700:5900" → pad with "::" to make it valid
    _v6 = _v6_raw.rstrip(":")
    if "::" not in _v6:
        _v6 += "::"
    try:
        _owner_nets_v6.append(ip_network(f"{_v6}/64", strict=False))
    except ValueError:
        pass


def is_owner_ip(ip: str) -> bool:
    """Owner IP detection — IPv4 exact + IPv6 CIDR /64 + loopback.

    S07 V94: single source of truth for owner detection.
    V113: supports pipe-separated multi-IP in OWNER_IP / OWNER_IPV6.
    V114: supports CIDR IPv4 notation (e.g. 92.184.0.0/16).
    Used by middleware/ip_ban.py, services/chat_rate_limit.py, routes/*.
    """
    if ip in _OWNER_EXACT:
        return True
    try:
        addr = ip_address(ip)
        if addr.is_loopback:
            return True
        for net in _owner_nets_v4:
            if addr in net:
                return True
        for net in _owner_nets_v6:
            if addr in net:
                return True
    except ValueError:
        pass
    return False


# ══════════════════════════════════════════════════════════════════════════════
# LOT 1.6.058 — IP du client = entrée de X-Forwarded-For ajoutée par le Google Front End
# ══════════════════════════════════════════════════════════════════════════════
# Le Google Front End ajoute l'IP du client à DROITE de X-Forwarded-For et fusionne plusieurs lignes en
# une : les entrées de gauche viennent du client et sont falsifiables. Quand X-Forwarded-For est présent,
# request.client / scope["client"] ne sont jamais retenus : uvicorn --proxy-headers
# --forwarded-allow-ips='*' (Dockerfile:59) les remplace par XFF[0], la valeur falsifiable.

_XFF_UNUSABLE_LOG_MAX = 50  # plafond PAR PROCESSUS du journal [CLIENT_IP] xff_unusable
_xff_unusable_count = 0


def _parse_ip(raw: str) -> str:
    """Normalise une entrée XFF (espaces, [IPv6]:port, IPv4:port, IPv4 mappée). "" si invalide."""
    s = raw.strip()
    if s.startswith("["):
        end = s.find("]")
        if end == -1:
            return ""
        s = s[1:end]
    elif s.count(":") == 1:
        s = s.split(":", 1)[0]
    try:
        addr = ip_address(s)
    except ValueError:
        return ""
    if addr.version == 6 and addr.ipv4_mapped:
        return str(addr.ipv4_mapped)
    return str(addr)


def _xff_from_scope(scope: dict) -> tuple[str, int]:
    """Lignes X-Forwarded-For du scope ASGI jointes dans l'ordre (RFC 9110 §5.3), et leur nombre."""
    values = [v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"x-forwarded-for"]
    return ", ".join(values), len(values)


def _log_xff_unusable(reason: str, xff_len: int) -> None:
    """[CLIENT_IP] xff_unusable : X-Forwarded-For présent mais inexploitable. Aucune IP ni valeur d'en-tête."""
    global _xff_unusable_count
    if _xff_unusable_count >= _XFF_UNUSABLE_LOG_MAX:
        return
    _xff_unusable_count += 1
    logger.warning("[CLIENT_IP] xff_unusable reason=%s xff_len=%d hops=%d", reason, xff_len, _GOOGLE_XFF_HOPS)


# Infra au 20/10/2026 : DNS seul chez Cloudflare (aucun proxy) + domain mapping Cloud Run.
# _GOOGLE_XFF_HOPS a été mesuré sur CE chemin (diagnostic 1.6.057, staging 20/10 et prod 21/10 : N = 1,
# identique sur lotoia.fr et run.app).
# Tout changement d'infrastructure (load balancer HTTPS : +2 entrées XFF ; proxy Cloudflare : IP Cloudflare)
# impose de revoir dans le MÊME lot : _GOOGLE_XFF_HOPS, cette fonction, la V138 et CF-IPCountry.
_GOOGLE_XFF_HOPS = 1


def _select_client_ip_candidate(xff: str, fallback: str, hops: int) -> str:
    """Règle du lot B à N variable (_select_client_ip en prod, N = 1 et N = 2 dans le diagnostic).

    Aucun autre en-tête n'est lu. Pas de XFF (dev local, TestClient) → fallback (pair TCP).
    Sinon → entrée ajoutée par Google, hops[-hops], normalisée ; XFF trop court ou invalide → "".
    """
    if not xff.strip():
        return fallback
    entries = xff.split(",")
    if hops < 1 or len(entries) < hops:
        return ""
    return _parse_ip(entries[-hops])


def _select_client_ip(xff: str, peer: str) -> str:
    """Règle unique de get_client_ip et get_client_ip_from_scope : hops[-_GOOGLE_XFF_HOPS].

    XFF absent ou vide → peer (pair TCP : uvicorn ne le réécrit que si XFF est non vide).
    XFF présent mais trop court, entrée vide ou non parsable → "" (jamais une valeur fournie par le
    client), journalisé sans IP. CF-Connecting-IP et X-Origin-Auth ne sont jamais lus.
    """
    ip = _select_client_ip_candidate(xff, peer, _GOOGLE_XFF_HOPS)
    if not ip and xff.strip():
        n = len(xff.split(","))
        _log_xff_unusable("too_short" if n < _GOOGLE_XFF_HOPS else "invalid", n)
    return ip


def get_client_ip(request: Request) -> str:
    """IP du client : entrée de X-Forwarded-For ajoutée par Google (règle : _select_client_ip).

    Toutes les lignes X-Forwarded-For sont jointes dans l'ordre (RFC 9110 §5.3).
    Sans X-Forwarded-For (dev local, TestClient) → request.client.host.
    """
    xff = ", ".join(request.headers.getlist("x-forwarded-for"))
    client_host = request.client.host if request.client else ""
    return _select_client_ip(xff, client_host or "")


def detect_country(request: Request) -> str | None:
    """Detect visitor country from CF-IPCountry header with Accept-Language fallback.

    CF special codes: XX (unknown), T1 (Tor) → treated as unknown.
    Returns None if unavailable.
    """
    import re
    cf = request.headers.get("cf-ipcountry", "").strip().upper()
    if cf and cf not in ("XX", "T1", ""):
        return cf
    accept_lang = request.headers.get("accept-language", "")
    if accept_lang:
        m = re.search(r"([a-z]{2})-([A-Z]{2})", accept_lang)
        if m:
            return m.group(2)
    return None


def get_client_ip_from_scope(scope: dict) -> str:
    """Même règle que get_client_ip() sur le scope ASGI brut (middlewares ASGI purs, sans Request)."""
    xff, _ = _xff_from_scope(scope)
    client_addr = scope.get("client")
    return _select_client_ip(xff, client_addr[0] if client_addr else "")


# ══════════════════════════════════════════════════════════════════════════════
# V138 — Origin Auth (anti-bypass Cloudflare → Cloud Run direct)
# ══════════════════════════════════════════════════════════════════════════════

logger = logging.getLogger(__name__)

# Lecture env var au module-load (= boot Cloud Run ou import test).
# Pattern V134 _env_bool aligné — reload module obligatoire en tests pour
# re-évaluer cette constante après monkeypatch.setenv.
#
# Si vide ou absente : helper retourne True (mode fail-open) → middleware
# laisse passer (déploiement progressif Phase 1, audit V137.D F03 P0).
# Si set : Cloudflare Transform Rule injecte X-Origin-Auth=<SECRET> sur tout
# trafic origin → handler vérifie via secrets.compare_digest (timing-safe).
_ORIGIN_AUTH_SECRET = os.environ.get("ORIGIN_AUTH_SECRET", "").strip()


def is_origin_authed(request: Request) -> bool:
    """V138 — Check if request carries the Cloudflare-injected X-Origin-Auth header.

    Returns True (= laisse passer) dans les cas suivants :
      - Pas de SECRET configuré (env var ORIGIN_AUTH_SECRET vide/absente) → fail-open
      - Header X-Origin-Auth présent ET match secret via secrets.compare_digest

    Returns False (= rejet 403 par le caller middleware) sinon.

    Helper centralisé pattern V94 S07 (is_owner_ip) / V127 (em_access_control delegation).
    Le caller middleware gère whitelist paths + logging + 403 response.
    Lecture env var au module-load — reload module obligatoire en tests (pattern V134).
    """
    # Fail-open : pas de secret configuré → mode déploiement progressif Phase 1
    if not _ORIGIN_AUTH_SECRET:
        return True
    # Lecture header (Starlette case-insensitive : .get() retourne "" si absent)
    provided = request.headers.get("x-origin-auth", "")
    if not provided:
        return False
    # secrets.compare_digest : timing-safe — empêche timing attack sur secret length
    return secrets.compare_digest(provided, _ORIGIN_AUTH_SECRET)


# ══════════════════════════════════════════════════════════════════════════════
# LOT 1.6.057 — Diagnostic CLIENT_IP_DIAG (mesure de _GOOGLE_XFF_HOPS, aucun effet)
# ══════════════════════════════════════════════════════════════════════════════
# Depuis 1.6.058, get_client_ip / get_client_ip_from_scope appliquent hops[-_GOOGLE_XFF_HOPS]. Ce bloc,
# désactivé par défaut, sert à remesurer N lors d'un changement d'infrastructure : il compare, dans un
# log sans aucune IP ni valeur d'en-tête, l'IP retenue aux candidates N = 1 et N = 2.


def _diag_enabled_from_env(raw: str | None) -> bool:
    """Désactivé par défaut depuis 1.6.058 ; CLIENT_IP_DIAG=1/true/yes/on l'active sans rebuild."""
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


_CLIENT_IP_DIAG = _diag_enabled_from_env(os.environ.get("CLIENT_IP_DIAG"))

# Plafond PAR PROCESSUS : uvicorn --workers 2 (Dockerfile:59) → au plus 200 lignes par instance.
# Quota réservé aux requêtes de mesure (/api/version?cidiag=1) : le trafic réel de /api/version
# (appelé à chaque page vue par version-inject.js) passe dans le quota général.
_DIAG_MAX_GENERAL = 80
_DIAG_MAX_PROBE = 20
_DIAG_PROBE_PATH = "/api/version"
_DIAG_PROBE_PARAM = b"cidiag=1"
_diag_counts = {"general": 0, "probe": 0}
_DIAG_HOP_KINDS_MAX = 6  # entrées de fin seulement : celles de Google sont à la fin


def _ip_kind(ip: str) -> str:
    """Classement pour le diagnostic : empty / invalid / private / public."""
    if not ip:
        return "empty"
    try:
        addr = ip_address(ip)
    except ValueError:
        return "invalid"
    return "private" if (addr.is_private or addr.is_loopback or addr.is_link_local) else "public"


def _entry_kind(raw: str) -> str:
    """Classement d'une entrée brute (XFF ou pair) : vide → empty, non parsable → invalid."""
    if not raw.strip():
        return "empty"
    ip = _parse_ip(raw)
    return _ip_kind(ip) if ip else "invalid"


def _host_kind(host: str) -> str:
    """Classement de l'en-tête Host : apex / www / run_app / other / none."""
    host = host.split(":")[0].strip().lower()
    if not host:
        return "none"
    if host.endswith(".run.app"):
        return "run_app"
    return {"lotoia.fr": "apex", "www.lotoia.fr": "www"}.get(host, "other")


def _same_ip(candidate: str, current: str) -> bool:
    """La candidate désigne-t-elle la même IP que celle retenue par get_client_ip_from_scope ?"""
    return candidate == current or (candidate != "" and candidate == _parse_ip(current))


def _is_diag_probe(scope: dict) -> bool:
    """Requête de mesure = /api/version avec le paramètre exact cidiag=1 dans la query string.

    Le marqueur sert UNIQUEMENT à choisir le quota du diagnostic : il n'a aucun effet sur l'IP
    retenue, l'accès ni la réponse.
    """
    if scope.get("path", "") != _DIAG_PROBE_PATH:
        return False
    return _DIAG_PROBE_PARAM in scope.get("query_string", b"").split(b"&")


def _diag_slot_available(probe: bool) -> bool:
    """Réserve une ligne de quota. Aucun await entre le test et l'incrément : atomique dans la boucle asyncio."""
    key = "probe" if probe else "general"
    limit = _DIAG_MAX_PROBE if probe else _DIAG_MAX_GENERAL
    if _diag_counts[key] >= limit:
        return False
    _diag_counts[key] += 1
    return True


def log_client_ip_diag(scope: dict) -> None:
    """[CLIENT_IP_DIAG] : une ligne par requête jusqu'au plafond. Aucune IP ni valeur d'en-tête loguée."""
    if not _CLIENT_IP_DIAG:
        return
    probe = _is_diag_probe(scope)
    if not _diag_slot_available(probe):
        return
    try:
        xff, xff_lines = _xff_from_scope(scope)
        entries = xff.split(",") if xff.strip() else []
        kinds = [_entry_kind(e) for e in entries[-_DIAG_HOP_KINDS_MAX:]]
        if len(entries) > _DIAG_HOP_KINDS_MAX:
            kinds.insert(0, "...")
        host = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"host"), "")
        client_addr = scope.get("client")
        peer = client_addr[0] if client_addr else ""
        current = get_client_ip_from_scope(scope)
        cand_n1 = _select_client_ip_candidate(xff, peer, 1)
        cand_n2 = _select_client_ip_candidate(xff, peer, 2)
        logger.info(
            "[CLIENT_IP_DIAG] host=%s probe=%s xff_lines=%d xff_len=%d hop_kinds=%s cand_n1=%s cand_n2=%s "
            "same_as_current_n1=%s same_as_current_n2=%s peer=%s",
            _host_kind(host), probe, xff_lines, len(entries), ",".join(kinds) or "-",
            _ip_kind(cand_n1), _ip_kind(cand_n2),
            _same_ip(cand_n1, current), _same_ip(cand_n2, current), _entry_kind(peer),
        )
    except Exception as e:
        logger.warning("[CLIENT_IP_DIAG] diag_error=%s", type(e).__name__)
