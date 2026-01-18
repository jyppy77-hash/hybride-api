from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import vertexai
from vertexai.generative_models import GenerativeModel

app = FastAPI()

vertexai.init(location="europe-west9")

model = GenerativeModel("gemini-1.5-flash")

class AskPayload(BaseModel):
    prompt: str

@app.get("/")
def health():
    return {"status": "ok", "service": "hybride-api"}

@app.post("/ask")
def ask(payload: AskPayload):
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt vide")

    response = model.generate_content(
        payload.prompt,
        generation_config={
            "temperature": 0.3,
            "max_output_tokens": 512,
        }
    )
    return {"output": response.text}
