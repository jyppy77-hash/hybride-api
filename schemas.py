from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal


# =========================
# Schema moteur HYBRIDE
# =========================

class AskPayload(BaseModel):
    prompt: str = Field(..., max_length=2000)


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
    analysis_local: str = Field(..., max_length=5000)
    stats: Optional[Dict[str, Any]] = None
    window: Optional[str] = "GLOBAL"


class MetaPdfPayload(BaseModel):
    analysis: Optional[str] = Field(default="", max_length=5000)
    window: Optional[str] = "75 tirages"
    engine: Optional[str] = "HYBRIDE_OPTIMAL_V1"
    metaType: Optional[str] = "META75"
    graph: Optional[str] = None
    graph_data: Optional[Dict[str, Any]] = None
    chance_data: Optional[Dict[str, Any]] = None
    sponsor: Optional[str] = None


# =========================
# Schemas HYBRIDE Chatbot
# =========================

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=2000)

class HybrideChatRequest(BaseModel):
    message: str = Field(..., max_length=2000)
    page: Literal["accueil", "loto", "simulateur", "statistiques"] = "accueil"
    history: list[ChatMessage] = Field(default=[], max_length=20)

class HybrideChatResponse(BaseModel):
    response: str
    source: str = "gemini"   # gemini | fallback
    mode: str = "decouverte" # decouverte | analyse | meta


# =========================
# Schema Pitch Grilles
# =========================

class PitchGrilleItem(BaseModel):
    numeros: list[int] = Field(..., max_length=5)
    chance: Optional[int] = None
    score_conformite: Optional[int] = None
    severity: Optional[int] = None

class PitchGrillesRequest(BaseModel):
    grilles: list[PitchGrilleItem] = Field(..., max_length=10)


# =========================
# Schemas Notation (Ratings)
# =========================

class RatingSubmit(BaseModel):
    source: str = Field(..., pattern=r"^(chatbot_loto|chatbot_em|popup_accueil)$")
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=500)
    session_id: str = Field(..., min_length=10, max_length=64)
    page: Optional[str] = "/"

class RatingResponse(BaseModel):
    success: bool
    message: str

class RatingAggregate(BaseModel):
    avg_rating: float
    review_count: int
    source: Optional[str] = None
