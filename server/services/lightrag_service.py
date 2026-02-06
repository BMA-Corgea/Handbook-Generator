"""LightRAG adapter.

Goal: keep LightRAG-specific code here.

TODO:
- Build / update knowledge graph from stored chunks
- Provide retrieval that can combine graph traversal + vector search
"""

from __future__ import annotations
from typing import List, Dict, Any

async def index_document(*, document_id: str) -> None:
    # TODO: call LightRAG ingestion/index routines
    return

async def retrieve(*, document_id: str, query: str, k: int = 8) -> List[Dict[str, Any]]:
    # TODO: use LightRAG retrieval; return list of {chunk_id, text, source}
    return []
