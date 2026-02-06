"""Chat workflow.

- Retrieves relevant context from the indexed PDFs
- Calls Grok with a grounded instruction
- Returns answer + citations
"""

from __future__ import annotations
from server.models.schemas import ChatRequest, ChatResponse
from server.retrieval.retrieval_service import retrieve_context
from server.services.grok_client import GrokClient

SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer using ONLY the provided context. "
    "If the context is insufficient, say so clearly. Cite sources by chunk_id when relevant."
)

async def answer_question(req: ChatRequest) -> ChatResponse:
    context, citations = await retrieve_context(document_id=req.document_id, query=req.question, k=8)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        messages.append({"role": "system", "content": f"CONTEXT:\n{context}"})
    # Optional: include brief history (keep short to avoid token bloat)
    if req.chat_history:
        messages.extend(req.chat_history[-6:])

    messages.append({"role": "user", "content": req.question})

    client = GrokClient()
    answer = await client.chat(messages, max_tokens=1200)

    return ChatResponse(answer=answer, citations=citations)
