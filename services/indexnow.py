"""
IndexNow integration — notify search engines (Bing, Yandex, Naver, Seznam) of URL updates.
=============================================================================================
V97: Auto-detect key from root .txt file or INDEXNOW_KEY env var.
Submits URLs via POST to api.indexnow.org/indexnow.
"""

import glob
import logging
import os
import re

import httpx

from config.templates import BASE_URL, EM_URLS
from config import killswitch

logger = logging.getLogger(__name__)

# ── Key auto-detection ───────────────────────────────────────────────────────

_HEX_KEY_RE = re.compile(r"^[0-9a-f]{32}$")

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
SITE_HOST = "lotoia.fr"


def _detect_key() -> str:
    """Read IndexNow key from env var or auto-detect from root .txt file."""
    env_key = os.getenv("INDEXNOW_KEY", "").strip()
    if env_key and _HEX_KEY_RE.match(env_key):
        return env_key
    # Auto-detect: find a .txt file at project root whose content is a 32-char hex key
    for path in glob.glob("*.txt"):
        if os.path.basename(path) in ("requirements.txt", "requirements-dev.txt"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if _HEX_KEY_RE.match(content):
                logger.info("[INDEXNOW] Key detected from %s", path)
                return content
        except Exception:
            continue
    logger.warning("[INDEXNOW] No key found — IndexNow disabled")
    return ""


INDEXNOW_KEY = _detect_key()
KEY_LOCATION = f"https://{SITE_HOST}/{INDEXNOW_KEY}.txt" if INDEXNOW_KEY else ""


# ── URL collection (mirrors sitemap.py logic) ───────────────────────────────

# Loto pages (FR only)
_LOTO_PATHS = [
    "/accueil", "/loto", "/loto/analyse", "/loto/statistiques",
    "/moteur", "/methodologie", "/historique",
    "/loto/intelligence-artificielle", "/loto/numeros-les-plus-sortis",
    "/loto/paires", "/hybride", "/a-propos", "/faq", "/news",
]

# EM page keys (same as sitemap.py _EM_PAGE_PRIORITY keys)
_EM_PAGE_KEYS = [
    "home", "generateur", "simulateur", "statistiques", "historique",
    "faq", "news", "a_propos", "moteur", "methodologie", "ia",
    "hybride_page", "paires",
]


def collect_all_urls() -> list[str]:
    """Collect all public URLs (same set as sitemap.xml)."""
    urls: list[str] = []

    # Launcher pages (6 langs)
    for lc in killswitch.ENABLED_LANGS:
        urls.append(f"{BASE_URL}/{lc}")

    # Loto FR pages
    for path in _LOTO_PATHS:
        urls.append(f"{BASE_URL}{path}")

    # EM pages (all enabled langs)
    seen: set[str] = set()
    for lang in killswitch.ENABLED_LANGS:
        lang_urls = EM_URLS.get(lang, {})
        for page_key in _EM_PAGE_KEYS:
            page_url = lang_urls.get(page_key)
            if page_url and page_url not in seen:
                seen.add(page_url)
                urls.append(f"{BASE_URL}{page_url}")

    return urls


# ── Submit to IndexNow ───────────────────────────────────────────────────────

async def submit_indexnow(urls: list[str], client: httpx.AsyncClient | None = None) -> dict:
    """POST URL list to IndexNow API.

    Returns {"status": <http_status>, "submitted": <count>} on success,
    or {"status": "error", "detail": "..."} on failure.
    """
    if not INDEXNOW_KEY:
        logger.warning("[INDEXNOW] No key configured — skipping submission")
        return {"status": "disabled", "submitted": 0}

    if not urls:
        return {"status": "empty", "submitted": 0}

    payload = {
        "host": SITE_HOST,
        "key": INDEXNOW_KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": urls,
    }

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=10.0)

    try:
        resp = await client.post(
            INDEXNOW_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        logger.info("[INDEXNOW] Submitted %d URLs — status %d", len(urls), resp.status_code)
        return {"status": resp.status_code, "submitted": len(urls)}
    except httpx.TimeoutException:
        logger.warning("[INDEXNOW] Timeout submitting %d URLs", len(urls))
        return {"status": "timeout", "submitted": 0}
    except Exception as e:
        logger.warning("[INDEXNOW] Error: %s", e)
        return {"status": "error", "detail": str(e), "submitted": 0}
    finally:
        if own_client:
            await client.aclose()


async def submit_all_sitemap_urls(client: httpx.AsyncClient | None = None) -> dict:
    """Collect all sitemap URLs and submit them to IndexNow."""
    urls = collect_all_urls()
    logger.info("[INDEXNOW] Collected %d URLs from sitemap", len(urls))
    return await submit_indexnow(urls, client=client)
