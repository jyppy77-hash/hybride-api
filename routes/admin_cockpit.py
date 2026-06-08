"""
Admin cockpit — Cockpit Métrique V_X.F (read-only, stateless).
==============================================================
Sub-router admin /admin/cockpit. Affiche les 4 étages de la métrique V_X.F
d'un run OOS uploadé en JSON. Ne lance rien, ne stocke rien, ne recalcule rien.

Flux : le front poste le fichier JSON (multipart, champ "file") → le serveur
parse en RAM (json.loads) → normalize_run() → renvoie le view-model JSON.
AUCUNE écriture disque/DB, AUCUN état. Owner-only (OWNER_IP) + cookie session,
hérité du pattern _require_auth* (routes/admin_helpers.py).

MUR ÉTANCHE : ce module n'importe JAMAIS tools.*. La seule frontière est le
JSON, parsé par la stdlib et normalisé par services.cockpit_parser (lui aussi
sans tools.*). Voir tests/test_cockpit_wall.py.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from config.templates import env
from routes.admin_helpers import (
    require_auth as _require_auth,
    require_auth_json as _require_auth_json,
)
from services.cockpit_parser import normalize_run
from services.cockpit_pdf_generator import generate_cockpit_pdf

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

# Cap large (un run fait quelques centaines de Ko ; 25 Mo = marge confortable).
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.get("/admin/cockpit", response_class=HTMLResponse, include_in_schema=False)
async def cockpit_page(request: Request):
    """Page cockpit (zone drag-drop). Owner-only, noindex (hérité de _base.html)."""
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/cockpit.html")
    resp = HTMLResponse(tpl.render(active="cockpit"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@router.post("/admin/cockpit/analyze", include_in_schema=False)
async def cockpit_analyze(request: Request):
    """Reçoit un JSON de run uploadé, le normalise en RAM, renvoie le view-model.

    Rejets gracieux (jamais de 500) : non authentifié, fichier absent/vide,
    trop gros (> 25 Mo), JSON invalide. Aucune écriture, tout en mémoire.
    """
    err = _require_auth_json(request)
    if err:
        return err

    # Garde précoce sur Content-Length (peut être absent ou usurpé → on revérifie après lecture).
    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > _MAX_UPLOAD_BYTES:
        return JSONResponse(
            {"ok": False, "error": "Fichier trop volumineux (max 25 Mo)"},
            status_code=413,
        )

    try:
        form = await request.form()
    except Exception as e:
        logger.warning("[COCKPIT] form parse error: %s", e)
        return JSONResponse({"ok": False, "error": "Requête invalide"}, status_code=400)

    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        return JSONResponse({"ok": False, "error": "Aucun fichier fourni"}, status_code=400)

    raw_bytes = await upload.read()
    if not raw_bytes:
        return JSONResponse({"ok": False, "error": "Fichier vide"}, status_code=400)
    if len(raw_bytes) > _MAX_UPLOAD_BYTES:
        return JSONResponse(
            {"ok": False, "error": "Fichier trop volumineux (max 25 Mo)"},
            status_code=413,
        )

    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.info("[COCKPIT] JSON invalide: %s", e)
        return JSONResponse({"ok": False, "error": "JSON invalide"}, status_code=400)

    if not isinstance(parsed, dict):
        return JSONResponse(
            {"ok": False, "error": "JSON invalide (objet attendu)"}, status_code=400
        )

    view_model = normalize_run(parsed)
    return JSONResponse({"ok": True, "data": view_model})


@router.post("/admin/cockpit/pdf", include_in_schema=False)
async def cockpit_pdf(request: Request):
    """Re-POST du JSON brut → normalize_run → PDF diffusion-grade (StreamingResponse).

    Gardes identiques à /analyze (volontairement dupliquées : /analyze est en
    prod, testé, byte-identique — pas de refactor DRY tant qu'un 3ᵉ endpoint
    upload n'existe pas). Owner-only, stateless. Run dégradé (error) → 400, on
    n'émet jamais de PDF vide.
    """
    err = _require_auth_json(request)
    if err:
        return err

    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > _MAX_UPLOAD_BYTES:
        return JSONResponse(
            {"ok": False, "error": "Fichier trop volumineux (max 25 Mo)"},
            status_code=413,
        )

    try:
        form = await request.form()
    except Exception as e:
        logger.warning("[COCKPIT] form parse error: %s", e)
        return JSONResponse({"ok": False, "error": "Requête invalide"}, status_code=400)

    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        return JSONResponse({"ok": False, "error": "Aucun fichier fourni"}, status_code=400)

    raw_bytes = await upload.read()
    if not raw_bytes:
        return JSONResponse({"ok": False, "error": "Fichier vide"}, status_code=400)
    if len(raw_bytes) > _MAX_UPLOAD_BYTES:
        return JSONResponse(
            {"ok": False, "error": "Fichier trop volumineux (max 25 Mo)"},
            status_code=413,
        )

    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.info("[COCKPIT] JSON invalide: %s", e)
        return JSONResponse({"ok": False, "error": "JSON invalide"}, status_code=400)

    if not isinstance(parsed, dict):
        return JSONResponse(
            {"ok": False, "error": "JSON invalide (objet attendu)"}, status_code=400
        )

    view_model = normalize_run(parsed)
    if view_model.get("error"):
        return JSONResponse(
            {"ok": False, "error": "Run non exploitable (schéma non reconnu)"},
            status_code=400,
        )

    buf = await asyncio.to_thread(generate_cockpit_pdf, view_model)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="cockpit-run.pdf"'},
    )
