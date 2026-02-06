"""Upload & ingestion endpoints.

Responsibilities:
- Accept PDF(s)
- Extract text
- Chunk text
- Create embeddings + store in Supabase (pgvector)
- Build/update LightRAG knowledge graph / index
"""

from fastapi import APIRouter, UploadFile, File
from server.models.schemas import UploadResponse
from server.services.ingest_service import ingest_pdf_bytes

router = APIRouter()

@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = File(...)):
    data = await file.read()
    result = await ingest_pdf_bytes(filename=file.filename, pdf_bytes=data)
    return result
