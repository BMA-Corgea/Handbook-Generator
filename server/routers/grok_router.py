from __future__ import annotations

from fastapi import APIRouter, HTTPException
from server.clients.grok_client import GrokClient

router = APIRouter(prefix="/grok", tags=["grok"])


@router.get("/test_grok")
async def test_grok():
    """
    Smoke test endpoint. Calls Grok via GrokClient.
    """
    try:
        client = GrokClient()
        text = await client.chat_text(
            [{"role": "user", "content": "Say hello in exactly five words."}],
            temperature=0.0,
            max_tokens=50,
        )
        return {"ok": True, "model": client.model, "response": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
