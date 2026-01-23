from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from typing import Optional
import logging

from engine.hybride import generate, generate_grids
from engine.stats import get_global_stats
from engine.version import __version__
import db_cloudsql

# Logging
logger = logging.getLogger(__name__)

app = FastAPI(
    title="HYBRIDE API",
    description="Moteur HYBRIDE_OPTIMAL_V1 — API officielle",
    version=__version__
)

# IMPORTANT : Accepter tous les domaines (hybride-api.lotoia.fr, lotoia.fr, etc.)
# Nécessaire car Cloud Run west9 ne supporte pas le custom domain mapping
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

# Compression GZip pour performance
app.add_middleware(GZipMiddleware, minimum_size=500)


# Middleware cache headers SEO
@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path

    # Cache long pour assets statiques
    if path.startswith("/static/") or path.startswith("/ui/static/"):
        if path.endswith((".css", ".js")):
            response.headers["Cache-Control"] = "public, max-age=604800"  # 7 jours
        elif path.endswith((".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp")):
            response.headers["Cache-Control"] = "public, max-age=2592000"  # 30 jours

    # Cache court pour pages HTML (SEO routes)
    seo_routes = ["/", "/loto", "/statistiques", "/simulateur", "/faq", "/news",
                  "/historique", "/disclaimer", "/mentions-legales",
                  "/politique-confidentialite", "/politique-cookies"]
    if path.endswith(".html") or path in seo_routes:
        response.headers["Cache-Control"] = "public, max-age=3600"  # 1 heure

    return response

import os

@app.get("/debug-env")
async def debug_env():
    return {
        "DB_USER": os.getenv("DB_USER"),
        "DB_NAME": os.getenv("DB_NAME"),
        "CLOUD_SQL_CONNECTION_NAME": os.getenv("CLOUD_SQL_CONNECTION_NAME"),
        "DB_PASSWORD_DEFINED": os.getenv("DB_PASSWORD") is not None,
        "K_SERVICE": os.getenv("K_SERVICE") is not None
    }

# =========================
# Static UI
# =========================

# Sert les fichiers CSS / JS / IMAGES
app.mount("/ui/static", StaticFiles(directory="ui/static"), name="ui-static")

# Compatibilité Claude / Laragon : chemins /static/...
app.mount("/static", StaticFiles(directory="ui/static"), name="static")

# Sert les pages HTML
app.mount("/ui", StaticFiles(directory="ui"), name="ui")

# =========================
# Schemas
# =========================

class AskPayload(BaseModel):
    prompt: str


# =========================
# Schemas Tracking
# =========================

class GridData(BaseModel):
    nums: Optional[list[int]] = []
    chance: Optional[int] = 0
    score: Optional[int] = None

class TrackGridPayload(BaseModel):
    grid_id: Optional[str] = "unknown"
    grid_number: Optional[int] = 0
    grid_data: Optional[GridData] = None
    target_date: Optional[str] = "unknown"
    timestamp: Optional[int] = None
    session_id: Optional[str] = "anonymous"

class TrackAdImpressionPayload(BaseModel):
    ad_id: Optional[str] = "unknown"
    timestamp: Optional[int] = None
    session_id: Optional[str] = "anonymous"

class TrackAdClickPayload(BaseModel):
    ad_id: Optional[str] = "unknown"
    partner_id: Optional[str] = "unknown"
    timestamp: Optional[int] = None
    session_id: Optional[str] = "anonymous"

# =========================
# Routes SEO - Fichiers racine
# =========================

@app.get("/robots.txt")
async def robots():
    """Robots.txt pour SEO."""
    return FileResponse("ui/robots.txt", media_type="text/plain",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/sitemap.xml")
async def sitemap():
    """Sitemap XML pour SEO."""
    return FileResponse("ui/sitemap.xml", media_type="application/xml",
                        headers={"Cache-Control": "public, max-age=3600"})


# =========================
# Routes SEO-friendly (Pages HTML)
# =========================

# Mapping URL → fichier HTML
SEO_PAGES = {
    "/": "launcher.html",
    "/loto": "loto.html",
    "/statistiques": "statistiques.html",
    "/simulateur": "simulateur.html",
    "/faq": "faq.html",
    "/news": "news.html",
    "/historique": "historique.html",
    "/disclaimer": "disclaimer.html",
    "/mentions-legales": "mentions-legales.html",
    "/politique-confidentialite": "politique-confidentialite.html",
    "/politique-cookies": "politique-cookies.html",
}


def serve_page(filename: str):
    """Sert une page HTML depuis ui/."""
    return FileResponse(f"ui/{filename}", media_type="text/html")


# Page d'accueil (launcher)
@app.get("/")
async def page_launcher():
    return serve_page("launcher.html")


# Pages principales
@app.get("/loto")
async def page_loto():
    return serve_page("loto.html")


@app.get("/statistiques")
async def page_statistiques():
    return serve_page("statistiques.html")


@app.get("/simulateur")
async def page_simulateur():
    return serve_page("simulateur.html")


@app.get("/faq")
async def page_faq():
    return serve_page("faq.html")


@app.get("/news")
async def page_news():
    return serve_page("news.html")


@app.get("/historique")
async def page_historique():
    return serve_page("historique.html")


# Pages légales
@app.get("/disclaimer")
async def page_disclaimer():
    return serve_page("disclaimer.html")


@app.get("/mentions-legales")
async def page_mentions():
    return serve_page("mentions-legales.html")


@app.get("/politique-confidentialite")
async def page_confidentialite():
    return serve_page("politique-confidentialite.html")


@app.get("/politique-cookies")
async def page_cookies():
    return serve_page("politique-cookies.html")


# =========================
# Routes API
# =========================

@app.get("/health")
def health():
    """
    Endpoint healthcheck Cloud Run
    """
    return {
        "status": "ok",
        "engine": "HYBRIDE_OPTIMAL_V1",
        "version": __version__
    }

@app.post("/ask")
def ask(payload: AskPayload):
    """
    Endpoint principal du moteur HYBRIDE
    """
    try:
        result = generate(payload.prompt)
        return {
            "success": True,
            "response": result
        }
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal engine error"
        )


# =========================
# API Tirages (Cloud SQL)
# =========================

@app.get("/api/tirages/count")
async def api_tirages_count():
    """
    Retourne le nombre total de tirages en base.

    Returns:
        JSON {success: bool, data: {total: int}, error: str|null}
    """
    try:
        total = db_cloudsql.get_tirages_count()
        return {
            "success": True,
            "data": {"total": total},
            "error": None
        }
    except Exception as e:
        logger.error(f"Erreur /api/tirages/count: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }


@app.get("/api/tirages/latest")
async def api_tirages_latest():
    """
    Retourne le tirage le plus recent.

    Returns:
        JSON {success: bool, data: {...tirage}, error: str|null}
    """
    try:
        tirage = db_cloudsql.get_latest_tirage()
        if tirage:
            return {
                "success": True,
                "data": tirage,
                "error": None
            }
        else:
            return {
                "success": False,
                "data": None,
                "error": "Aucun tirage trouve"
            }
    except Exception as e:
        logger.error(f"Erreur /api/tirages/latest: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }


@app.get("/api/tirages/list")
async def api_tirages_list(
    limit: int = Query(default=10, ge=1, le=100, description="Nombre de tirages"),
    offset: int = Query(default=0, ge=0, description="Offset pour pagination")
):
    """
    Retourne une liste de tirages (du plus recent au plus ancien).

    Args:
        limit: Nombre max de tirages (1-100, defaut: 10)
        offset: Decalage pour pagination (defaut: 0)

    Returns:
        JSON {success: bool, data: {items: [...], count: int, limit: int}, error: str|null}
    """
    try:
        tirages = db_cloudsql.get_tirages_list(limit=limit, offset=offset)
        return {
            "success": True,
            "data": {
                "items": tirages,
                "count": len(tirages),
                "limit": limit,
                "offset": offset
            },
            "error": None
        }
    except Exception as e:
        logger.error(f"Erreur /api/tirages/list: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }


# =========================
# API Database Info
# =========================

@app.get("/database-info")
async def database_info():
    """
    Retourne les informations sur la base de donnees.
    Utilise par le frontend pour afficher le statut.
    """
    try:
        result = db_cloudsql.test_connection()

        if result['status'] == 'ok':
            return {
                "status": "success",
                "exists": True,
                "is_ready": result['total_tirages'] > 0,
                "total_rows": result['total_tirages'],
                "total_draws": result['total_tirages'],
                "date_min": result['date_min'],
                "date_max": result['date_max'],
                "first_draw": result['date_min'],
                "last_draw": result['date_max'],
                "file_size_mb": 0  # N/A pour Cloud SQL
            }
        else:
            return {
                "status": "error",
                "exists": False,
                "is_ready": False,
                "error": result.get('error', 'Connexion echouee')
            }
    except Exception as e:
        logger.error(f"Erreur /database-info: {e}")
        return {
            "status": "error",
            "exists": False,
            "is_ready": False,
            "error": str(e)
        }


@app.get("/stats")
async def stats():
    """
    Retourne les statistiques globales.
    """
    try:
        global_stats = get_global_stats()
        return {
            "success": True,
            "stats": global_stats
        }
    except Exception as e:
        logger.error(f"Erreur /stats: {e}")
        return {
            "success": False,
            "message": str(e)
        }


@app.get("/generate")
async def generate_endpoint(
    n: int = Query(default=3, ge=1, le=10, description="Nombre de grilles"),
    mode: str = Query(default="balanced", description="Mode: conservative, balanced, recent")
):
    """
    Genere N grilles optimisees.

    Args:
        n: Nombre de grilles (1-10, defaut: 3)
        mode: Mode de generation (conservative, balanced, recent)

    Returns:
        JSON {success: bool, grids: [...], metadata: {...}}
    """
    try:
        # Validation du mode
        valid_modes = ["conservative", "balanced", "recent"]
        if mode not in valid_modes:
            mode = "balanced"

        result = generate_grids(n=n, mode=mode)

        return {
            "success": True,
            "grids": result['grids'],
            "metadata": result['metadata']
        }
    except Exception as e:
        logger.error(f"Erreur /generate: {e}")
        return {
            "success": False,
            "message": str(e),
            "grids": [],
            "metadata": {}
        }


# =========================
# API Stats Completes
# =========================

@app.get("/api/stats")
async def api_stats():
    """
    Retourne les statistiques completes pour le simulateur et la page stats.
    Base sur les tirages reels de Cloud SQL.

    Returns:
        - total_tirages
        - periode (debut, fin)
        - frequences de chaque numero (1-49)
        - retards (tirages depuis derniere apparition)
        - top_chauds (5 numeros les plus frequents)
        - top_froids (5 numeros les moins frequents)
    """
    try:
        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        # Total tirages et periode
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                MIN(date_de_tirage) as date_min,
                MAX(date_de_tirage) as date_max
            FROM tirages
        """)
        info = cursor.fetchone()
        total_tirages = info['total']
        date_min = str(info['date_min']) if info['date_min'] else None
        date_max = str(info['date_max']) if info['date_max'] else None

        # Calculer frequences et retards pour chaque numero (1-49)
        frequences = {}
        retards = {}

        for num in range(1, 50):
            # Frequence
            cursor.execute("""
                SELECT COUNT(*) as freq
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            freq_result = cursor.fetchone()
            frequences[str(num)] = freq_result['freq'] if freq_result else 0

            # Retard (nombre de tirages depuis derniere apparition)
            cursor.execute("""
                SELECT MAX(date_de_tirage) as last_date
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            last_result = cursor.fetchone()

            if last_result and last_result['last_date']:
                cursor.execute("""
                    SELECT COUNT(*) as gap
                    FROM tirages
                    WHERE date_de_tirage > %s
                """, (last_result['last_date'],))
                gap_result = cursor.fetchone()
                retards[str(num)] = gap_result['gap'] if gap_result else 0
            else:
                retards[str(num)] = total_tirages

        conn.close()

        # Trier pour top chauds et froids
        sorted_by_freq = sorted(
            [(int(k), v) for k, v in frequences.items()],
            key=lambda x: x[1],
            reverse=True
        )

        top_chauds = [{"numero": n, "freq": f} for n, f in sorted_by_freq[:5]]
        top_froids = [{"numero": n, "freq": f} for n, f in sorted_by_freq[-5:]]

        return {
            "success": True,
            "data": {
                "total_tirages": total_tirages,
                "periode": {
                    "debut": date_min,
                    "fin": date_max
                },
                "frequences": frequences,
                "retards": retards,
                "top_chauds": top_chauds,
                "top_froids": top_froids
            },
            "error": None
        }

    except Exception as e:
        logger.error(f"Erreur /api/stats: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }


@app.get("/api/numbers-heat")
async def api_numbers_heat():
    """
    Retourne la classification chaud/neutre/froid pour chaque numero (1-49).
    Utilise par le simulateur pour colorer les boutons.
    """
    try:
        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        # Total tirages
        cursor.execute("SELECT COUNT(*) as total FROM tirages")
        total = cursor.fetchone()['total']

        # Calculer frequences
        numbers_data = {}
        frequencies = []

        for num in range(1, 50):
            cursor.execute("""
                SELECT COUNT(*) as freq
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            freq = cursor.fetchone()['freq']

            # Derniere apparition
            cursor.execute("""
                SELECT MAX(date_de_tirage) as last_date
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            last = cursor.fetchone()
            last_date = str(last['last_date']) if last and last['last_date'] else None

            numbers_data[num] = {
                "frequency": freq,
                "last_draw": last_date
            }
            frequencies.append(freq)

        conn.close()

        # Calculer seuils (top 33% = chaud, bottom 33% = froid)
        frequencies.sort(reverse=True)
        seuil_chaud = frequencies[len(frequencies) // 3]
        seuil_froid = frequencies[2 * len(frequencies) // 3]

        # Classifier chaque numero
        for num in range(1, 50):
            freq = numbers_data[num]["frequency"]
            if freq >= seuil_chaud:
                numbers_data[num]["category"] = "hot"
            elif freq <= seuil_froid:
                numbers_data[num]["category"] = "cold"
            else:
                numbers_data[num]["category"] = "neutral"

        return {
            "success": True,
            "numbers": numbers_data,
            "total_tirages": total,
            "seuils": {
                "chaud": seuil_chaud,
                "froid": seuil_froid
            }
        }

    except Exception as e:
        logger.error(f"Erreur /api/numbers-heat: {e}")
        return {
            "success": False,
            "numbers": {},
            "error": str(e)
        }


@app.post("/api/analyze-custom-grid")
async def api_analyze_custom_grid(
    nums: list = Query(..., description="5 numeros principaux"),
    chance: int = Query(..., ge=1, le=10, description="Numero chance")
):
    """
    Analyse une grille personnalisee composee par l'utilisateur.
    Retourne un score, des badges et des suggestions.
    """
    try:
        # Validation
        if len(nums) != 5:
            return {"success": False, "error": "5 numeros requis"}

        nums = [int(n) for n in nums]
        if not all(1 <= n <= 49 for n in nums):
            return {"success": False, "error": "Numeros doivent etre entre 1 et 49"}

        if len(set(nums)) != 5:
            return {"success": False, "error": "Numeros doivent etre uniques"}

        nums = sorted(nums)

        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        # Recuperer les frequences
        cursor.execute("SELECT COUNT(*) as total FROM tirages")
        total_tirages = cursor.fetchone()['total']

        frequencies = []
        for num in nums:
            cursor.execute("""
                SELECT COUNT(*) as freq
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            freq = cursor.fetchone()['freq']
            frequencies.append(freq)

        conn.close()

        # Calcul des metriques
        nb_pairs = sum(1 for n in nums if n % 2 == 0)
        nb_impairs = 5 - nb_pairs
        nb_bas = sum(1 for n in nums if n <= 24)
        nb_hauts = 5 - nb_bas
        somme = sum(nums)
        dispersion = max(nums) - min(nums)

        # Suites consecutives
        nums_sorted = sorted(nums)
        suites = sum(1 for i in range(4) if nums_sorted[i+1] - nums_sorted[i] == 1)

        # Score de conformite
        score_conformite = 100
        if nb_pairs < 1 or nb_pairs > 4:
            score_conformite -= 15
        if nb_bas < 1 or nb_bas > 4:
            score_conformite -= 10
        if somme < 70 or somme > 150:
            score_conformite -= 20
        if dispersion < 15:
            score_conformite -= 25
        if suites > 2:
            score_conformite -= 15

        # Score frequence (moyenne des frequences normalisee)
        freq_moyenne = sum(frequencies) / 5
        freq_max_theorique = total_tirages * 5 / 49  # Frequence attendue uniforme
        score_freq = min(100, (freq_moyenne / freq_max_theorique) * 100)

        # Score final
        score = int(0.6 * score_conformite + 0.4 * score_freq)
        score = max(0, min(100, score))

        # Note etoiles
        if score >= 80:
            note_etoiles = 5
        elif score >= 65:
            note_etoiles = 4
        elif score >= 50:
            note_etoiles = 3
        elif score >= 35:
            note_etoiles = 2
        else:
            note_etoiles = 1

        # Badges
        badges = []
        if freq_moyenne > freq_max_theorique * 1.1:
            badges.append("Numeros chauds")
        elif freq_moyenne < freq_max_theorique * 0.9:
            badges.append("Mix de retards")
        else:
            badges.append("Equilibre")

        if dispersion > 35:
            badges.append("Large spectre")
        if nb_pairs == 2 or nb_pairs == 3:
            badges.append("Pair/Impair OK")

        badges.append("Analyse personnalisee")

        # Suggestions
        suggestions = []
        if score >= 70:
            suggestions.append("Excellent equilibre dans votre selection")
        if nb_pairs == 0 or nb_pairs == 5:
            suggestions.append("Equilibrer le ratio pair/impair (2-3 pairs ideal)")
        if nb_bas == 0 or nb_bas == 5:
            suggestions.append("Mixer numeros bas (1-24) et hauts (25-49)")
        if somme < 70:
            suggestions.append("Somme trop basse, ajouter des numeros plus eleves")
        elif somme > 150:
            suggestions.append("Somme trop elevee, ajouter des numeros plus bas")
        if dispersion < 15:
            suggestions.append("Numeros trop groupes, elargir la dispersion")
        if suites > 2:
            suggestions.append("Trop de numeros consecutifs")
        if not suggestions:
            suggestions.append("Grille bien equilibree")

        # Comparaison
        if score >= 80:
            comparaison = f"Meilleure que 85% des grilles aleatoires"
        elif score >= 60:
            comparaison = f"Meilleure que 60% des grilles aleatoires"
        elif score >= 40:
            comparaison = f"Dans la moyenne des grilles"
        else:
            comparaison = f"En dessous de la moyenne"

        return {
            "success": True,
            "nums": nums,
            "chance": chance,
            "score": score,
            "note_etoiles": note_etoiles,
            "comparaison": comparaison,
            "badges": badges,
            "details": {
                "pairs_impairs": f"{nb_pairs}/{nb_impairs}",
                "bas_haut": f"{nb_bas}/{nb_hauts}",
                "somme": str(somme),
                "dispersion": str(dispersion),
                "suites_consecutives": str(suites),
                "score_conformite": f"{score_conformite}%"
            },
            "suggestions": suggestions
        }

    except Exception as e:
        logger.error(f"Erreur /api/analyze-custom-grid: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# =========================
# API Stats pour page Statistiques
# =========================

@app.get("/draw/{date}")
async def get_draw_by_date(date: str):
    """
    Recherche un tirage par date (format YYYY-MM-DD).
    """
    try:
        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT date_de_tirage, boule_1, boule_2, boule_3, boule_4, boule_5, numero_chance
            FROM tirages
            WHERE date_de_tirage = %s
        """, (date,))

        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                "success": True,
                "found": True,
                "draw": {
                    "date": str(result['date_de_tirage']),
                    "n1": result['boule_1'],
                    "n2": result['boule_2'],
                    "n3": result['boule_3'],
                    "n4": result['boule_4'],
                    "n5": result['boule_5'],
                    "chance": result['numero_chance']
                }
            }
        else:
            return {
                "success": True,
                "found": False,
                "message": f"Aucun tirage pour la date {date}"
            }

    except Exception as e:
        logger.error(f"Erreur /draw/{date}: {e}")
        return {
            "success": False,
            "found": False,
            "message": str(e)
        }


@app.get("/api/stats/number/{number}")
async def api_stats_number(number: int):
    """
    Analyse complete d'un numero specifique (1-49).
    """
    try:
        if not 1 <= number <= 49:
            return {"success": False, "message": "Numero doit etre entre 1 et 49"}

        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        # Toutes les apparitions
        cursor.execute("""
            SELECT date_de_tirage
            FROM tirages
            WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
               OR boule_4 = %s OR boule_5 = %s
            ORDER BY date_de_tirage ASC
        """, (number, number, number, number, number))

        results = cursor.fetchall()
        appearance_dates = [str(r['date_de_tirage']) for r in results]

        total_appearances = len(appearance_dates)
        first_appearance = appearance_dates[0] if appearance_dates else None
        last_appearance = appearance_dates[-1] if appearance_dates else None

        # Ecart actuel
        current_gap = 0
        if last_appearance:
            cursor.execute("""
                SELECT COUNT(*) as gap
                FROM tirages
                WHERE date_de_tirage > %s
            """, (last_appearance,))
            gap_result = cursor.fetchone()
            current_gap = gap_result['gap'] if gap_result else 0

        conn.close()

        return {
            "success": True,
            "number": number,
            "total_appearances": total_appearances,
            "first_appearance": first_appearance,
            "last_appearance": last_appearance,
            "current_gap": current_gap,
            "appearance_dates": appearance_dates
        }

    except Exception as e:
        logger.error(f"Erreur /api/stats/number/{number}: {e}")
        return {
            "success": False,
            "message": str(e)
        }


@app.get("/api/stats/top-flop")
async def api_stats_top_flop():
    """
    Retourne le classement des numeros par frequence (Top et Flop).
    """
    try:
        conn = db_cloudsql.get_connection()
        cursor = conn.cursor()

        # Calculer frequences
        numbers_freq = []

        for num in range(1, 50):
            cursor.execute("""
                SELECT COUNT(*) as freq
                FROM tirages
                WHERE boule_1 = %s OR boule_2 = %s OR boule_3 = %s
                   OR boule_4 = %s OR boule_5 = %s
            """, (num, num, num, num, num))
            freq = cursor.fetchone()['freq']
            numbers_freq.append({"number": num, "count": freq})

        conn.close()

        # Trier
        top = sorted(numbers_freq, key=lambda x: (-x['count'], x['number']))
        flop = sorted(numbers_freq, key=lambda x: (x['count'], x['number']))

        return {
            "success": True,
            "top": top,
            "flop": flop
        }

    except Exception as e:
        logger.error(f"Erreur /api/stats/top-flop: {e}")
        return {
            "success": False,
            "message": str(e)
        }


# =========================
# API Tracking (Analytics)
# =========================

@app.post("/api/track-grid")
async def api_track_grid(payload: TrackGridPayload):
    """
    Enregistre le tracking d'une grille generee.
    Pour l'instant, log uniquement. Extensible vers Cloud SQL ou BigQuery.

    Args:
        payload: Donnees de tracking (grid_id, session_id, etc.)

    Returns:
        JSON {success: bool, message: str}
    """
    try:
        grid_id = payload.grid_id or "unknown"
        session_id = payload.session_id or "anonymous"
        target_date = payload.target_date or "unknown"
        nums = payload.grid_data.nums if payload.grid_data else []
        chance = payload.grid_data.chance if payload.grid_data else 0

        logger.info(
            f"[TRACK] Grid generated - "
            f"grid_id={grid_id}, "
            f"session={session_id[:8]}..., "
            f"target={target_date}, "
            f"nums={nums}, "
            f"chance={chance}"
        )

        return {
            "success": True,
            "message": "Grid tracked",
            "grid_id": grid_id
        }

    except Exception as e:
        logger.error(f"Erreur /api/track-grid: {e}")
        return {
            "success": False,
            "message": str(e)
        }


@app.post("/api/track-ad-impression")
async def api_track_ad_impression(payload: TrackAdImpressionPayload):
    """
    Enregistre une impression publicitaire.

    Args:
        payload: Donnees d'impression (ad_id, session_id, timestamp)

    Returns:
        JSON {success: bool, message: str}
    """
    try:
        ad_id = payload.ad_id or "unknown"
        session_id = payload.session_id or "anonymous"

        logger.info(
            f"[TRACK] Ad impression - "
            f"ad_id={ad_id}, "
            f"session={session_id[:8]}..."
        )

        return {
            "success": True,
            "message": "Impression tracked",
            "ad_id": ad_id
        }

    except Exception as e:
        logger.error(f"Erreur /api/track-ad-impression: {e}")
        return {
            "success": False,
            "message": str(e)
        }


@app.post("/api/track-ad-click")
async def api_track_ad_click(payload: TrackAdClickPayload):
    """
    Enregistre un clic publicitaire (CPA tracking).

    Args:
        payload: Donnees de clic (ad_id, partner_id, session_id)

    Returns:
        JSON {success: bool, message: str}
    """
    try:
        ad_id = payload.ad_id or "unknown"
        partner_id = payload.partner_id or "unknown"
        session_id = payload.session_id or "anonymous"

        logger.info(
            f"[TRACK] Ad click - "
            f"ad_id={ad_id}, "
            f"partner={partner_id}, "
            f"session={session_id[:8]}..."
        )

        return {
            "success": True,
            "message": "Click tracked",
            "ad_id": ad_id,
            "partner_id": partner_id
        }

    except Exception as e:
        logger.error(f"Erreur /api/track-ad-click: {e}")
        return {
            "success": False,
            "message": str(e)
        }
