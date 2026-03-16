"""
Bot IP management — Whitelist + Blacklist CIDR ranges + suspicious URL patterns.

Two data structures for optimal performance:
- WHITELIST / BLACKLIST: lists of ipaddress.IPv4Network/IPv6Network (CIDR match)
- BLACKLIST_IPS: set of individual IPs as strings (O(1) lookup for Tor/IPsum)

Static hardcoded ranges serve as fallback. Dynamic refresh adds to them.
"""

import ipaddress
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Static WHITELIST CIDR ranges (hardcoded fallback) ────────────────────────

_STATIC_WHITELIST_CIDRS = [
    # GCP Health Checks (CRITICAL)
    "35.191.0.0/16",
    "130.211.0.0/22",
    "209.85.152.0/22",
    "209.85.204.0/22",
    "2600:2d00:1:b029::/64",
    "2600:2d00:1:1::/64",
    "2600:1901:8001::/48",
    # Facebook/Meta (AS32934)
    "31.13.24.0/21",
    "31.13.64.0/18",
    "45.64.40.0/22",
    "66.220.144.0/20",
    "69.63.176.0/20",
    "69.171.224.0/19",
    "157.240.0.0/16",
    "173.252.64.0/18",
    "129.134.0.0/16",
    "2a03:2880::/32",
    # Twitter/X (AS13414)
    "104.244.40.0/21",
    "199.96.56.0/21",
    "192.133.76.0/22",
    "199.16.156.0/22",
    "199.59.148.0/22",
    "69.195.160.0/19",
    "209.237.192.0/19",
    "188.64.224.0/21",
    "64.63.0.0/18",
    # LinkedIn (AS14413)
    "108.174.0.0/20",
    "144.2.0.0/19",
    "185.63.144.0/22",
    "199.101.160.0/22",
    "216.52.16.0/21",
    "2620:109:c001::/48",
    "2620:109:c002::/48",
    "2620:109:c00a::/48",
    "2620:119:50c0::/48",
    # Telegram Bot API
    "149.154.160.0/20",
    "91.108.4.0/22",
]

# ── Static BLACKLIST CIDR ranges (hardcoded fallback) ────────────────────────

_STATIC_BLACKLIST_CIDRS = [
    # ClaudeBot (Anthropic)
    "160.79.104.0/23",
    "2607:6bc0::/48",
    # PetalBot (Huawei)
    "114.119.128.0/19",
]

# ── Suspicious URL paths (instant ban on first hit) ──────────────────────────

SUSPICIOUS_PATHS = frozenset([
    # Environment files
    "/.env", "/.env.backup", "/.env.dev", "/.env.production", "/.env.local",
    "/docker-compose.yml", "/config.json", "/config.yml",
    "/.aws/credentials", "/application.yml", "/appsettings.json",
    "/database.yml", "/parameters.yml",
    # Git/VCS
    "/.git/config", "/.git/HEAD", "/.git/index",
    "/.svn/entries", "/.hg/requires", "/.bzr/README",
    "/.gitignore", "/.git-credentials",
    # Database admin panels
    "/phpmyadmin", "/pma", "/adminer", "/dbadmin",
    "/mysql", "/sql", "/manager/html", "/tomcat", "/solr",
    # WordPress (we're not WordPress!)
    "/wp-admin", "/wp-login.php", "/wp-content", "/wp-includes",
    "/xmlrpc.php", "/wp-config.php",
    # Logs
    "/error_log", "/access.log", "/debug.log",
    "/laravel.log", "/system.log",
    # Backups
    "/backup.zip", "/backup.sql", "/dump.sql", "/database.sql",
    "/source.zip", "/www.zip", "/site.tar.gz",
    # Actuator/metrics
    "/actuator/env", "/actuator/health", "/actuator/heapdump",
    "/swagger-ui.html", "/v2/api-docs", "/graphql",
    "/server-status", "/server-info",
    # PHP specific (we're not PHP!)
    "/admin.php", "/login.php", "/shell.php", "/cmd.php",
    "/eval-stdin.php", "/vendor/phpunit",
])

# ── Dynamic source URLs ──────────────────────────────────────────────────────

WHITELIST_JSON_SOURCES = {
    "googlebot": "https://developers.google.com/static/search/apis/ipranges/googlebot.json",
    "google_special": "https://developers.google.com/static/search/apis/ipranges/special-crawlers.json",
    "google_user_triggered": "https://developers.google.com/static/search/apis/ipranges/user-triggered-fetchers.json",
    "google_user_triggered2": "https://developers.google.com/static/search/apis/ipranges/user-triggered-fetchers-google.json",
    "bingbot": "https://www.bing.com/toolbox/bingbot.json",
    "applebot": "https://search.developer.apple.com/applebot.json",
}

BLACKLIST_JSON_SOURCES = {
    "gptbot": "https://openai.com/gptbot.json",
}

BLACKLIST_TEXT_SOURCES = {
    "tor_exit": "https://check.torproject.org/torbulkexitlist",
    "ipsum_l3": "https://raw.githubusercontent.com/stamparm/ipsum/master/levels/3.txt",
}

# ── Runtime state ────────────────────────────────────────────────────────────

_whitelist_networks: list = []
_blacklist_networks: list = []
_blacklist_ips: set[str] = set()


def _parse_cidr_list(cidr_strings: list[str]) -> list:
    """Parse CIDR strings into ipaddress network objects, skip invalid."""
    nets = []
    for cidr in cidr_strings:
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError as e:
            logger.warning("[BOT_IPS] Invalid CIDR %s: %s", cidr, e)
    return nets


def _collapse(nets: list) -> list:
    """Collapse adjacent networks. Separate v4 and v6 before collapsing."""
    v4 = [n for n in nets if n.version == 4]
    v6 = [n for n in nets if n.version == 6]
    result = []
    try:
        result.extend(ipaddress.collapse_addresses(v4))
    except Exception:
        result.extend(v4)
    try:
        result.extend(ipaddress.collapse_addresses(v6))
    except Exception:
        result.extend(v6)
    return result


def _init_static():
    """Initialize from hardcoded static ranges (called at import time)."""
    global _whitelist_networks, _blacklist_networks
    _whitelist_networks = _collapse(_parse_cidr_list(_STATIC_WHITELIST_CIDRS))
    _blacklist_networks = _collapse(_parse_cidr_list(_STATIC_BLACKLIST_CIDRS))
    logger.info(
        "[BOT_IPS] Static init: %d whitelist networks, %d blacklist networks",
        len(_whitelist_networks), len(_blacklist_networks),
    )


# Initialize at import time (static fallback always available)
_init_static()


# ── Public API ───────────────────────────────────────────────────────────────

def is_whitelisted_bot(ip: str) -> bool:
    """Check if IP belongs to a whitelisted bot network (GCP, Google, Meta, etc.)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _whitelist_networks)


def is_blacklisted(ip: str) -> bool:
    """Check if IP is in blacklist (CIDR networks + individual IPs set)."""
    if ip in _blacklist_ips:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _blacklist_networks)


def is_suspicious_path(path: str) -> bool:
    """Check if URL path matches a suspicious pattern (startswith matching)."""
    path_lower = path.lower().split("?")[0]  # strip query string, case-insensitive
    return any(path_lower.startswith(p) for p in SUSPICIOUS_PATHS)


# ── JSON/text parsing helpers ────────────────────────────────────────────────

def _parse_google_style_json(data: dict) -> list[str]:
    """Parse Google/Bing/Apple style JSON: prefixes[].ipv4Prefix / ipv6Prefix."""
    cidrs = []
    for prefix in data.get("prefixes", []):
        if "ipv4Prefix" in prefix:
            cidrs.append(prefix["ipv4Prefix"])
        elif "ipv6Prefix" in prefix:
            cidrs.append(prefix["ipv6Prefix"])
        elif "ip_prefix" in prefix:
            cidrs.append(prefix["ip_prefix"])
    return cidrs


def _parse_text_ips(text: str) -> list[str]:
    """Parse plain text: one IP or CIDR per line, skip comments."""
    ips = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # IPsum format: "IP\tcount" — take first token
        token = line.split()[0] if line.split() else ""
        if token:
            ips.append(token)
    return ips


# ── Dynamic refresh ──────────────────────────────────────────────────────────

async def refresh_from_remote(httpx_client) -> dict:
    """
    Fetch all remote sources, rebuild whitelist + blacklist.
    Returns stats dict. Errors on individual sources don't block others.
    Merges dynamic results WITH static hardcoded ranges.
    """
    global _whitelist_networks, _blacklist_networks, _blacklist_ips

    errors = []
    dynamic_wl_cidrs: list[str] = []
    dynamic_bl_cidrs: list[str] = []
    dynamic_bl_ips: set[str] = set()

    # ── Whitelist JSON sources ──
    for name, url in WHITELIST_JSON_SOURCES.items():
        try:
            resp = await httpx_client.get(url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            cidrs = _parse_google_style_json(data)
            dynamic_wl_cidrs.extend(cidrs)
            logger.info("[BOT_IPS] Whitelist %s: %d CIDRs", name, len(cidrs))
        except Exception as e:
            errors.append(f"whitelist:{name}: {e}")
            logger.warning("[BOT_IPS] Whitelist %s fetch failed: %s", name, e)

    # ── Blacklist JSON sources ──
    for name, url in BLACKLIST_JSON_SOURCES.items():
        try:
            resp = await httpx_client.get(url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            cidrs = _parse_google_style_json(data)
            dynamic_bl_cidrs.extend(cidrs)
            logger.info("[BOT_IPS] Blacklist %s: %d CIDRs", name, len(cidrs))
        except Exception as e:
            errors.append(f"blacklist:{name}: {e}")
            logger.warning("[BOT_IPS] Blacklist %s fetch failed: %s", name, e)

    # ── Blacklist text sources ──
    for name, url in BLACKLIST_TEXT_SOURCES.items():
        try:
            resp = await httpx_client.get(url, timeout=10.0)
            resp.raise_for_status()
            entries = _parse_text_ips(resp.text)
            # Distinguish IPs from CIDRs
            for entry in entries:
                if "/" in entry:
                    dynamic_bl_cidrs.append(entry)
                else:
                    dynamic_bl_ips.add(entry)
            logger.info("[BOT_IPS] Blacklist %s: %d entries", name, len(entries))
        except Exception as e:
            errors.append(f"blacklist_text:{name}: {e}")
            logger.warning("[BOT_IPS] Blacklist %s fetch failed: %s", name, e)

    # ── Merge static + dynamic, collapse ──
    all_wl = _parse_cidr_list(_STATIC_WHITELIST_CIDRS) + _parse_cidr_list(dynamic_wl_cidrs)
    all_bl = _parse_cidr_list(_STATIC_BLACKLIST_CIDRS) + _parse_cidr_list(dynamic_bl_cidrs)

    _whitelist_networks = _collapse(all_wl)
    _blacklist_networks = _collapse(all_bl)
    _blacklist_ips = dynamic_bl_ips

    stats = {
        "whitelist_networks": len(_whitelist_networks),
        "blacklist_networks": len(_blacklist_networks),
        "blacklist_ips": len(_blacklist_ips),
        "errors": errors,
    }
    logger.info("[BOT_IPS] Refresh complete: %s", stats)
    return stats
