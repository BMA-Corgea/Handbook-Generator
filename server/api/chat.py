"""Chat endpoint.

Responsibilities:
- Take a user question
- Retrieve context via retrieval_service (LightRAG + pgvector)
- Call Grok 4.1 with a grounded prompt
- Return answer + citations
"""

from fastapi import APIRouter
from server.models.schemas import ChatRequest, ChatResponse
from server.workflows.chat.chat_workflow import answer_question

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    return await answer_question(req)
