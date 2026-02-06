"""Grok 4.1 client wrapper (via API).

Keep *all* LLM calls going through this client.
That makes it easy to swap auth, base URL, model name, retries, etc.
"""

from __future__ import annotations
import os
import httpx
from typing import List, Dict, Any

class GrokClient:
    def __init__(self):
        self.api_key = os.getenv("GROK_API_KEY", "")
        self.base_url = os.getenv("GROK_BASE_URL", "").rstrip("/")
        self.model = os.getenv("GROK_MODEL", "grok-4.1")

    async def chat(self, messages: List[Dict[str, Any]], temperature: float = 0.2, max_tokens: int = 2000) -> str:
        """Call Grok chat completion endpoint.

        NOTE: endpoint/payload may differ; adjust to LunarTech-provided docs.
        """
        if not self.api_key or not self.base_url:
            raise RuntimeError("Missing GROK_API_KEY or GROK_BASE_URL in environment.")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=60) as client:
            # Example path; confirm actual API
            r = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            # Typical OpenAI-style response:
            return data["choices"][0]["message"]["content"]
