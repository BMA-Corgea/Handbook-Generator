from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
import os
import httpx

load_dotenv()
app = FastAPI()

@app.get("/test-grok")
async def test_grok():
    grok_api_key = os.getenv("GROK_API_KEY")
    grok_base_url = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1").rstrip("/")
    grok_model = os.getenv("GROK_MODEL", "grok-4")  # default to grok-4

    if not grok_api_key:
        raise HTTPException(500, "Missing GROK_API_KEY")
    if not grok_base_url:
        raise HTTPException(500, "Missing GROK_BASE_URL")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {grok_api_key}",
    }

    payload = {
        "model": grok_model,
        "messages": [
            {"role": "user", "content": "What is the meaning of life, the universe, and everything?"}
        ],
        "stream": False,
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{grok_base_url}/chat/completions", json=payload, headers=headers)

    # If it fails, return useful debugging info
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()
