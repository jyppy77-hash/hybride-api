import re

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
import asyncio
import db_cloudsql

router = APIRouter()


# =========================
# Mapping URL → fichier HTML (reference SEO)
# =========================

SEO_PAGES = {
    "/": "launcher.html",
    "/accueil": "accueil.html",
    "/loto": "loto.html",
    "/loto/analyse": "simulateur.html",
    "/loto/exploration": "loto.html",
    "/loto/statistiques": "statistiques.html",
    "/loto/intelligence-artificielle": "loto-ia.html",
    "/loto/numeros-les-plus-sortis": "numeros-les-plus-sortis.html",
    "/faq": "faq.html",
    "/news": "news.html",
    "/historique": "historique.html",
    "/methodologie": "methodologie.html",
    "/moteur": "moteur.html",
    "/a-propos": "a-propos.html",
    "/disclaimer": "disclaimer.html",
    "/mentions-legales": "mentions-legales.html",
    "/politique-confidentialite": "politique-confidentialite.html",
    "/politique-cookies": "politique-cookies.html",
}


def serve_page(filename: str):
    """Sert une page HTML depuis ui/."""
    return FileResponse(f"ui/{filename}", media_type="text/html")


def serve_page_with_canonical(filename: str, canonical_url: str):
    """Sert une page HTML en remplaçant la balise canonical (SEO dedup)."""
    with open(f"ui/{filename}", "r", encoding="utf-8") as f:
        html = f.read()
    html = re.sub(
        r'<link\s+rel="canonical"\s+href="[^"]*"',
        f'<link rel="canonical" href="{canonical_url}"',
        html,
        count=1,
    )
    return HTMLResponse(content=html)


# =========================
# Routes SEO - Fichiers racine
# =========================

@router.get("/robots.txt")
async def robots():
    """Robots.txt pour SEO."""
    return FileResponse("ui/robots.txt", media_type="text/plain",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/sitemap.xml")
async def sitemap():
    """Sitemap XML pour SEO."""
    return FileResponse("ui/sitemap.xml", media_type="application/xml",
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("favicon.ico")


@router.get("/BingSiteAuth.xml")
def bing_auth():
    return FileResponse("BingSiteAuth.xml")


# =========================
# Routes SEO-friendly (Pages HTML)
# =========================

# Page d'accueil (launcher / choix des moteurs)
@router.get("/")
async def page_launcher():
    return serve_page("launcher.html")


# =========================
# Routes Loto France (SaaS)
# =========================

@router.get("/accueil")
async def page_accueil():
    """Accueil Loto France (fallback pour liens existants)."""
    return serve_page("accueil.html")


@router.get("/loto")
async def page_loto():
    """Loto France — Exploration de grilles (generateur)."""
    return serve_page("loto.html")


@router.get("/loto/analyse")
async def page_loto_analyse():
    """Loto France — Analyse de grille (simulateur)."""
    return serve_page_with_canonical("simulateur.html", "https://lotoia.fr/loto/analyse")


@router.get("/loto/exploration")
async def page_loto_exploration():
    """Loto France — Exploration de grilles (generateur)."""
    return serve_page_with_canonical("loto.html", "https://lotoia.fr/loto")


@router.get("/loto/statistiques")
async def page_loto_statistiques():
    """Loto France — Statistiques et historique."""
    return serve_page_with_canonical("statistiques.html", "https://lotoia.fr/loto/statistiques")


@router.get("/loto/intelligence-artificielle")
async def page_loto_ia():
    """Loto France — Page pilier IA et analyse statistique."""
    return serve_page("loto-ia.html")


@router.get("/loto/numeros-les-plus-sortis")
async def page_loto_numeros():
    """Loto France — Numéros les plus sortis (classement fréquences)."""
    return serve_page("numeros-les-plus-sortis.html")


## /statistiques et /simulateur supprimés — 301 vers /loto/statistiques et /loto/analyse (main.py)


@router.get("/faq")
async def page_faq():
    try:
        total = await asyncio.to_thread(db_cloudsql.get_tirages_count)
    except Exception:
        total = 967  # fallback
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
