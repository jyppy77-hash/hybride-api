from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import logging

from schemas import MetaPdfPayload
from services.pdf_generator import generate_meta_pdf
from rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


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

        buf = generate_meta_pdf(
            analysis=payload.analysis,
            window=payload.window,
            engine=payload.engine,
            graph=payload.graph,
            graph_data=payload.graph_data,
            sponsor=payload.sponsor
        )
        return StreamingResponse(
            buf,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline; filename=meta75_report.pdf"}
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab non installe")
    except Exception as e:
        logger.error(f"[META-PDF] Erreur generation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur generation PDF")
