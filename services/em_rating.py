"""
Note JSON-LD (AggregateRating) de l'accueil EuroMillions — Lot 1.6.067 (décision Jyppy 08/11/2026).

Périmètre EM complet : toutes les sources de vote EuroMillions réellement présentes en base, au lieu du
seul popup EM. L'accueil Loto (/accueil) reste sur la vue ratings_global (entité « LotoIA », toutes sources).

DETTE (hors lot) : les chatbots EM ES/PT/DE/NL émettent chatbot_em_es / chatbot_em_pt / chatbot_em_de /
chatbot_em_nl (ui/static/hybride-chatbot-em-{es,pt,de,nl}.js), mais ces votes sont refusés par l'API
(schemas.py:77, motif RatingSubmit.source) et par la contrainte CHECK chk_source_enum de la migration 014 :
ils n'arrivent jamais en base. Les ajouter ici le jour où schemas.py et la contrainte CHECK les accepteront.
"""
import db_cloudsql

EM_RATING_SOURCES = ("popup_em", "chatbot_em", "chatbot_em_en")

_EM_RATING_SQL = (
    "SELECT COUNT(*) AS review_count, ROUND(AVG(rating), 1) AS avg_rating "
    "FROM ratings WHERE source IN (%s, %s, %s)"
)


async def fetch_em_rating(db=None) -> tuple[float, int]:
    """(note moyenne arrondie à 0,1, nombre de votes) ; (0, 0) si aucun vote ou erreur base.

    `db` : module db_cloudsql de la route appelante (les tests patchent `routes.<module>.db_cloudsql`) ;
    None → module db_cloudsql importé ici.
    """
    db = db or db_cloudsql
    try:
        row = await db.async_fetchone(_EM_RATING_SQL, EM_RATING_SOURCES)
        if row and row.get("review_count"):
            return round(float(row["avg_rating"]), 1), int(row["review_count"])
    except Exception:
        pass
    return 0, 0
