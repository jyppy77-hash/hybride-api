"""
Admin sponsors — sponsors CRUD, factures, contrats, config entreprise, tarifs.
==============================================================================
Split from routes/admin.py (Phase 2 refacto V88).
"""

import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

import db_cloudsql
from config.templates import env
from routes.admin_helpers import (
    require_auth as _require_auth,
    require_auth_json as _require_auth_json,
    dec as _dec,
    next_invoice_number as _next_invoice_number,
    next_contrat_number as _next_contrat_number,
    validate_contrat_form as _validate_contrat_form,
    VALID_EVENTS as _VALID_EVENTS,
    VALID_STATUTS as _VALID_STATUTS,
    VALID_CONTRAT_STATUTS as _VALID_CONTRAT_STATUTS,
    VALID_TYPE_CONTRAT as _VALID_TYPE_CONTRAT,
    VALID_MODE_DEPASSEMENT as _VALID_MODE_DEPASSEMENT,
    VALID_TARIF_CODES as _VALID_TARIF_CODES,
    PALIERS_V9 as _PALIERS_V9,
    get_contract_impressions_consumed as _get_pool_consumed,
)

from rate_limit import limiter  # S15 V94

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


def _safe_int(value, default: int) -> int:
    """S13 V93: safe int conversion — fallback to default on invalid input."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value, default: float) -> float:
    """S14 V93: safe float conversion — fallback to default on invalid input."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


# ══════════════════════════════════════════════════════════════════════════════
# SPONSORS CRUD
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/sponsors", response_class=HTMLResponse, include_in_schema=False)
async def admin_sponsors_list(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    sponsors = []
    try:
        sponsors = await db_cloudsql.async_fetchall(
            "SELECT id, nom, contact_nom, contact_email, contact_tel, adresse, siret, notes, actif "
            "FROM fia_sponsors ORDER BY nom"
        )
    except Exception as e:
        logger.error("[ADMIN] sponsors list: %s", e)
    tpl = env.get_template("admin/sponsors.html")
    return HTMLResponse(tpl.render(active="sponsors", sponsors=sponsors))


@router.get("/admin/sponsors/new", response_class=HTMLResponse, include_in_schema=False)
async def admin_sponsor_new_form(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    tpl = env.get_template("admin/sponsor_form.html")
    return HTMLResponse(tpl.render(active="sponsors", sponsor=None, grille=None, error=None))


@router.post("/admin/sponsors/new", response_class=HTMLResponse, include_in_schema=False)
async def admin_sponsor_create(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    nom = (form.get("nom") or "").strip()
    if not nom:
        tpl = env.get_template("admin/sponsor_form.html")
        return HTMLResponse(tpl.render(active="sponsors", sponsor=None, grille=None, error="Le nom est obligatoire."), status_code=400)

    try:
        await db_cloudsql.async_query(
            "INSERT INTO fia_sponsors (nom, contact_nom, contact_email, contact_tel, adresse, siret, notes, actif) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (nom, form.get("contact_nom", ""), form.get("contact_email", ""),
             form.get("contact_tel", ""), form.get("adresse", ""),
             form.get("siret", ""), form.get("notes", ""), _safe_int(form.get("actif", 1), 1)),
        )
        row = await db_cloudsql.async_fetchone("SELECT LAST_INSERT_ID() AS id")
        sponsor_id = row["id"]
        logger.info("[ADMIN_AUDIT] action=sponsor_create sponsor_id=%s name=%s", sponsor_id, nom)

        # Save pricing grid
        events = form.getlist("tarif_event[]")
        prices = form.getlist("tarif_prix[]")
        descs = form.getlist("tarif_desc[]")
        for ev, pr, desc in zip(events, prices, descs):
            if ev in _VALID_EVENTS and pr:
                await db_cloudsql.async_query(
                    "INSERT INTO fia_grille_tarifaire (sponsor_id, event_type, prix_unitaire, description) "
                    "VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE prix_unitaire=%s, description=%s",
                    (sponsor_id, ev, float(pr), desc, float(pr), desc),
                )
    except Exception as e:
        logger.error("[ADMIN] sponsor create: %s", e)
        tpl = env.get_template("admin/sponsor_form.html")
        return HTMLResponse(tpl.render(active="sponsors", sponsor=None, grille=None, error=str(e)), status_code=500)

    return RedirectResponse(url="/admin/sponsors", status_code=302)


@router.get("/admin/sponsors/{sponsor_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def admin_sponsor_edit_form(request: Request, sponsor_id: int):
    redir = _require_auth(request)
    if redir:
        return redir
    sponsor = await db_cloudsql.async_fetchone("SELECT * FROM fia_sponsors WHERE id = %s", (sponsor_id,))
    if not sponsor:
        return RedirectResponse(url="/admin/sponsors", status_code=302)
    grille = await db_cloudsql.async_fetchall("SELECT * FROM fia_grille_tarifaire WHERE sponsor_id = %s", (sponsor_id,))
    tpl = env.get_template("admin/sponsor_form.html")
    return HTMLResponse(tpl.render(active="sponsors", sponsor=sponsor, grille=grille, error=None))


@router.post("/admin/sponsors/{sponsor_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def admin_sponsor_update(request: Request, sponsor_id: int):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    nom = (form.get("nom") or "").strip()
    if not nom:
        sponsor = await db_cloudsql.async_fetchone("SELECT * FROM fia_sponsors WHERE id = %s", (sponsor_id,))
        grille = await db_cloudsql.async_fetchall("SELECT * FROM fia_grille_tarifaire WHERE sponsor_id = %s", (sponsor_id,))
        tpl = env.get_template("admin/sponsor_form.html")
        return HTMLResponse(tpl.render(active="sponsors", sponsor=sponsor, grille=grille, error="Le nom est obligatoire."), status_code=400)

    try:
        await db_cloudsql.async_query(
            "UPDATE fia_sponsors SET nom=%s, contact_nom=%s, contact_email=%s, contact_tel=%s, "
            "adresse=%s, siret=%s, notes=%s, actif=%s WHERE id=%s",
            (nom, form.get("contact_nom", ""), form.get("contact_email", ""),
             form.get("contact_tel", ""), form.get("adresse", ""),
             form.get("siret", ""), form.get("notes", ""), _safe_int(form.get("actif", 1), 1), sponsor_id),
        )
        logger.info("[ADMIN_AUDIT] action=sponsor_update sponsor_id=%s name=%s", sponsor_id, nom)

        # Replace pricing grid (S03 V93: transactional DELETE+INSERT)
        events = form.getlist("tarif_event[]")
        prices = form.getlist("tarif_prix[]")
        descs = form.getlist("tarif_desc[]")
        async with db_cloudsql.get_connection() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                try:
                    await cur.execute("DELETE FROM fia_grille_tarifaire WHERE sponsor_id = %s", (sponsor_id,))
                    for ev, pr, desc in zip(events, prices, descs):
                        if ev in _VALID_EVENTS and pr:
                            await cur.execute(
                                "INSERT INTO fia_grille_tarifaire (sponsor_id, event_type, prix_unitaire, description) VALUES (%s, %s, %s, %s)",
                                (sponsor_id, ev, float(pr), desc),
                            )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
    except Exception as e:
        logger.error("[ADMIN] sponsor update: %s", e)

    return RedirectResponse(url="/admin/sponsors", status_code=302)


# ══════════════════════════════════════════════════════════════════════════════
# FACTURES CRUD
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/factures", response_class=HTMLResponse, include_in_schema=False)
async def admin_factures_list(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    factures = []
    try:
        factures = await db_cloudsql.async_fetchall(
            "SELECT f.*, s.nom AS sponsor_nom FROM fia_factures f "
            "LEFT JOIN fia_sponsors s ON f.sponsor_id = s.id "
            "ORDER BY f.date_emission DESC"
        )
    except Exception as e:
        logger.error("[ADMIN] factures list: %s", e)
    tpl = env.get_template("admin/factures.html")
    return HTMLResponse(tpl.render(active="factures", factures=factures))


@router.get("/admin/factures/new", response_class=HTMLResponse, include_in_schema=False)
async def admin_facture_new_form(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    sponsors = []
    try:
        sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom")
    except Exception as e:
        logger.error("[ADMIN] facture form sponsors: %s", e)
    tpl = env.get_template("admin/facture_form.html")
    return HTMLResponse(tpl.render(active="factures", sponsors=sponsors, error=None))


@router.post("/admin/factures/new", response_class=HTMLResponse, include_in_schema=False)
async def admin_facture_create(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    sponsor_id = form.get("sponsor_id")
    periode_debut = form.get("periode_debut", "")
    periode_fin = form.get("periode_fin", "")

    sponsors = []
    try:
        sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom")
    except Exception:
        pass

    if not sponsor_id or not periode_debut or not periode_fin:
        tpl = env.get_template("admin/facture_form.html")
        return HTMLResponse(tpl.render(active="factures", sponsors=sponsors, error="Tous les champs sont obligatoires."), status_code=400)

    try:
        sponsor_id = int(sponsor_id)
        pd = date.fromisoformat(periode_debut)
        pf = date.fromisoformat(periode_fin)
    except (ValueError, TypeError):
        tpl = env.get_template("admin/facture_form.html")
        return HTMLResponse(tpl.render(active="factures", sponsors=sponsors, error="Dates invalides."), status_code=400)

    try:
        # fia_grille_tarifaire: per-sponsor × event_type unit pricing (CPC/CPM).
        # Source of truth for invoice calculation.
        # See also: sponsor_tarifs (monthly packages, admin /tarifs interface).
        grille = await db_cloudsql.async_fetchall(
            "SELECT * FROM fia_grille_tarifaire WHERE sponsor_id = %s", (sponsor_id,))

        # Count events in period from sponsor_impressions (single GROUP BY — A07)
        event_types = [g["event_type"] for g in grille]
        counts_by_type = {}
        if event_types:
            placeholders = ",".join(["%s"] * len(event_types))
            count_rows = await db_cloudsql.async_fetchall(
                f"SELECT event_type, COUNT(*) AS cnt FROM sponsor_impressions "
                f"WHERE event_type IN ({placeholders}) "
                f"AND DATE(created_at) >= %s AND DATE(created_at) <= %s "
                f"GROUP BY event_type",
                (*event_types, pd.isoformat(), pf.isoformat()),
            )
            counts_by_type = {r["event_type"]: r["cnt"] for r in count_rows}

        lignes = []
        montant_ht = Decimal("0")
        for g in grille:
            qty = counts_by_type.get(g["event_type"], 0)
            prix = Decimal(str(g["prix_unitaire"]))
            total_ligne = prix * qty
            montant_ht += total_ligne
            desc = g["description"] or g["event_type"]
            lignes.append({"event_type": g["event_type"], "description": desc,
                           "quantite": qty, "prix_unitaire": float(prix), "total_ht": float(total_ligne)})

        # TVA
        config_row = await db_cloudsql.async_fetchone("SELECT taux_tva FROM fia_config_entreprise WHERE id = 1")
        taux_tva = Decimal(str(config_row["taux_tva"])) if config_row else Decimal("20")
        montant_tva = (montant_ht * taux_tva / Decimal("100")).quantize(Decimal("0.01"))
        montant_ttc = montant_ht + montant_tva

        # Invoice number — retry on duplicate (S15 unique constraint)
        date_echeance_str = form.get("date_echeance", "")
        date_ech = date.fromisoformat(date_echeance_str) if date_echeance_str else (date.today() + timedelta(days=30))

        for _attempt in range(3):
            cnt_row = await db_cloudsql.async_fetchone(
                "SELECT COUNT(*) AS cnt FROM fia_factures WHERE numero LIKE %s",
                (f"FIA-{date.today().strftime('%Y%m')}-%",))
            numero = _next_invoice_number(cnt_row["cnt"] if cnt_row else 0)
            try:
                await db_cloudsql.async_query(
                    "INSERT INTO fia_factures (numero, sponsor_id, date_emission, date_echeance, "
                    "periode_debut, periode_fin, montant_ht, montant_tva, montant_ttc, statut, lignes, notes) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (numero, sponsor_id, date.today().isoformat(), date_ech.isoformat(),
                     pd.isoformat(), pf.isoformat(),
                     float(montant_ht), float(montant_tva), float(montant_ttc),
                     "brouillon", json.dumps(lignes), form.get("notes", "")),
                )
                break
            except Exception as dup_err:
                if "Duplicate" in str(dup_err) and _attempt < 2:
                    continue
                raise
        logger.info("[ADMIN_AUDIT] action=facture_create numero=%s sponsor_id=%s montant_ttc=%s", numero, sponsor_id, float(montant_ttc))
    except Exception as e:
        logger.error("[ADMIN] facture create: %s", e)
        tpl = env.get_template("admin/facture_form.html")
        return HTMLResponse(tpl.render(active="factures", sponsors=sponsors, error=str(e)), status_code=500)

    return RedirectResponse(url="/admin/factures", status_code=302)


@router.get("/admin/factures/{facture_id}", response_class=HTMLResponse, include_in_schema=False)
async def admin_facture_detail(request: Request, facture_id: int):
    redir = _require_auth(request)
    if redir:
        return redir
    facture = await db_cloudsql.async_fetchone(
        "SELECT f.*, s.nom AS sponsor_nom FROM fia_factures f "
        "LEFT JOIN fia_sponsors s ON f.sponsor_id = s.id WHERE f.id = %s", (facture_id,))
    if not facture:
        return RedirectResponse(url="/admin/factures", status_code=302)
    lignes = json.loads(facture.get("lignes") or "[]")
    tpl = env.get_template("admin/facture_detail.html")
    return HTMLResponse(tpl.render(active="factures", facture=facture, lignes=lignes))


@router.post("/admin/factures/{facture_id}/status", include_in_schema=False)
async def admin_facture_update_status(request: Request, facture_id: int):
    redir = _require_auth(request)
    if redir:
        return redir
    form = await request.form()
    new_statut = form.get("statut", "")
    if new_statut in _VALID_STATUTS:
        try:
            await db_cloudsql.async_query(
                "UPDATE fia_factures SET statut = %s WHERE id = %s", (new_statut, facture_id))
            logger.info("[ADMIN_AUDIT] action=facture_status_update facture_id=%s new_statut=%s", facture_id, new_statut)
        except Exception as e:
            logger.error("[ADMIN] facture status update: %s", e)
    return RedirectResponse(url=f"/admin/factures/{facture_id}", status_code=302)


@router.get("/admin/factures/{facture_id}/pdf", include_in_schema=False)
@limiter.limit("30/minute")  # S15 V94
async def admin_facture_pdf(request: Request, facture_id: int):
    redir = _require_auth(request)
    if redir:
        return redir

    facture = await db_cloudsql.async_fetchone(
        "SELECT f.*, s.nom AS sponsor_nom, s.adresse AS sponsor_adresse FROM fia_factures f "
        "LEFT JOIN fia_sponsors s ON f.sponsor_id = s.id WHERE f.id = %s", (facture_id,))
    if not facture:
        return RedirectResponse(url="/admin/factures", status_code=302)

    config = await db_cloudsql.async_fetchone("SELECT * FROM fia_config_entreprise WHERE id = 1") or {}
    lignes = json.loads(facture.get("lignes") or "[]")

    # Convert date objects to strings for PDF
    for key in ("date_emission", "date_echeance", "periode_debut", "periode_fin"):
        if facture.get(key) and not isinstance(facture[key], str):
            facture[key] = str(facture[key])

    from services.admin_pdf import generate_invoice_pdf
    pdf_buf = generate_invoice_pdf(facture, config, lignes)

    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={facture['numero']}.pdf"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# CONTRATS CRUD (S06)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/contrats", response_class=HTMLResponse, include_in_schema=False)
async def admin_contrats_list(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    contrats = []
    try:
        contrats = await db_cloudsql.async_fetchall(
            "SELECT c.*, s.nom AS sponsor_nom FROM fia_contrats c "
            "LEFT JOIN fia_sponsors s ON c.sponsor_id = s.id "
            "ORDER BY c.created_at DESC"
        )
    except Exception as e:
        logger.error("[ADMIN] contrats list: %s", e)

    # V121 — Pool consumption for active/brouillon contracts
    pool_data = {}
    for c in contrats:
        if c.get("statut") in ("actif", "brouillon"):
            try:
                pool_data[c["id"]] = await _get_pool_consumed(c)
            except Exception as e:
                logger.error("[ADMIN] pool consumption contrat %s: %s", c.get("id"), e)
    tpl = env.get_template("admin/contrats.html")
    return HTMLResponse(tpl.render(active="contrats", contrats=contrats, pool_data=pool_data))


@router.get("/admin/contrats/new", response_class=HTMLResponse, include_in_schema=False)
async def admin_contrat_new_form(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom") or []
    tpl = env.get_template("admin/contrat_form.html")
    return HTMLResponse(tpl.render(active="contrats", contrat=None, sponsors=sponsors, error=None))


@router.post("/admin/contrats/new", response_class=HTMLResponse, include_in_schema=False)
async def admin_contrat_create(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    data, error = _validate_contrat_form(form)
    if error:
        sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom") or []
        tpl = env.get_template("admin/contrat_form.html")
        return HTMLResponse(tpl.render(active="contrats", contrat=None, sponsors=sponsors, error=error), status_code=400)

    try:
        # Generate numero with retry on duplicate
        for _attempt in range(3):
            cnt_row = await db_cloudsql.async_fetchone(
                "SELECT COUNT(*) AS cnt FROM fia_contrats WHERE numero LIKE %s",
                (f"CTR-{date.today().strftime('%Y%m')}-%",))
            numero = _next_contrat_number(cnt_row["cnt"] if cnt_row else 0)
            try:
                await db_cloudsql.async_query(
                    "INSERT INTO fia_contrats (sponsor_id, numero, type_contrat, product_codes, "
                    "date_debut, date_fin, montant_mensuel_ht, engagement_mois, "
                    "pool_impressions, mode_depassement, plafond_mensuel, conditions_particulieres) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (data["sponsor_id"], numero, data["type_contrat"], data["product_codes"],
                     data["date_debut"], data["date_fin"],
                     data["montant_mensuel_ht"],
                     data["engagement_mois"], data["pool_impressions"], data["mode_depassement"],
                     data["plafond_mensuel"], data["conditions_particulieres"]),
                )
                break
            except Exception as dup_err:
                if "Duplicate" in str(dup_err) and _attempt < 2:
                    continue
                raise
        logger.info("[ADMIN_AUDIT] action=contrat_create numero=%s sponsor_id=%s", numero, data["sponsor_id"])
    except Exception as e:
        logger.error("[ADMIN] contrat create: %s", e)
        sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom") or []
        tpl = env.get_template("admin/contrat_form.html")
        return HTMLResponse(tpl.render(active="contrats", contrat=None, sponsors=sponsors, error=str(e)), status_code=500)

    return RedirectResponse(url="/admin/contrats", status_code=302)


@router.get("/admin/contrats/{contrat_id}", response_class=HTMLResponse, include_in_schema=False)
async def admin_contrat_detail(request: Request, contrat_id: int):
    redir = _require_auth(request)
    if redir:
        return redir
    contrat = await db_cloudsql.async_fetchone(
        "SELECT c.*, s.nom AS sponsor_nom FROM fia_contrats c "
        "LEFT JOIN fia_sponsors s ON c.sponsor_id = s.id WHERE c.id = %s", (contrat_id,))
    if not contrat:
        return RedirectResponse(url="/admin/contrats", status_code=302)

    # V121 — Pool consumption for active/brouillon contracts
    impressions_data = None
    if contrat.get("statut") in ("actif", "brouillon"):
        try:
            impressions_data = await _get_pool_consumed(contrat)
        except Exception as e:
            logger.error("[ADMIN] pool consumption contrat %s: %s", contrat_id, e)
    tpl = env.get_template("admin/contrat_detail.html")
    return HTMLResponse(tpl.render(active="contrats", contrat=contrat, impressions_data=impressions_data))


@router.get("/admin/contrats/{contrat_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def admin_contrat_edit_form(request: Request, contrat_id: int):
    redir = _require_auth(request)
    if redir:
        return redir
    contrat = await db_cloudsql.async_fetchone("SELECT * FROM fia_contrats WHERE id = %s", (contrat_id,))
    if not contrat:
        return RedirectResponse(url="/admin/contrats", status_code=302)
    sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom") or []
    tpl = env.get_template("admin/contrat_form.html")
    return HTMLResponse(tpl.render(active="contrats", contrat=contrat, sponsors=sponsors, error=None))


@router.post("/admin/contrats/{contrat_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def admin_contrat_update(request: Request, contrat_id: int):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    data, error = _validate_contrat_form(form)
    if error:
        contrat = await db_cloudsql.async_fetchone("SELECT * FROM fia_contrats WHERE id = %s", (contrat_id,))
        sponsors = await db_cloudsql.async_fetchall("SELECT id, nom FROM fia_sponsors WHERE actif = 1 ORDER BY nom") or []
        tpl = env.get_template("admin/contrat_form.html")
        return HTMLResponse(tpl.render(active="contrats", contrat=contrat, sponsors=sponsors, error=error), status_code=400)

    try:
        await db_cloudsql.async_query(
            "UPDATE fia_contrats SET sponsor_id=%s, type_contrat=%s, product_codes=%s, "
            "date_debut=%s, date_fin=%s, montant_mensuel_ht=%s, engagement_mois=%s, "
            "pool_impressions=%s, mode_depassement=%s, plafond_mensuel=%s, "
            "conditions_particulieres=%s WHERE id=%s",
            (data["sponsor_id"], data["type_contrat"], data["product_codes"],
             data["date_debut"], data["date_fin"],
             data["montant_mensuel_ht"],
             data["engagement_mois"], data["pool_impressions"], data["mode_depassement"],
             data["plafond_mensuel"], data["conditions_particulieres"],
             contrat_id),
        )
        logger.info("[ADMIN_AUDIT] action=contrat_update contrat_id=%s", contrat_id)
    except Exception as e:
        logger.error("[ADMIN] contrat update: %s", e)

    return RedirectResponse(url=f"/admin/contrats/{contrat_id}", status_code=302)


@router.post("/admin/contrats/{contrat_id}/status", include_in_schema=False)
async def admin_contrat_update_status(request: Request, contrat_id: int):
    redir = _require_auth(request)
    if redir:
        return redir
    form = await request.form()
    new_statut = form.get("statut", "")
    if new_statut in _VALID_CONTRAT_STATUTS:
        try:
            await db_cloudsql.async_query(
                "UPDATE fia_contrats SET statut = %s WHERE id = %s", (new_statut, contrat_id))
            logger.info("[ADMIN_AUDIT] action=contrat_status_update contrat_id=%s new_statut=%s", contrat_id, new_statut)
        except Exception as e:
            logger.error("[ADMIN] contrat status update: %s", e)
    return RedirectResponse(url=f"/admin/contrats/{contrat_id}", status_code=302)


@router.get("/admin/contrats/{contrat_id}/pdf", include_in_schema=False)
@limiter.limit("30/minute")  # S15 V94
async def admin_contrat_pdf(request: Request, contrat_id: int):
    redir = _require_auth(request)
    if redir:
        return redir

    contrat = await db_cloudsql.async_fetchone(
        "SELECT c.*, s.nom AS sponsor_nom, s.adresse AS sponsor_adresse, s.siret AS sponsor_siret "
        "FROM fia_contrats c LEFT JOIN fia_sponsors s ON c.sponsor_id = s.id WHERE c.id = %s", (contrat_id,))
    if not contrat:
        return RedirectResponse(url="/admin/contrats", status_code=302)

    config = await db_cloudsql.async_fetchone("SELECT * FROM fia_config_entreprise WHERE id = 1") or {}

    from services.admin_pdf import generate_contrat_pdf
    pdf_buf = generate_contrat_pdf(contrat, config)

    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={contrat['numero']}.pdf"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG ENTREPRISE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/config", response_class=HTMLResponse, include_in_schema=False)
async def admin_config_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    cfg = {}
    try:
        cfg = await db_cloudsql.async_fetchone("SELECT * FROM fia_config_entreprise WHERE id = 1") or {}
    except Exception as e:
        logger.error("[ADMIN] config read: %s", e)
    from services.alerting import DEFAULT_THRESHOLDS, get_alert_thresholds
    try:
        alert_cfg = await get_alert_thresholds()
    except Exception:
        alert_cfg = dict(DEFAULT_THRESHOLDS)
    tpl = env.get_template("admin/config.html")
    return HTMLResponse(tpl.render(active="config", cfg=cfg, success=False,
                                   alert_cfg=alert_cfg, alert_success=False))


@router.post("/admin/config", response_class=HTMLResponse, include_in_schema=False)
async def admin_config_save(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()

    # V92 S04: defense-in-depth — SASU/SAS/SARL/EURL require rcs + capital_social
    forme_juridique = (form.get("forme_juridique") or "EI").strip()
    rcs = (form.get("rcs") or "").strip()
    capital_social = (form.get("capital_social") or "").strip()
    if forme_juridique != "EI":
        missing = []
        if not rcs:
            missing.append("RCS")
        if not capital_social:
            missing.append("capital social")
        if missing:
            cfg = {}
            try:
                cfg = await db_cloudsql.async_fetchone("SELECT * FROM fia_config_entreprise WHERE id = 1") or {}
            except Exception:
                pass
            from services.alerting import DEFAULT_THRESHOLDS, get_alert_thresholds
            try:
                alert_cfg = await get_alert_thresholds()
            except Exception:
                alert_cfg = dict(DEFAULT_THRESHOLDS)
            tpl = env.get_template("admin/config.html")
            return HTMLResponse(tpl.render(
                active="config", cfg=cfg, success=False,
                alert_cfg=alert_cfg, alert_success=False,
                error=f"{forme_juridique} requiert : {', '.join(missing)}",
            ))

    try:
        await db_cloudsql.async_query(
            "UPDATE fia_config_entreprise SET raison_sociale=%s, siret=%s, adresse=%s, "
            "code_postal=%s, ville=%s, pays=%s, email=%s, telephone=%s, "
            "tva_intra=%s, taux_tva=%s, iban=%s, bic=%s, "
            "forme_juridique=%s, rcs=%s, capital_social=%s WHERE id=1",
            (form.get("raison_sociale", ""), form.get("siret", ""),
             form.get("adresse", ""), form.get("code_postal", ""),
             form.get("ville", ""), form.get("pays", "France"),
             form.get("email", ""), form.get("telephone", ""),
             form.get("tva_intra", ""), float(form.get("taux_tva", 20)),
             form.get("iban", ""), form.get("bic", ""),
             forme_juridique, rcs, capital_social),
        )
        from utils import get_client_ip
        logger.info("[ADMIN_AUDIT] action=config_update ip=%s", get_client_ip(request))
    except Exception as e:
        logger.error("[ADMIN] config save: %s", e)

    cfg = {}
    try:
        cfg = await db_cloudsql.async_fetchone("SELECT * FROM fia_config_entreprise WHERE id = 1") or {}
    except Exception:
        pass
    from services.alerting import DEFAULT_THRESHOLDS, get_alert_thresholds
    try:
        alert_cfg = await get_alert_thresholds()
    except Exception:
        alert_cfg = dict(DEFAULT_THRESHOLDS)
    tpl = env.get_template("admin/config.html")
    return HTMLResponse(tpl.render(active="config", cfg=cfg, success=True,
                                   alert_cfg=alert_cfg, alert_success=False))


@router.post("/admin/config/alerts", response_class=HTMLResponse, include_in_schema=False)
async def admin_config_alerts_save(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    form = await request.form()
    _ALERT_KEYS = {
        "alert_error_rate_warn": lambda v: str(float(v) / 100),  # % → ratio
        "alert_error_rate_crit": lambda v: str(float(v) / 100),
        "alert_latency_p95_warn": lambda v: str(int(float(v))),
        "alert_latency_p95_crit": lambda v: str(int(float(v))),
        "alert_cpu_warn": lambda v: str(float(v) / 100),  # % → ratio
        "alert_cpu_crit": lambda v: str(float(v) / 100),
        "alert_memory_warn": lambda v: str(float(v) / 100),
        "alert_memory_crit": lambda v: str(float(v) / 100),
        "alert_gemini_avg_warn": lambda v: str(int(float(v))),
        "alert_gemini_avg_crit": lambda v: str(int(float(v))),
        "alert_cost_month_warn": lambda v: str(int(float(v))),
        "alert_cost_month_crit": lambda v: str(int(float(v))),
    }
    try:
        for key, convert in _ALERT_KEYS.items():
            val = form.get(key, "")
            if val:
                stored = convert(val)
                await db_cloudsql.async_query(
                    "INSERT INTO admin_config (config_key, config_value) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE config_value = %s",
                    (key, stored, stored),
                )
        logger.info("[ADMIN_AUDIT] action=alert_config_save keys_updated=%d", len(_ALERT_KEYS))
    except Exception as e:
        logger.error("[ADMIN] alert config save: %s", e)

    cfg = {}
    try:
        cfg = await db_cloudsql.async_fetchone("SELECT * FROM fia_config_entreprise WHERE id = 1") or {}
    except Exception:
        pass
    from services.alerting import get_alert_thresholds
    try:
        alert_cfg = await get_alert_thresholds()
    except Exception:
        from services.alerting import DEFAULT_THRESHOLDS
        alert_cfg = dict(DEFAULT_THRESHOLDS)
    tpl = env.get_template("admin/config.html")
    return HTMLResponse(tpl.render(active="config", cfg=cfg, success=False,
                                   alert_cfg=alert_cfg, alert_success=True))


# ══════════════════════════════════════════════════════════════════════════════
# TARIFS — Grille tarifaire EU + Switch EI/SASU
# ══════════════════════════════════════════════════════════════════════════════


async def _get_admin_config():
    """Read admin_config key-value pairs into a dict."""
    cfg = {"billing_mode": "EI", "ei_raison_sociale": "EmovisIA — Jean-Philippe Godard",
           "ei_siret": "", "sasu_raison_sociale": "LotoIA SASU", "sasu_siret": ""}
    try:
        rows = await db_cloudsql.async_fetchall("SELECT config_key, config_value FROM admin_config")
        for r in rows:
            cfg[r["config_key"]] = r["config_value"]
    except Exception as e:
        logger.error("[ADMIN] admin_config read: %s", e)
    return cfg


@router.get("/admin/tarifs", response_class=HTMLResponse, include_in_schema=False)
async def admin_tarifs_page(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir

    tpl = env.get_template("admin/tarifs.html")
    return HTMLResponse(tpl.render(
        active="tarifs",
        paliers=_PALIERS_V9,
    ))


@router.post("/admin/api/tarifs/mode", include_in_schema=False)
async def admin_api_tarifs_mode(request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        body = await request.json()
        mode = body.get("mode", "")
        if mode not in ("EI", "SASU"):
            return JSONResponse({"ok": False, "error": "Mode invalide"}, status_code=400)
        await db_cloudsql.async_query(
            "INSERT INTO admin_config (config_key, config_value) VALUES ('billing_mode', %s) "
            "ON DUPLICATE KEY UPDATE config_value = %s",
            (mode, mode),
        )
        from utils import get_client_ip
        logger.info("[ADMIN_AUDIT] action=tarif_mode_change mode=%s ip=%s", mode, get_client_ip(request))
        return JSONResponse({"ok": True, "mode": mode})
    except Exception as e:
        logger.error("[ADMIN] tarifs mode switch: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# sponsor_tarifs: monthly packages per product_code (LOTOIA_EXCLU V9).
# Used for admin /tarifs interface and commercial pricing grid.
# See also: fia_grille_tarifaire (per-event unit pricing, invoice calculation).
@router.put("/admin/api/tarifs/{code}", include_in_schema=False)
async def admin_api_tarifs_update(request: Request, code: str):
    err = _require_auth_json(request)
    if err:
        return err
    if code not in _VALID_TARIF_CODES:
        return JSONResponse({"ok": False, "error": "Code invalide"}, status_code=400)
    try:
        body = await request.json()
        tarif = float(body.get("tarif_mensuel", 0))
        engagement = int(body.get("engagement_min_mois", 3))
        red6 = float(body.get("reduction_6m", 10))
        red12 = float(body.get("reduction_12m", 20))
        active = int(body.get("active", 1))
        if tarif < 0 or engagement < 1 or not (0 <= red6 <= 100) or not (0 <= red12 <= 100):
            return JSONResponse({"ok": False, "error": "Valeurs invalides"}, status_code=400)
        await db_cloudsql.async_query(
            "UPDATE sponsor_tarifs SET tarif_mensuel=%s, engagement_min_mois=%s, "
            "reduction_6m=%s, reduction_12m=%s, active=%s WHERE code=%s",
            (tarif, engagement, red6, red12, active, code),
        )
        from utils import get_client_ip
        logger.info("[ADMIN_AUDIT] action=tarif_update code=%s ip=%s", code, get_client_ip(request))
        return JSONResponse({"ok": True, "code": code})
    except Exception as e:
        logger.error("[ADMIN] tarif update %s: %s", code, e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/admin/api/tarifs", include_in_schema=False)
async def admin_api_tarifs_data(request: Request):
    err = _require_auth_json(request)
    if err:
        return err
    try:
        cfg = await _get_admin_config()
        tarifs = await db_cloudsql.async_fetchall("SELECT * FROM sponsor_tarifs ORDER BY code")
        tarifs = [{k: (_dec(v) if isinstance(v, Decimal) else v) for k, v in row.items()} for row in tarifs]
        return JSONResponse({"billing_mode": cfg["billing_mode"], "tarifs": tarifs, "paliers": _PALIERS_V9})
    except Exception as e:
        logger.error("[ADMIN] tarifs API: %s", e)
        return JSONResponse({"billing_mode": "EI", "tarifs": [], "paliers": []}, status_code=500)
