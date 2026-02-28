"""
API Ratings — Système de notation utilisateur LotoIA
=====================================================
POST /api/rating              → soumettre une note
GET  /api/ratings/aggregate   → note moyenne globale (schema JSON-LD)
GET  /api/ratings/aggregate/{source} → note moyenne par source
"""

import hashlib
import logging

from fastapi import APIRouter, Request, HTTPException

import db_cloudsql
from rate_limit import limiter
from schemas import RatingSubmit, RatingResponse, RatingAggregate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ratings"])


@router.post("/rating", response_model=RatingResponse)
@limiter.limit("10/minute")
async def submit_rating(data: RatingSubmit, request: Request):
    """Soumet une note utilisateur (1 vote par session+source, upsert)."""
    try:
        # Hash IP pour anti-spam RGPD-friendly
        client_ip = request.client.host if request.client else "unknown"
        ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]

        # User-Agent pour analytics
        user_agent = (request.headers.get("user-agent") or "")[:500]

        # UPSERT : INSERT + ON DUPLICATE KEY UPDATE (MySQL)
        sql = """
            INSERT INTO ratings (source, rating, comment, session_id, page, user_agent, ip_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                rating     = VALUES(rating),
                comment    = VALUES(comment),
                created_at = CURRENT_TIMESTAMP
        """
        params = (
            data.source,
            data.rating,
            data.comment,
            data.session_id,
            data.page,
            user_agent,
            ip_hash,
        )

        await db_cloudsql.async_query(sql, params)

        logger.info(
            f"[RATING] {data.source} -> {data.rating} stars "
            f"(session: {data.session_id[:8]}...)"
        )

        return RatingResponse(success=True, message="Merci pour votre note !")

    except Exception as e:
        logger.error(f"[RATING ERROR] {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de l'enregistrement")


@router.get("/ratings/aggregate", response_model=RatingAggregate)
@limiter.limit("60/minute")
async def get_aggregate(request: Request):
    """Retourne la note moyenne globale (pour le schema JSON-LD)."""
    try:
        result = await db_cloudsql.async_fetchone(
            "SELECT review_count, avg_rating FROM ratings_global"
        )

        if result and result.get("review_count"):
            return RatingAggregate(
                avg_rating=float(result["avg_rating"]),
                review_count=int(result["review_count"]),
            )

        return RatingAggregate(avg_rating=0, review_count=0)

    except Exception as e:
        logger.error(f"[RATING AGGREGATE ERROR] {e}")
        return RatingAggregate(avg_rating=0, review_count=0)


@router.get("/ratings/aggregate/{source}", response_model=RatingAggregate)
@limiter.limit("60/minute")
async def get_aggregate_by_source(source: str, request: Request):
    """Retourne la note moyenne par source (chatbot_loto, chatbot_em, popup_accueil)."""
    try:
        result = await db_cloudsql.async_fetchone(
            "SELECT review_count, avg_rating FROM ratings_aggregate WHERE source = %s",
            (source,),
        )

        if result and result.get("review_count"):
            return RatingAggregate(
                avg_rating=float(result["avg_rating"]),
                review_count=int(result["review_count"]),
                source=source,
            )

        return RatingAggregate(avg_rating=0, review_count=0, source=source)

    except Exception as e:
        logger.error(f"[RATING AGGREGATE ERROR] {e}")
        return RatingAggregate(avg_rating=0, review_count=0, source=source)
