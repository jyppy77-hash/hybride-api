from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from engine.hybride import generate  # adapte si le nom de la fonction diffère
from engine.version import __version__

app = FastAPI(
    title="HYBRIDE API",
    description="Moteur HYBRIDE_OPTIMAL_V1 – API officielle",
    version=__version__
)


# =========================
# Schemas
# =========================

class AskPayload(BaseModel):
    prompt: str


# =========================
# Routes
# =========================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": "HYBRIDE_OPTIMAL_V1",
        "version": __version__
    }


@app.post("/ask")
def ask(payload: AskPayload):
    try:
        result = generate(payload.prompt)
        return {
            "success": True,
            "response": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))