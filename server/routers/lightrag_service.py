"""
lightrag_service.py - WORKING VERSION (modular)

- LightRAG ingestion + query endpoints live here.
- Supabase persistence is delegated to supabase_router.py (keeps file size sane).

OpenAI-compatible providers are used for:
- LLM entity extraction (LLM_* env vars)
- Embeddings (EMBEDDINGS_* env vars)

Grok is NOT used in this file.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from dotenv import load_dotenv
from pathlib import Path
from typing import Any
import json
import os
from datetime import datetime

# Local module: keep Supabase plumbing elsewhere
from server.routers.supabase_router import sync_lightrag_artifacts_to_supabase

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
    history_messages: list | None = None,
    **kwargs,
) -> str:
    """
    OpenAI-compatible chat completion call used by LightRAG for extraction/reasoning.
    """
    import httpx

    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    if not api_key:
        raise ValueError("Missing LLM_API_KEY (or OPENAI_API_KEY) in environment.")

    url = f"{base_url.rstrip('/')}/chat/completions"

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": kwargs.get("temperature", 0.0),
        "max_tokens": kwargs.get("max_tokens", 4000),
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise ValueError(f"LLM API error ({e.response.status_code}): {e.response.text}") from e
    except Exception as e:
        raise ValueError(f"LLM API request failed: {str(e)}") from e


async def openai_compatible_embedding(texts: list[str]):
    """
    OpenAI-compatible embeddings call used by LightRAG.
    IMPORTANT: returns numpy ndarray (LightRAG expects .size / vector ops).
    """
    import httpx
    import numpy as np

    base_url = os.getenv("EMBEDDINGS_BASE_URL", "https://api.openai.com/v1")
    api_key = os.getenv("EMBEDDINGS_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")

    if not api_key:
        raise ValueError("Missing EMBEDDINGS_API_KEY (or OPENAI_API_KEY) in environment.")

    url = f"{base_url.rstrip('/')}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "input": texts}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        embeddings = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
        return np.asarray(embeddings, dtype=np.float32)
    except httpx.HTTPStatusError as e:
        raise ValueError(f"Embeddings API error ({e.response.status_code}): {e.response.text}") from e
    except Exception as e:
        raise ValueError(f"Embeddings API request failed: {str(e)}") from e


def _get_embedding_dim() -> int:
    """
    Prefer explicit EMBEDDINGS_DIM if set (avoids guessing / provider differences).
    Fallback to common OpenAI dims.
    """
    env_dim = os.getenv("EMBEDDINGS_DIM")
    if env_dim:
        try:
            return int(env_dim)
        except Exception:
            pass

    model = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")
    dim_map = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }
    return dim_map.get(model, 1536)


async def _get_lightrag() -> LightRAG:
    if not LIGHTRAG_AVAILABLE:
        raise HTTPException(status_code=500, detail="LightRAG not installed. Run: pip install lightrag-hku")

    global _lightrag_instance
    if _lightrag_instance is not None:
        return _lightrag_instance

    working_dir = os.getenv("LIGHTRAG_WORKING_DIR", "./lightrag_cache")

    llm_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    embed_key = os.getenv("EMBEDDINGS_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not llm_key:
        raise HTTPException(status_code=500, detail="Missing LLM_API_KEY (or OPENAI_API_KEY) in .env")
    if not embed_key:
        raise HTTPException(status_code=500, detail="Missing EMBEDDINGS_API_KEY (or OPENAI_API_KEY) in .env")

    _lightrag_instance = LightRAG(
        working_dir=working_dir,
        llm_model_func=openai_compatible_llm,
        embedding_func=EmbeddingFunc(
            embedding_dim=_get_embedding_dim(),
            max_token_size=8192,
            func=openai_compatible_embedding,
        ),
    )

    # Initialize storages before first use
    await _lightrag_instance.initialize_storages()
    return _lightrag_instance


# -----------------------------
# PDF helpers
# -----------------------------
def _extract_text_from_pdf(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise HTTPException(status_code=500, detail="pypdf not installed. Run: pip install pypdf") from e

    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"--- Page {i+1} ---\n{text}")
    return "\n\n".join(pages)


def _outputs_dir() -> Path:
    out = Path("./outputs")
    out.mkdir(parents=True, exist_ok=True)
    return out


# -----------------------------
# Routes
# -----------------------------
@router.post("/ingest-pdf")
async def ingest_pdf(file: UploadFile = File(...), description: str | None = None) -> dict[str, Any]:
    """
    Upload and ingest a PDF into LightRAG (builds graph + embeddings on disk).
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    temp_dir = Path("./temp_uploads")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / file.filename

    try:
        content = await file.read()
        temp_path.write_bytes(content)

        text = _extract_text_from_pdf(temp_path)
        if not text.strip():
            raise HTTPException(status_code=400, detail="PDF contains no extractable text")

        rag = await _get_lightrag()
        await rag.ainsert(text)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "filename": file.filename,
            "description": description,
            "char_count": len(text),
            "word_count": len(text.split()),
            "status": "success",
        }
        log_path = _outputs_dir() / "ingestion_log.jsonl"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

        return {
            "ok": True,
            "filename": file.filename,
            "char_count": len(text),
            "word_count": len(text.split()),
            "message": "PDF ingested into LightRAG working_dir",
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    finally:
        if temp_path.exists():
            temp_path.unlink()


@router.get("/ingest-local-pdfs")
async def ingest_local_pdfs(pdf_dir: str = ".") -> dict[str, Any]:
    """
    Ingest all PDFs from a local directory into LightRAG.
    """
    pdf_dir_path = Path(pdf_dir)
    if not pdf_dir_path.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {pdf_dir}")

    pdf_files = sorted(pdf_dir_path.glob("*.pdf"))
    if not pdf_files:
        return {"ok": False, "pdf_count": 0, "message": f"No PDF files found in {pdf_dir}"}

    rag = await _get_lightrag()
    results: list[dict[str, Any]] = []

    for pdf_path in pdf_files:
        try:
            text = _extract_text_from_pdf(pdf_path)
            if not text.strip():
                results.append({"filename": pdf_path.name, "status": "skipped", "reason": "No extractable text"})
                continue

            await rag.ainsert(text)
            results.append(
                {
                    "filename": pdf_path.name,
                    "status": "success",
                    "char_count": len(text),
                    "word_count": len(text.split()),
                }
            )
        except Exception as e:
            results.append({"filename": pdf_path.name, "status": "error", "error": str(e)})

    successful = sum(1 for r in results if r["status"] == "success")
    return {
        "ok": True,
        "pdf_count": len(pdf_files),
        "successful": successful,
        "failed": len(pdf_files) - successful,
        "results": results,
    }


@router.post("/query")
async def query_knowledge_graph(
    query: str,
    mode: str = Query(default="hybrid", pattern="^(naive|local|global|hybrid)$"),
) -> dict[str, Any]:
    """
    Query LightRAG’s knowledge graph (still uses on-disk working_dir).
    """
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        rag = await _get_lightrag()
        result = await rag.aquery(query, param=QueryParam(mode=mode))
        return {"ok": True, "query": query, "mode": mode, "response": result}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying knowledge graph: {str(e)}")


@router.post("/sync-to-supabase")
def sync_to_supabase(
    working_dir: str | None = None,
    batch_size: int = Query(default=200, ge=1, le=1000),
    store_doc_text: bool = Query(default=True),
) -> dict[str, Any]:
    """
    Phase 1 persistence: store ONLY documents + chunks + chunk embeddings in Supabase (pgvector).

    Delegates to supabase_router.sync_lightrag_artifacts_to_supabase to keep this file small.
    """
    wd = Path(working_dir or os.getenv("LIGHTRAG_WORKING_DIR", "./lightrag_cache"))
    return sync_lightrag_artifacts_to_supabase(
        working_dir=wd,
        batch_size=batch_size,
        store_doc_text=store_doc_text,
    )


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """
    Quick visibility into whether LightRAG has built artifacts in working_dir.
    """
    try:
        rag = await _get_lightrag()
        working_dir = Path(rag.working_dir)

        files_to_check = [
            "graph_chunk_entity_relation.graphml",
            "vdb_chunks.json",
            "kv_store_full_docs.json",
            "kv_store_text_chunks.json",
        ]
        file_status = {f: (working_dir / f).exists() for f in files_to_check}

        return {
            "ok": True,
            "working_dir": str(working_dir),
            "files": file_status,
            "config": {
                "llm_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
                "embeddings_model": os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small"),
                "embedding_dim": _get_embedding_dim(),
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.delete("/clear")
async def clear_knowledge_graph() -> dict[str, Any]:
    """
    Deletes LightRAG working_dir and resets the in-memory instance.
    """
    try:
        rag = await _get_lightrag()
        working_dir = Path(rag.working_dir)

        if working_dir.exists():
            import shutil
            shutil.rmtree(working_dir)

        global _lightrag_instance
        _lightrag_instance = None

        return {"ok": True, "message": "LightRAG working_dir cleared and instance reset."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing knowledge graph: {str(e)}")
