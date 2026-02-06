from fastapi import APIRouter

from schemas import MetaAnalyseTextePayload
from services.gemini import enrich_analysis

router = APIRouter()


# =========================
# META ANALYSE Texte Gemini (logique dans services/gemini.py)
# =========================

@router.post("/api/meta-analyse-texte")
async def api_meta_analyse_texte(payload: MetaAnalyseTextePayload):
    """Enrichit le texte d'analyse local via Gemini."""
    return await enrich_analysis(
        analysis_local=payload.analysis_local,
        window=payload.window or "GLOBAL"
    )
