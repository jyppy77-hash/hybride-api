"""
Backward compat — routes EuroMillions analyse.
Thin wrappers delegating to unified routes.
Keeps /meta-analyse-texte and /meta-pdf (EM-only, no Loto equivalent).
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from typing import Optional
import logging

from em_schemas import EMMetaAnalyseTextePayload, EMMetaPdfPayload
from rate_limit import limiter
from config.games import ValidGame
from routes.api_analyse_unified import (
    unified_generate,
    unified_meta_analyse_local,
    unified_analyze_custom_grid,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/euromillions", tags=["EuroMillions - Analyse"])

_EM = ValidGame.euromillions


# ── Wrappers ──

@router.get("/generate")
@limiter.limit("60/minute")
async def em_generate(
    request: Request,
    n: int = Query(default=3, ge=1, le=10),
    mode: str = Query(default="balanced"),
    lang: str = Query(default="fr", pattern=r"^(fr|en|pt|es|de|nl)$"),
):
    return await unified_generate(request=request, game=_EM, n=n, mode=mode, lang=lang)


@router.get("/meta-analyse-local")
@limiter.limit("60/minute")
async def em_meta_analyse_local(
    request: Request,
    window: Optional[str] = Query(default="GLOBAL"),
    years: Optional[str] = Query(default=None),
):
    return await unified_meta_analyse_local(request=request, game=_EM, window=window, years=years)


@router.post("/analyze-custom-grid")
@limiter.limit("60/minute")
async def em_analyze_custom_grid(
    request: Request,
    nums: list = Query(..., description="5 numeros principaux (1-50)"),
    etoile1: int = Query(..., ge=1, le=12, description="Etoile 1"),
    etoile2: int = Query(..., ge=1, le=12, description="Etoile 2"),
    lang: str = Query(default="fr", pattern=r"^(fr|en|pt|es|de|nl)$"),
):
    return await unified_analyze_custom_grid(
        request=request, game=_EM, nums=nums, etoile1=etoile1, etoile2=etoile2, lang=lang,
    )


# ── EM-only routes (no Loto equivalent) ──

@router.post("/meta-analyse-texte")
@limiter.limit("10/minute")
async def em_meta_analyse_texte(request: Request, payload: EMMetaAnalyseTextePayload):
    """Enrichit le texte d'analyse local EuroMillions via Gemini."""
    from services.em_gemini import enrich_analysis_em
    return await enrich_analysis_em(
        analysis_local=payload.analysis_local,
        window=payload.window or "GLOBAL",
        http_client=request.app.state.httpx_client,
        lang=payload.lang,
    )


async def _fetch_last_draw_date_em() -> str | None:
    """Fetch last EM draw date from DB for PDF timestamp (F07)."""
    try:
        from engine.db import get_connection
        async with get_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT date_de_tirage FROM tirages_euromillions ORDER BY date_de_tirage DESC LIMIT 1"
            )
            row = await cursor.fetchone()
        return str(row["date_de_tirage"]) if row else None
    except Exception as e:
        logger.warning(f"[META-PDF-EM] last_draw_date fetch failed: {e}")
        return None


@router.post("/meta-pdf")
@limiter.limit("10/minute")
async def em_meta_pdf(request: Request, payload: EMMetaPdfPayload):
    """Genere le PDF officiel META75 EuroMillions via ReportLab."""
    from services.em_pdf_generator import generate_em_meta_pdf

    try:
        logger.info(f"[META-PDF-EM ROUTE] graph_data_boules: {type(payload.graph_data_boules).__name__}, "
                     f"graph_data_etoiles: {type(payload.graph_data_etoiles).__name__}")

        # Fetch last draw date from DB (F07 timestamp)
        last_draw_date = await _fetch_last_draw_date_em()

        buf = await asyncio.to_thread(
            generate_em_meta_pdf,
            analysis=payload.analysis,
            window=payload.window,
            engine=payload.engine,
            graph=payload.graph,
            graph_data_boules=payload.graph_data_boules,
            graph_data_etoiles=payload.graph_data_etoiles,
            sponsor=payload.sponsor,
            lang=payload.lang,
            all_freq_boules=payload.all_freq_boules,
            all_freq_secondary=payload.all_freq_secondary,
            last_draw_date=last_draw_date,
        )
        lang = payload.lang or "fr"
        fname = f"rapport-meta-euromillions-{lang}.pdf"
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
        logger.error(f"[META-PDF-EM] Erreur generation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur generation PDF EM")
