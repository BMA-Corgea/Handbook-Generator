from fastapi import FastAPI
import os
import httpx

app = FastAPI()

GROK_API_KEY = os.getenv("GROK_API_KEY")
GROK_BASE_URL = os.getenv("GROK_BASE_URL")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-4.1")

@app.get("/test-grok")
async def test_grok():
    headers = {"Authorization": f"Bearer {GROK_API_KEY}"}
    payload = {
        "model": GROK_MODEL,
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Say hello in 5 words."}
        ],
        "max_tokens": 50
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{GROK_BASE_URL}/chat/completions",
            json=payload,
            headers=headers
        )
        r.raise_for_status()
        return r.json()