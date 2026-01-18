from pydantic import BaseModel
from typing import List


class GenerateRequest(BaseModel):
    n: int = 5
    mode: str = "safe"


class Ticket(BaseModel):
    nums: List[int]
    chance: int
    score: int  # Conservé pour compatibilité backend
    note_etoiles: int  # 1-5
    note_texte: str  # "★★★★☆"
    note_disclaimer: str  # Explication
    badges: List[str]
