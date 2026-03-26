"""
Dynamic XML sitemap for LotoIA.
Includes FR Loto pages (static) + EuroMillions pages for all ENABLED_LANGS.
Replaces the old static ui/sitemap.xml.
"""
from fastapi import APIRouter, Response

from config.templates import EM_URLS, BASE_URL
from config.version import LAST_DEPLOY_DATE
from config import killswitch

router = APIRouter()

# ── Static Loto pages (FR only) ─────────────────────────────────────────

_LOTO_PAGES = [
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
    "home":             (0.9,  "daily"),
    "generateur":       (0.85, "daily"),
    "simulateur":       (0.85, "daily"),
    "statistiques":     (0.85, "daily"),
    "historique":       (0.7,  "daily"),
    "faq":              (0.6,  "monthly"),
    "news":             (0.5,  "weekly"),
    "a_propos":         (0.6,  "monthly"),
    "moteur":           (0.8,  "monthly"),
    "methodologie":     (0.8,  "monthly"),
    "ia":               (0.8,  "monthly"),
    "hybride_page":     (0.7,  "monthly"),
    # Legal pages excluded — they have noindex,follow meta tag
    # "mentions", "confidentialite", "cookies", "disclaimer" → not in sitemap
}

# Multilang priority factor — non-FR EM pages get reduced priority
# to signal Google that FR is the primary content language
# and prevent crawl budget dilution on Loto FR pages.
_MULTILANG_PRIORITY_FACTOR = 0.7


def _url_block(loc: str, lastmod: str, freq: str, priority: float,
               alternates: list[tuple[str, str]] | None = None) -> str:
    lines = [
        f"  <url>",
        f"    <loc>{loc}</loc>",
        f"    <lastmod>{lastmod}</lastmod>",
        f"    <changefreq>{freq}</changefreq>",
        f"    <priority>{priority}</priority>",
    ]
    if alternates:
        for hreflang, href in alternates:
            lines.append(
                f'    <xhtml:link rel="alternate" hreflang="{hreflang}" href="{href}"/>'
            )
    lines.append(f"  </url>")
    return "\n".join(lines)


def _hreflang_alternates(page_key: str) -> list[tuple[str, str]]:
    """Build [(hreflang, absolute_url), ...] for all enabled langs + x-default.

    x-default → FR for EM pages (marché principal). See config/templates.py for strategy doc.
    """
    alternates = []
    for lc in killswitch.ENABLED_LANGS:
        url = EM_URLS.get(lc, {}).get(page_key)
        if url:
            alternates.append((lc, f"{BASE_URL}{url}"))
    fr_url = EM_URLS["fr"].get(page_key)
    if fr_url:
        alternates.append(("x-default", f"{BASE_URL}{fr_url}"))
    return alternates


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    """Dynamic XML sitemap — Launcher multilang + Loto FR + EuroMillions multilang."""
    last_modified = LAST_DEPLOY_DATE
    blocks = []

    # Launcher pages (6 languages) — site entry points, highest priority
    _launcher_priorities = {"fr": 1.0, "en": 0.9}
    _launcher_alternates = [
        (lc, f"{BASE_URL}/{lc}") for lc in killswitch.ENABLED_LANGS
    # x-default → EN pour le launcher (entrée internationale, public non-FR)
    # Voir aussi config/templates.py pour la stratégie EM (x-default → FR)
    ] + [("x-default", f"{BASE_URL}/en")]
    for lc in killswitch.ENABLED_LANGS:
        prio = _launcher_priorities.get(lc, 0.8)
        blocks.append(_url_block(
            f"{BASE_URL}/{lc}", last_modified, "weekly", prio,
            alternates=_launcher_alternates,
        ))

    # Loto pages (always FR)
    for path, priority, freq in _LOTO_PAGES:
        blocks.append(_url_block(f"{BASE_URL}{path}", last_modified, freq, priority))

    # EuroMillions pages for each enabled language
    seen = set()
    for lang in killswitch.ENABLED_LANGS:
        lang_urls = EM_URLS.get(lang, {})
        for page_key, (priority, freq) in _EM_PAGE_PRIORITY.items():
            page_url = lang_urls.get(page_key)
            if page_url and page_url not in seen:
                seen.add(page_url)
                alternates = _hreflang_alternates(page_key)
                # Non-FR languages get reduced priority to protect
                # Loto FR crawl budget and signal FR as primary
                effective_priority = priority if lang == "fr" else round(
                    priority * _MULTILANG_PRIORITY_FACTOR, 2
                )
                blocks.append(_url_block(
                    f"{BASE_URL}{page_url}", last_modified, freq,
                    effective_priority,
                    alternates=alternates,
                ))

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<?xml-stylesheet type="text/xsl" href="/sitemap.xsl"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(blocks)
        + "\n</urlset>\n"
    )
    return Response(
        content=xml,
        media_type="application/xml; charset=utf-8",
    )


# ── XSL stylesheet for browser rendering ─────────────────────────────────

_SITEMAP_XSL = """\
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="2.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:sitemap="http://www.sitemaps.org/schemas/sitemap/0.9"
    xmlns:xhtml="http://www.w3.org/1999/xhtml">
<xsl:output method="html" encoding="UTF-8" indent="yes"/>
<xsl:template match="/">
<html lang="fr">
<head>
<title>Plan du site XML — LotoIA</title>
<meta name="robots" content="noindex, follow"/>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:20px 40px;background:#0f172a;color:#e2e8f0}
h1{font-size:1.4rem;color:#10b981;margin-bottom:4px}
p.info{color:#94a3b8;font-size:.85rem;margin-bottom:20px}
table{width:100%;border-collapse:collapse;font-size:.82rem}
th{background:#1e293b;color:#94a3b8;text-align:left;padding:8px 12px;font-weight:600;text-transform:uppercase;font-size:.72rem;letter-spacing:.5px}
td{padding:6px 12px;border-bottom:1px solid #1e293b}
tr:hover td{background:rgba(16,185,129,.06)}
a{color:#38bdf8;text-decoration:none}
a:hover{text-decoration:underline}
.lang{display:inline-block;background:#1e293b;color:#10b981;padding:2px 6px;border-radius:4px;font-size:.7rem;margin:1px}
.prio{color:#f59e0b;font-weight:600}
</style>
</head>
<body>
<h1>&#127760; Plan du site XML — LotoIA</h1>
<p class="info">
  <xsl:value-of select="count(sitemap:urlset/sitemap:url)"/> URLs —
  Mis à jour le <xsl:value-of select="sitemap:urlset/sitemap:url[1]/sitemap:lastmod"/>
</p>
<table>
<tr><th>#</th><th>URL</th><th>Priorité</th><th>Fréquence</th><th>Langues</th></tr>
<xsl:for-each select="sitemap:urlset/sitemap:url">
<xsl:sort select="sitemap:priority" order="descending" data-type="number"/>
<tr>
  <td><xsl:value-of select="position()"/></td>
  <td><a href="{sitemap:loc}"><xsl:value-of select="sitemap:loc"/></a></td>
  <td class="prio"><xsl:value-of select="sitemap:priority"/></td>
  <td><xsl:value-of select="sitemap:changefreq"/></td>
  <td>
    <xsl:for-each select="xhtml:link[@rel='alternate']">
      <span class="lang"><xsl:value-of select="@hreflang"/></span>
    </xsl:for-each>
  </td>
</tr>
</xsl:for-each>
</table>
</body>
</html>
</xsl:template>
</xsl:stylesheet>
"""


@router.get("/sitemap.xsl", include_in_schema=False)
async def sitemap_xsl():
    """XSL stylesheet for human-readable sitemap rendering in browsers."""
    return Response(
        content=_SITEMAP_XSL,
        media_type="application/xslt+xml; charset=utf-8",
    )
