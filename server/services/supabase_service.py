"""Supabase adapter.

This isolates pgvector storage so your business logic doesn't care how data is stored.

TODO:
- Initialize Supabase client
- Create 'document_chunks' table: (document_id, chunk_id, text, embedding, metadata)
- Insert embeddings and metadata
- Query for top-k nearest neighbors by embedding
"""

from __future__ import annotations
from typing import List, Dict, Any

async def upsert_chunks(*, document_id: str, filename: str, chunks: List[Dict[str, Any]]) -> None:
    # TODO: implement with supabase-py or direct PostgREST
    return

async def query_similar_chunks(*, document_id: str, query: str, k: int = 8) -> List[Dict[str, Any]]:
    # TODO: embed query + run pgvector similarity search
    return []
