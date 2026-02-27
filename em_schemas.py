"""
Schemas Pydantic — EuroMillions
===============================
Equivalents EM des schemas Loto (schemas.py).
Differences cles :
  - 5 boules [1-50] (vs [1-49])
  - 2 etoiles [1-12] (vs 1 chance [1-10])
  - Champs supplementaires : jackpot_euros, nb_joueurs, nb_gagnants_rang1
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


# =========================
# Schema Grille EM
# =========================

class EMGridData(BaseModel):
    nums: Optional[List[int]] = []
    etoiles: Optional[List[int]] = []
    score: Optional[int] = None


# =========================
# Schema META ANALYSE EM
# =========================

class EMMetaAnalyseTextePayload(BaseModel):
    analysis_local: str = Field(..., max_length=5000)
    stats: Optional[Dict[str, Any]] = None
    window: Optional[str] = "GLOBAL"


# =========================
# Schema Pitch Grilles EM
# =========================

class EMPitchGrilleItem(BaseModel):
    numeros: List[int] = Field(..., max_length=5)
    etoiles: Optional[List[int]] = None
    score_conformite: Optional[int] = None
    severity: Optional[int] = None


class EMPitchGrillesRequest(BaseModel):
    grilles: List[EMPitchGrilleItem] = Field(..., max_length=10)


# =========================
# Schema Chat EM
# =========================

class EMChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., max_length=2000)


class EMChatRequest(BaseModel):
    message: str = Field(..., max_length=2000)
    page: str = Field(default="accueil-em")
    history: Optional[List[EMChatMessage]] = None
    lang: str = Field(default="fr", pattern=r"^(fr|en)$")


class EMChatResponse(BaseModel):
    response: str
    source: str = "gemini"
    mode: str = "decouverte"


# =========================
# Schema META PDF EM
# =========================

class EMMetaPdfPayload(BaseModel):
    analysis: Optional[str] = Field(default="", max_length=5000)
    window: Optional[str] = "75 tirages"
    engine: Optional[str] = "HYBRIDE"
    metaType: Optional[str] = "META75_EM"
    graph: Optional[str] = None
    graph_data_boules: Optional[Dict[str, Any]] = None
    graph_data_etoiles: Optional[Dict[str, Any]] = None
    sponsor: Optional[str] = None
