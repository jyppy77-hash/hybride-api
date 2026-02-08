from pydantic import BaseModel
from typing import Optional, Dict, Any


# =========================
# Schema moteur HYBRIDE
# =========================

class AskPayload(BaseModel):
    prompt: str


# =========================
# Schemas Tracking
# =========================

class GridData(BaseModel):
    nums: Optional[list[int]] = []
    chance: Optional[int] = 0
    score: Optional[int] = None

class TrackGridPayload(BaseModel):
    grid_id: Optional[str] = "unknown"
    grid_number: Optional[int] = 0
    grid_data: Optional[GridData] = None
    target_date: Optional[str] = "unknown"
    timestamp: Optional[int] = None
    session_id: Optional[str] = "anonymous"

class TrackAdImpressionPayload(BaseModel):
    ad_id: Optional[str] = "unknown"
    timestamp: Optional[int] = None
    session_id: Optional[str] = "anonymous"

class TrackAdClickPayload(BaseModel):
    ad_id: Optional[str] = "unknown"
    partner_id: Optional[str] = "unknown"
    timestamp: Optional[int] = None
    session_id: Optional[str] = "anonymous"


# =========================
# Schema META ANALYSE Texte
# =========================

class MetaAnalyseTextePayload(BaseModel):
    analysis_local: str
    stats: Optional[Dict[str, Any]] = None
    window: Optional[str] = "GLOBAL"


class MetaPdfPayload(BaseModel):
    analysis: Optional[str] = ""
    window: Optional[str] = "75 tirages"
    engine: Optional[str] = "HYBRIDE_OPTIMAL_V1"
    metaType: Optional[str] = "META75"
    graph: Optional[str] = None
    graph_data: Optional[Dict[str, Any]] = None
    sponsor: Optional[str] = None


# =========================
# Schemas HYBRIDE Chatbot
# =========================

class ChatMessage(BaseModel):
    role: str       # "user" ou "assistant"
    content: str

class HybrideChatRequest(BaseModel):
    message: str
    page: str = "accueil"    # accueil | loto | simulateur | statistiques
    history: list[ChatMessage] = []

class HybrideChatResponse(BaseModel):
    response: str
    source: str = "gemini"   # gemini | fallback
    mode: str = "decouverte" # decouverte | analyse | meta


# =========================
# Schema Pitch Grilles
# =========================

class PitchGrilleItem(BaseModel):
    numeros: list[int]
    chance: Optional[int] = None

class PitchGrillesRequest(BaseModel):
    grilles: list[PitchGrilleItem]
