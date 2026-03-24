from pydantic import BaseModel


class GenerateRequest(BaseModel):
    n: int = 5
    mode: str = "balanced"
