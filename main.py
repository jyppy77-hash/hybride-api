from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine.hybride import generate
from engine.version import __version__

app = FastAPI(
    title="HYBRIDE API",
    description="Moteur HYBRIDE_OPTIMAL_V1 — API officielle",
    version=__version__
)

# =========================
# Static UI
# =========================

# Sert le dossier /ui (HTML / CSS / JS)
app.mount("/ui", StaticFiles(directory="ui"), name="ui")

# =========================
# Schemas
# =========================

class AskPayload(BaseModel):
    prompt: str

# =========================
# Routes
# =========================

@app.get("/")
def root():
    """
    Redirection vers l'UI live
    """
    return RedirectResponse(url="/ui/launcher.html")


@app.get("/health")
def health():
    """
    Endpoint healthcheck Cloud Run
    """
    return {
        "status": "ok",
        "engine": "HYBRIDE_OPTIMAL_V1",
        "version": __version__
    }


@app.post("/ask")
def ask(payload: AskPayload):
    """
    Endpoint principal du moteur HYBRIDE
    """
    try:
        result = generate(payload.prompt)
        return {
            "success": True,
            "response": result
        }
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal engine error"
        )
