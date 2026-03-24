import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
import logging

from schemas import MetaPdfPayload
from services.pdf_generator import generate_meta_pdf
from rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


async def _fetch_last_draw_date_loto() -> str | None:
    """Fetch last draw date from DB for PDF timestamp (F07)."""
    try:
        from engine.db import get_connection
        async with get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT date_de_tirage FROM tirages ORDER BY date_de_tirage DESC LIMIT 1"
            )
            row = await cursor.fetchone()
        return str(row["date_de_tirage"]) if row else None
    except Exception as e:
        logger.warning(f"[META-PDF] last_draw_date fetch failed: {e}")
        return None


# =========================
# META PDF (logique dans services/pdf_generator.py)
# =========================

@router.post("/api/meta-pdf")
@limiter.limit("10/minute")
async def api_meta_pdf(request: Request, payload: MetaPdfPayload):
    """Genere le PDF officiel META75 via ReportLab."""
    try:
        # --- TRACE graph_data recu ---
        if payload.graph_data and isinstance(payload.graph_data, dict):
            logger.info(f"[META-PDF ROUTE] graph_data recu — keys: {list(payload.graph_data.keys())}, "
                        f"labels_len: {len(payload.graph_data.get('labels', []))}, "
                        f"values_len: {len(payload.graph_data.get('values', []))}")
        else:
            logger.info(f"[META-PDF ROUTE] graph_data ABSENT ou invalide — raw: {type(payload.graph_data)}")

        # Fetch last draw date from DB (F07 timestamp)
        last_draw_date = await _fetch_last_draw_date_loto()

        buf = await asyncio.to_thread(
            generate_meta_pdf,
            analysis=payload.analysis,
            window=payload.window,
            engine=payload.engine,
            graph=payload.graph,
            graph_data=payload.graph_data,
            chance_data=payload.chance_data,
            sponsor=payload.sponsor,
            lang=payload.lang,
            all_freq_boules=payload.all_freq_boules,
            all_freq_secondary=payload.all_freq_secondary,
            last_draw_date=last_draw_date,
        )
        lang = payload.lang or "fr"
        fname = f"rapport-meta-lotoia-{lang}.pdf"
        pdf_bytes = buf.getvalue()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{fname}"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab non installe")
    except Exception as e:
        logger.error(f"[META-PDF] Erreur generation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur generation PDF")
