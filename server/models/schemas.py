"""Pydantic request/response models.

Keep these stable and simple; it makes UI + tests easier.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class Citation(BaseModel):
    source: str = Field(..., description="Filename or document id")
    chunk_id: str = Field(..., description="Chunk identifier in storage")
    excerpt: str = Field(..., description="Short excerpt used to ground the answer")

class UploadResponse(BaseModel):
    document_id: str
    filename: str
    chunks_indexed: int

class ChatRequest(BaseModel):
    document_id: str
    question: str
    chat_history: Optional[List[Dict[str, Any]]] = None  # [{role, content}, ...]

class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation] = []

class HandbookRequest(BaseModel):
    document_id: str
    topic: str
    target_words: int = 20000

class HandbookResponse(BaseModel):
    title: str
    word_count: int
    handbook_markdown: str
    citations: List[Citation] = []
