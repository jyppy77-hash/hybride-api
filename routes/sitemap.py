"""
Dynamic XML sitemap for LotoIA.
Includes FR Loto pages (static) + EuroMillions pages for all ENABLED_LANGS.
Replaces the old static ui/sitemap.xml.
"""
from datetime import date

from fastapi import APIRouter, Response

from config.templates import EM_URLS, BASE_URL
from config import killswitch

router = APIRouter()

# ── Static Loto pages (FR only) ─────────────────────────────────────────

_LOTO_PAGES = [
    ("/",                                1.0,  "daily"),
    ("/accueil",                         0.9,  "daily"),
    ("/loto",                            0.95, "daily"),
    ("/loto/analyse",                    0.85, "daily"),
    ("/loto/statistiques",               0.85, "daily"),
    ("/moteur",                          0.8,  "monthly"),
    ("/methodologie",                    0.8,  "monthly"),
    ("/historique",                      0.7,  "daily"),
    ("/loto/intelligence-artificielle",  0.85, "monthly"),
    ("/loto/numeros-les-plus-sortis",    0.85, "daily"),
    ("/hybride",                         0.8,  "monthly"),
    ("/a-propos",                        0.6,  "monthly"),
    ("/faq",                             0.6,  "monthly"),
    ("/news",                            0.5,  "weekly"),
]

# ── EM page priorities ───────────────────────────────────────────────────

_EM_PAGE_PRIORITY = {
    "home":         (0.9,  "daily"),
    "generateur":   (0.85, "daily"),
    "simulateur":   (0.85, "daily"),
    "statistiques": (0.85, "daily"),
    "historique":   (0.7,  "daily"),
    "faq":          (0.6,  "monthly"),
    "news":         (0.5,  "weekly"),
}


def _url_block(loc: str, lastmod: str, freq: str, priority: float) -> str:
    return (
        f"  <url>\n"
        f"    <loc>{loc}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{freq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        f"  </url>"
    )


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    """Dynamic XML sitemap — Loto FR + EuroMillions multilang."""
    today = date.today().isoformat()
    blocks = []

    # Loto pages (always FR)
    for path, priority, freq in _LOTO_PAGES:
        blocks.append(_url_block(f"{BASE_URL}{path}", today, freq, priority))

    # EuroMillions pages for each enabled language
    seen = set()
    for lang in killswitch.ENABLED_LANGS:
        lang_urls = EM_URLS.get(lang, {})
        for page_key, (priority, freq) in _EM_PAGE_PRIORITY.items():
            page_url = lang_urls.get(page_key)
            if page_url and page_url not in seen:
                seen.add(page_url)
                blocks.append(_url_block(
                    f"{BASE_URL}{page_url}", today, freq, priority,
                ))

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(blocks)
        + "\n</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")
