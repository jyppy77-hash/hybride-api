from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import logging

from schemas import MetaPdfPayload
from services.pdf_generator import generate_meta_pdf

logger = logging.getLogger(__name__)

router = APIRouter()


# =========================
# META PDF (logique dans services/pdf_generator.py)
# =========================

@router.post("/api/meta-pdf")
async def api_meta_pdf(payload: MetaPdfPayload):
    """Genere le PDF officiel META75 via ReportLab."""
    try:
        buf = generate_meta_pdf(
            analysis=payload.analysis,
            window=payload.window,
            engine=payload.engine,
            graph=payload.graph,
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
        raise HTTPException(status_code=500, detail=f"Erreur generation PDF: {e}")
