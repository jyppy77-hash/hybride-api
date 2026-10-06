import re

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
import db_cloudsql
from config.templates import MIN_REVIEWS_FOR_RATING
from config.version import LAST_DEPLOY_DATE
from services.loto_key_figures import (
    CACHE_CONTROL, get_key_figures_snapshot, if_none_match_hit,
    page_etag, page_last_modified, render_key_figures,
)

router = APIRouter()


# =========================
# Mapping URL → fichier HTML (reference SEO)
# =========================

SEO_PAGES = {
    "/accueil": "accueil.html",
    "/loto": "loto.html",
    "/loto/analyse": "simulateur.html",
    "/loto/statistiques": "statistiques.html",
    "/loto/intelligence-artificielle": "loto-ia.html",
    "/loto/numeros-les-plus-sortis": "numeros-les-plus-sortis.html",
    "/loto/paires": "paires.html",
    "/faq": "faq.html",
    "/news": "news.html",
    "/historique": "historique.html",
    "/methodologie": "methodologie.html",
    "/moteur": "moteur.html",
    "/hybride": "hybride.html",
    "/a-propos": "a-propos.html",
    "/disclaimer": "disclaimer.html",
    "/mentions-legales": "mentions-legales.html",
    "/politique-confidentialite": "politique-confidentialite.html",
    "/politique-cookies": "politique-cookies.html",
}


def serve_page(filename: str):
    """Sert une page HTML depuis ui/."""
    return FileResponse(f"ui/{filename}", media_type="text/html")


def _read_with_canonical(filename: str, canonical_url: str) -> str:
    """Lit une page HTML de ui/ en remplaçant la balise canonical (SEO dedup)."""
    with open(f"ui/{filename}", "r", encoding="utf-8") as f:
        html = f.read()
    return re.sub(
        r'<link\s+rel="canonical"\s+href="[^"]*"',
        f'<link rel="canonical" href="{canonical_url}"',
        html,
        count=1,
    )


def serve_page_with_canonical(filename: str, canonical_url: str):
    """Sert une page HTML en remplaçant la balise canonical (SEO dedup)."""
    return HTMLResponse(content=_read_with_canonical(filename, canonical_url))


# =========================
# Routes SEO - Fichiers racine
# =========================

@router.get("/robots.txt")
async def robots():
    """Robots.txt pour SEO."""
    return FileResponse("ui/robots.txt", media_type="text/plain",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/.well-known/traffic-advice")
async def traffic_advice():
    """Chrome prefetch proxy opt-in (traffic-advice spec)."""
    return JSONResponse(
        [{"user_agent": "prefetch-proxy", "fraction": 1.0}],
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/BingSiteAuth.xml")
async def bing_site_auth():
    """Bing Webmaster Tools verification file."""
    return FileResponse("ui/BingSiteAuth.xml", media_type="application/xml",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("favicon.ico")




# =========================
# Routes SEO-friendly (Pages HTML)
# =========================

# =========================
# Routes Loto France (SaaS)
# =========================

@router.get("/accueil")
async def page_accueil():
    """Accueil Loto France — schema JSON-LD dynamique (ratings)."""
    try:
        async with db_cloudsql.get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute("SELECT review_count, avg_rating FROM ratings_global")
            result = await cursor.fetchone()
        review_count = int(result["review_count"]) if result and result.get("review_count") else 0
        avg_rating = float(result["avg_rating"]) if result and result.get("avg_rating") else 0
    except Exception:
        review_count = 0
        avg_rating = 0

    with open("ui/accueil.html", "r", encoding="utf-8") as f:
        html = f.read()

    # Injecter le schema dynamique seulement si assez de vrais avis
    if review_count >= MIN_REVIEWS_FOR_RATING:
        html = html.replace("__RATING_VALUE__", str(avg_rating))
        html = html.replace("__RATING_COUNT__", str(review_count))
    else:
        # Retirer le bloc AggregateRating (eviter penalite Google)
        html = html.replace(
            ',\n        "aggregateRating": {\n'
            '          "@type": "AggregateRating",\n'
            '          "ratingValue": "__RATING_VALUE__",\n'
            '          "ratingCount": "__RATING_COUNT__",\n'
            '          "bestRating": "5",\n'
            '          "worstRating": "1"\n'
            '        }',
            ""
        )

    return HTMLResponse(content=html)


@router.get("/loto")
async def page_loto():
    """Loto France — Exploration de grilles (generateur)."""
    return serve_page("loto.html")


@router.get("/loto/analyse")
async def page_loto_analyse():
    """Loto France — Analyse de grille (simulateur)."""
    return serve_page_with_canonical("simulateur.html", "https://lotoia.fr/loto/analyse")


## /loto/exploration supprimé — 301 vers /loto (main.py, dedup SEO audit 2026-06-10 #9)


@router.get("/loto/statistiques")
async def page_loto_statistiques(request: Request):
    """Loto France — Statistiques : bloc « chiffres clés » rendu serveur (Cycle 2A 1B).

    ETag / Last-Modified / 304 gérés ici (main._DATA_DATED_ROUTES) : liés au dernier tirage,
    ou identiques au middleware en fallback (snapshot indisponible). Jamais de 500.
    """
    snap = await get_key_figures_snapshot()
    headers = {
        "ETag": page_etag(snap),
        "Last-Modified": page_last_modified(snap),
        "Cache-Control": CACHE_CONTROL,
    }
    if request.method == "GET" and if_none_match_hit(request.headers.get("if-none-match"), headers["ETag"]):
        return Response(status_code=304, headers=headers)
    html = _read_with_canonical("statistiques.html", "https://lotoia.fr/loto/statistiques")
    return HTMLResponse(content=render_key_figures(html, snap), headers=headers)


@router.get("/loto/intelligence-artificielle")
async def page_loto_ia():
    """Loto France — Page pilier IA et analyse statistique."""
    with open("ui/loto-ia.html", "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__DATE_MODIFIED__", LAST_DEPLOY_DATE)
    return HTMLResponse(content=html)


@router.get("/loto/numeros-les-plus-sortis")
async def page_loto_numeros():
    """Loto France — Numéros les plus sortis (classement fréquences)."""
    with open("ui/numeros-les-plus-sortis.html", "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__DATE_MODIFIED__", LAST_DEPLOY_DATE)
    return HTMLResponse(content=html)


@router.get("/loto/paires")
async def page_loto_paires():
    """Loto France — Paires de numéros (co-occurrences et classement)."""
    return serve_page("paires.html")


## /statistiques et /simulateur supprimés — 301 vers /loto/statistiques et /loto/analyse (main.py)


@router.get("/faq")
async def page_faq():
    try:
        total = await db_cloudsql.get_tirages_count()
    except Exception:
        total = 1000  # fallback arrondi
    with open("ui/faq.html", "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__DB_TOTAL__", str(total))
    return HTMLResponse(content=html)


@router.get("/news")
async def page_news():
    return serve_page("news.html")


@router.get("/historique")
async def page_historique():
    return serve_page("historique.html")


# Pages produit/documentation
@router.get("/methodologie")
async def page_methodologie():
    return serve_page("methodologie.html")


@router.get("/moteur")
async def page_moteur():
    return serve_page("moteur.html")


@router.get("/hybride")
async def page_hybride():
    """HYBRIDE — Chatbot IA Grounded de LotoIA."""
    return serve_page("hybride.html")


@router.get("/a-propos")
async def page_a_propos():
    """À propos de LotoIA (E-E-A-T)."""
    return serve_page("a-propos.html")


# Pages legales
@router.get("/disclaimer")
async def page_disclaimer():
    return serve_page("disclaimer.html")


@router.get("/mentions-legales")
async def page_mentions():
    return serve_page("mentions-legales.html")


@router.get("/politique-confidentialite")
async def page_confidentialite():
    return serve_page("politique-confidentialite.html")


@router.get("/politique-cookies")
async def page_cookies():
    return serve_page("politique-cookies.html")
