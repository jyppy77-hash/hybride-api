from fastapi import APIRouter
import logging

from schemas import TrackGridPayload, TrackAdImpressionPayload, TrackAdClickPayload

logger = logging.getLogger(__name__)

router = APIRouter()


# =========================
# API Tracking (Analytics)
# =========================

@router.post("/api/track-grid")
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
            "message": "Erreur interne du serveur"
        }


@router.post("/api/track-ad-impression")
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
            "message": "Erreur interne du serveur"
        }


@router.post("/api/track-ad-click")
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
            "message": "Erreur interne du serveur"
        }
