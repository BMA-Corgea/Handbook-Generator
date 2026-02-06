"""Ingestion orchestration.

Coordinates:
- PDF text extraction
- Chunking
- Storage (Supabase)
- LightRAG indexing
"""

from __future__ import annotations
import uuid
from server.models.schemas import UploadResponse
from server.services.pdf_service import extract_text_from_pdf_bytes
from server.services.chunking_service import chunk_text
from server.services.supabase_service import upsert_chunks
from server.services.lightrag_service import index_document

async def ingest_pdf_bytes(*, filename: str, pdf_bytes: bytes) -> UploadResponse:
    document_id = str(uuid.uuid4())
    text = extract_text_from_pdf_bytes(pdf_bytes)
    chunks = chunk_text(text)

    # Prepare records for storage.
    records = [{"chunk_id": c.chunk_id, "text": c.text, "source": filename} for c in chunks]

    # Store in Supabase (embeddings to be added in that layer).
    await upsert_chunks(document_id=document_id, filename=filename, chunks=records)

    # Build LightRAG graph/index
    await index_document(document_id=document_id)

    return UploadResponse(document_id=document_id, filename=filename, chunks_indexed=len(chunks))
