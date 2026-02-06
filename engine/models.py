from pydantic import BaseModel
from typing import List


class GenerateRequest(BaseModel):
    n: int = 5
    mode: str = "safe"


class Ticket(BaseModel):
    nums: List[int]
    chance: int
    score: int  # Conservé pour compatibilité interne
    badges: List[str]
