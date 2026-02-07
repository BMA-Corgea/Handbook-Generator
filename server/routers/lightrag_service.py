"""
lightrag_service.py - WORKING VERSION

This properly uses LightRAG with OpenAI API for embeddings and entity extraction.
Grok is NOT used here - only for handbook generation in a separate service.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from dotenv import load_dotenv
from pathlib import Path
from typing import Any
import json
import os
from datetime import datetime
import asyncio

# Only import what actually exists in LightRAG
try:
    from lightrag import LightRAG, QueryParam
    from lightrag.utils import EmbeddingFunc
    LIGHTRAG_AVAILABLE = True
except ImportError:
    LIGHTRAG_AVAILABLE = False
    print("WARNING: LightRAG not installed. Install with: pip install lightrag-hku")

load_dotenv()

router = APIRouter(prefix="/lightrag", tags=["lightrag"])

# Global LightRAG instance
_lightrag_instance: LightRAG | None = None


# -----------------------------
# Custom LLM and Embedding Functions
# -----------------------------

async def openai_compatible_llm(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list = None,
    **kwargs
) -> str:
    """
    Custom LLM function for OpenAI API.
    This is used by LightRAG for entity extraction and reasoning.
    """
    import httpx
    
    # Use LLM-specific env vars, fallback to generic OPENAI_API_KEY
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    
    if not api_key:
        raise ValueError(
            "LLM_API_KEY or OPENAI_API_KEY required in environment. "
            "Get your key at: https://platform.openai.com/api-keys"
        )
    
    url = f"{base_url.rstrip('/')}/chat/completions"
    
    # Build messages
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": kwargs.get("temperature", 0.0),
        "max_tokens": kwargs.get("max_tokens", 4000)
    }
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        
        return data["choices"][0]["message"]["content"]
    
    except httpx.HTTPStatusError as e:
        error_detail = e.response.text if hasattr(e.response, 'text') else str(e)
        raise ValueError(f"LLM API error ({e.response.status_code}): {error_detail}")
    except Exception as e:
        raise ValueError(f"LLM API request failed: {str(e)}")


async def openai_compatible_embedding(texts: list[str]):
    import httpx
    import numpy as np

    base_url = os.getenv("EMBEDDINGS_BASE_URL", "https://api.openai.com/v1")
    api_key = os.getenv("EMBEDDINGS_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")

    if not api_key:
        raise ValueError(
            "EMBEDDINGS_API_KEY or OPENAI_API_KEY required in environment."
        )

    url = f"{base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {"model": model, "input": texts}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        embeddings = [
            item["embedding"]
            for item in sorted(data["data"], key=lambda x: x["index"])
        ]

        # ✅ CRITICAL: return ndarray so LightRAG can call .size and do vector ops
        return np.asarray(embeddings, dtype=np.float32)

    except httpx.HTTPStatusError as e:
        error_detail = e.response.text if hasattr(e.response, "text") else str(e)
        raise ValueError(f"Embeddings API error ({e.response.status_code}): {error_detail}")
    except Exception as e:
        raise ValueError(f"Embeddings API request failed: {str(e)}")

def _get_embedding_dim() -> int:
    """Get embedding dimension based on model."""
    model = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")
    
    # Common OpenAI embedding dimensions
    dim_map = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }
    
    return dim_map.get(model, 1536)


async def _get_lightrag() -> LightRAG:
    """
    Initialize LightRAG with OpenAI API functions.
    
    Environment variables required:
    - OPENAI_API_KEY (or LLM_API_KEY and EMBEDDINGS_API_KEY separately)
    - Optional: LLM_MODEL, EMBEDDINGS_MODEL, LLM_BASE_URL, EMBEDDINGS_BASE_URL
    """
    if not LIGHTRAG_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="LightRAG not installed. Run: pip install lightrag-hku"
        )
    
    global _lightrag_instance
    
    if _lightrag_instance is not None:
        return _lightrag_instance
    
    working_dir = os.getenv("LIGHTRAG_WORKING_DIR", "./lightrag_cache")
    
    # Verify API keys are set
    llm_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    embed_key = os.getenv("EMBEDDINGS_API_KEY") or os.getenv("OPENAI_API_KEY")
    
    if not llm_key:
        raise HTTPException(
            status_code=500,
            detail="Missing OpenAI API key. Set LLM_API_KEY or OPENAI_API_KEY in .env"
        )
    
    if not embed_key:
        raise HTTPException(
            status_code=500,
            detail="Missing OpenAI API key. Set EMBEDDINGS_API_KEY or OPENAI_API_KEY in .env"
        )
    
    # Initialize LightRAG with our custom OpenAI functions
    _lightrag_instance = LightRAG(
        working_dir=working_dir,
        llm_model_func=openai_compatible_llm,
        embedding_func=EmbeddingFunc(
            embedding_dim=int(os.getenv("EMBEDDINGS_DIM", "1536")),
            max_token_size=8192,
            func=openai_compatible_embedding
        )
    )
    
    # CRITICAL: Initialize storages before first use
    await _lightrag_instance.initialize_storages()
    
    return _lightrag_instance


def _extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="pypdf not installed. Run: pip install pypdf"
        )
    
    reader = PdfReader(str(pdf_path))
    pages = []
    
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"--- Page {i+1} ---\n{text}")
    
    return "\n\n".join(pages)


def _outputs_dir() -> Path:
    """Ensure outputs directory exists."""
    out = Path("./outputs")
    out.mkdir(parents=True, exist_ok=True)
    return out


# -----------------------------
# Routes
# -----------------------------

@router.post("/ingest-pdf")
async def ingest_pdf(
    file: UploadFile = File(...),
    description: str | None = None
) -> dict[str, Any]:
    """
    Upload and ingest a PDF into the LightRAG knowledge graph.
    
    Steps:
    1. Extract text from PDF
    2. Insert into LightRAG (builds knowledge graph with entities & relationships)
    3. Store for later retrieval
    
    Uses OpenAI API for:
    - Embeddings (text-embedding-3-small by default)
    - Entity extraction (gpt-4o-mini by default)
    """
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Save uploaded file temporarily
    temp_dir = Path("./temp_uploads")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / file.filename
    
    try:
        # Save file
        content = await file.read()
        temp_path.write_bytes(content)
        
        # Extract text
        text = _extract_text_from_pdf(temp_path)
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="PDF contains no extractable text")
        
        # Get LightRAG instance
        rag = await _get_lightrag()
        
        # Insert into knowledge graph
        # This will extract entities, build graph, create embeddings
        await rag.ainsert(text)
        
        # Log the ingestion
        char_count = len(text)
        word_count = len(text.split())
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "filename": file.filename,
            "description": description,
            "char_count": char_count,
            "word_count": word_count,
            "status": "success"
        }
        
        # Save log
        log_path = _outputs_dir() / "ingestion_log.jsonl"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        return {
            "ok": True,
            "filename": file.filename,
            "char_count": char_count,
            "word_count": word_count,
            "message": "PDF successfully ingested into knowledge graph"
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        # API key or API call errors
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing PDF: {str(e)}"
        )
    finally:
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()


@router.get("/ingest-local-pdfs")
async def ingest_local_pdfs(
    pdf_dir: str = ".",
) -> dict[str, Any]:
    """
    Ingest all PDFs from a local directory.
    Useful for batch processing.
    
    Uses OpenAI API for embeddings and entity extraction.
    """
    pdf_dir_path = Path(pdf_dir)
    if not pdf_dir_path.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {pdf_dir}")
    
    pdf_files = sorted(pdf_dir_path.glob("*.pdf"))
    
    if not pdf_files:
        return {
            "ok": False,
            "pdf_count": 0,
            "message": f"No PDF files found in {pdf_dir}"
        }
    
    results = []
    
    try:
        rag = await _get_lightrag()
    except HTTPException as e:
        raise e
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    for pdf_path in pdf_files:
        try:
            text = _extract_text_from_pdf(pdf_path)
            
            if not text.strip():
                results.append({
                    "filename": pdf_path.name,
                    "status": "skipped",
                    "reason": "No extractable text"
                })
                continue
            
            # Insert into knowledge graph
            await rag.ainsert(text)
            
            results.append({
                "filename": pdf_path.name,
                "status": "success",
                "char_count": len(text),
                "word_count": len(text.split())
            })
            
        except Exception as e:
            results.append({
                "filename": pdf_path.name,
                "status": "error",
                "error": str(e)
            })
    
    successful = sum(1 for r in results if r["status"] == "success")
    
    return {
        "ok": True,
        "pdf_count": len(pdf_files),
        "successful": successful,
        "failed": len(pdf_files) - successful,
        "results": results
    }


@router.post("/query")
async def query_knowledge_graph(
    query: str,
    mode: str = Query(default="hybrid", regex="^(naive|local|global|hybrid)$")
) -> dict[str, Any]:
    """
    Query the knowledge graph built from your PDFs.
    
    Modes:
    - naive: Simple vector similarity search
    - local: Entity-based local search (good for specific questions)
    - global: Community-based global search (good for broad topics)
    - hybrid: Combines local + global (recommended)
    
    Uses OpenAI embeddings for semantic search.
    """
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    try:
        rag = await _get_lightrag()
        
        # Query the knowledge graph
        result = await rag.aquery(
            query,
            param=QueryParam(mode=mode)
        )
        
        return {
            "ok": True,
            "query": query,
            "mode": mode,
            "response": result
        }
        
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error querying knowledge graph: {str(e)}"
        )


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """
    Get status of the LightRAG knowledge graph.
    Shows what's been indexed and ready for querying.
    """
    try:
        rag = await _get_lightrag()
        working_dir = Path(rag.working_dir)
        
        # Check what's been indexed
        files_to_check = [
            "graph_chunk_entity_relation.graphml",
            "vdb_chunks.json",
            "kv_store_full_docs.json"
        ]
        
        file_status = {
            f: (working_dir / f).exists() 
            for f in files_to_check
        }
        
        has_graph = file_status.get("graph_chunk_entity_relation.graphml", False)
        
        return {
            "ok": True,
            "working_dir": str(working_dir),
            "has_knowledge_graph": has_graph,
            "files": file_status,
            "ready": has_graph,
            "config": {
                "llm_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
                "embeddings_model": os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small"),
                "embedding_dim": _get_embedding_dim()
            }
        }
        
    except ValueError as e:
        return {
            "ok": False,
            "error": str(e)
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }


@router.delete("/clear")
async def clear_knowledge_graph() -> dict[str, Any]:
    """
    Clear the entire knowledge graph.
    Useful for starting fresh or testing.
    """
    try:
        rag = await _get_lightrag()
        working_dir = Path(rag.working_dir)
        
        if working_dir.exists():
            import shutil
            shutil.rmtree(working_dir)
        
        # Reset instance
        global _lightrag_instance
        _lightrag_instance = None
        
        return {
            "ok": True,
            "message": "Knowledge graph cleared successfully"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error clearing knowledge graph: {str(e)}"
        )


# Keep the old endpoint for backwards compatibility, but mark as deprecated
@router.get("/dump-pdf-vectors")
async def dump_pdf_vectors_deprecated(
    pdf_dir: str = ".",
    chunk_chars: int = Query(default=2500, ge=200, le=20000),
    overlap_chars: int = Query(default=250, ge=0, le=5000),
    include_text: bool = Query(default=True),
) -> dict[str, Any]:
    """
    DEPRECATED: Use /ingest-local-pdfs instead.
    
    This endpoint is kept for backwards compatibility but redirects
    to the proper LightRAG ingestion.
    """
    return {
        "ok": False,
        "deprecated": True,
        "message": "This endpoint is deprecated. Use POST /lightrag/ingest-pdf or GET /lightrag/ingest-local-pdfs instead.",
        "new_endpoints": {
            "single_pdf": "POST /lightrag/ingest-pdf",
            "batch_pdfs": "GET /lightrag/ingest-local-pdfs?pdf_dir=."
        }
    }