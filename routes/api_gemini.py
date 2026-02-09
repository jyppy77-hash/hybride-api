from fastapi import APIRouter, Request

from schemas import MetaAnalyseTextePayload
from services.gemini import enrich_analysis
from rate_limit import limiter

router = APIRouter()


# =========================
# META ANALYSE Texte Gemini (logique dans services/gemini.py)
# =========================

@router.post("/api/meta-analyse-texte")
@limiter.limit("10/minute")
async def api_meta_analyse_texte(request: Request, payload: MetaAnalyseTextePayload):
    """Enrichit le texte d'analyse local via Gemini."""
    return await enrich_analysis(
        analysis_local=payload.analysis_local,
        window=payload.window or "GLOBAL",
        http_client=request.app.state.httpx_client
    )
