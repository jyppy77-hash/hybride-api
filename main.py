from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from engine.hybride import generate
from engine.version import __version__

app = FastAPI(
    title="HYBRIDE API",
    description="Moteur HYBRIDE_OPTIMAL_V1 — API officielle",
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

@app.get("/", response_class=HTMLResponse)
def root():
    """
    Page publique stand-by.
    L'API reste fonctionnelle.
    """
    return f"""
    <!DOCTYPE html>
    <html lang="fr">
        <head>
            <meta charset="utf-8">
            <title>LotoIA — HYBRIDE</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    margin: 0;
                    font-family: Arial, Helvetica, sans-serif;
                    background: #0b1220;
                    color: #ffffff;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    text-align: center;
                }}
                .box {{
                    max-width: 520px;
                    padding: 40px;
                }}
                h1 {{
                    font-size: 32px;
                    margin-bottom: 10px;
                }}
                p {{
                    font-size: 16px;
                    opacity: 0.85;
                }}
                .badge {{
                    margin-top: 20px;
                    display: inline-block;
                    padding: 6px 14px;
                    font-size: 13px;
                    border-radius: 20px;
                    background: #1f2937;
                    color: #9ca3af;
                }}
            </style>
        </head>
        <body>
            <div class="box">
                <h1>LotoIA</h1>
                <p>Moteur HYBRIDE_OPTIMAL_V1</p>
                <p>Interface en cours de finalisation.</p>
                <div class="badge">API active • v{__version__}</div>
            </div>
        </body>
    </html>
    """


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
