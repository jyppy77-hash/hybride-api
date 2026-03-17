"""
API Contact — Formulaire de contact visiteurs
===============================================
POST /api/contact → validation + sanitization + INSERT MySQL
Pas d'email — feedback consultable via /admin/messages uniquement.
"""

import hashlib
import html
import logging
import re

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator
from typing import Optional

import db_cloudsql
from rate_limit import limiter
from utils import get_client_ip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["contact"])

_VALID_SUJETS = {"bug", "suggestion", "question", "autre"}
_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


class ContactSubmit(BaseModel):
    nom: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    sujet: str = Field(..., max_length=200)
    message: str = Field(..., min_length=10, max_length=2000)
    page_source: Optional[str] = Field(None, max_length=100)
    lang: Optional[str] = Field("fr", max_length=5)

    @field_validator("sujet")
    @classmethod
    def validate_sujet(cls, v):
        if v.strip().lower() not in _VALID_SUJETS:
            raise ValueError(f"sujet must be one of: {', '.join(_VALID_SUJETS)}")
        return v.strip().lower()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if v is not None:
            v = v.strip()
            if v and not _EMAIL_REGEX.match(v):
                raise ValueError("Invalid email format")
            if not v:
                return None
        return v


@router.post("/contact")
@limiter.limit("3/minute")
async def submit_contact(request: Request):
    """Submit a contact message (honeypot-protected, rate-limited)."""
    try:
        body = await request.json()
    except Exception:
        logger.warning("[CONTACT] Invalid JSON body")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Honeypot check — silent accept but don't store
    honey = body.get("_honey", "")
    if honey:
        logger.info("[CONTACT] Honeypot triggered — silent reject")
        return {"status": "ok"}

    # Validate via pydantic
    try:
        data = ContactSubmit(**body)
    except ValidationError as e:
        logger.warning("[CONTACT] Validation failed: %s", str(e)[:200])
        raise HTTPException(status_code=422, detail=str(e))

    # Sanitize fields
    nom = html.escape(data.nom.strip())[:100] if data.nom and data.nom.strip() else None
    email = data.email  # already validated
    sujet = html.escape(data.sujet)
    message = html.escape(data.message.strip())[:2000]
    page_source = html.escape(data.page_source.strip())[:100] if data.page_source and data.page_source.strip() else None
    lang = (data.lang or "fr")[:5]

    # IP hash for RGPD (use shared get_client_ip)
    client_ip = get_client_ip(request)
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]

    # Session hash
    session_hash = body.get("session_id", "")[:64] or None

    try:
        sql = """
            INSERT INTO contact_messages (nom, email, sujet, message, page_source, lang, ip, session_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        await db_cloudsql.async_query(sql, (nom, email, sujet, message, page_source, lang, ip_hash, session_hash))
        logger.info("[CONTACT] OK sujet=%s lang=%s page=%s nom=%s", sujet, lang, page_source, nom or "anonymous")
    except Exception as e:
        logger.error("[CONTACT ERROR] DB insert failed: %s", e)
        raise HTTPException(status_code=500, detail="Erreur lors de l'enregistrement")

    return {"status": "ok"}
