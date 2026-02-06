"""Shared retrieval service.

Both chat and handbook workflows call this.
"""

from __future__ import annotations
from typing import List
from server.models.schemas import Citation
from server.services.lightrag_service import retrieve as lightrag_retrieve

async def retrieve_context(*, document_id: str, query: str, k: int = 8) -> tuple[str, List[Citation]]:
    results = await lightrag_retrieve(document_id=document_id, query=query, k=k)

    citations: List[Citation] = []
    context_parts: List[str] = []
    for r in results:
        text = (r.get("text") or "").strip()
        if not text:
            continue
        context_parts.append(text)
        citations.append(
            Citation(
                source=r.get("source", "unknown"),
                chunk_id=r.get("chunk_id", "unknown"),
                excerpt=text[:240],
            )
        )

    context = "\n\n---\n\n".join(context_parts)
    return context, citations
