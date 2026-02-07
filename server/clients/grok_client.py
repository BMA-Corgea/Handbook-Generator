from __future__ import annotations

import os
from typing import Any, Dict, List
import httpx


class GrokClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("GROK_API_KEY", "").strip()
        self.base_url = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1").strip().rstrip("/")
        self.model = os.getenv("GROK_MODEL", "grok-4").strip()

        if not self.api_key:
            raise RuntimeError("Missing GROK_API_KEY in environment (.env).")
        if not self.base_url:
            raise RuntimeError("Missing GROK_BASE_URL in environment (.env).")

    async def chat_json(
        self,
        messages: List[Dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        stream: bool = False,
    ) -> Dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)

        if r.status_code >= 400:
            raise RuntimeError(f"xAI error {r.status_code}: {r.text}")

        return r.json()

    async def chat_text(
        self,
        messages: List[Dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> str:
        data = await self.chat_json(messages, temperature=temperature, max_tokens=max_tokens, stream=False)
        return data["choices"][0]["message"]["content"]


# Convenience function (so callers don’t have to instantiate if they don’t want to)
async def grok_chat_text(
    messages: List[Dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 2000,
) -> str:
    return await GrokClient().chat_text(messages, temperature=temperature, max_tokens=max_tokens)
