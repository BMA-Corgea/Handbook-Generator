"""
lightrag_service.py

Fix for "LightRAG compounds on new PDFs even with per-doc working_dir cleanup".

What’s actually happening (based on your evidence):
- You digest into shoes-test folder (OK).
- You digest into cheese-50-words folder (new empty files show 0 records loaded).
- Yet kv_store_full_docs.json for cheese ends up containing shoes + cheese.

That can only happen if LightRAG (or its storages) are sharing process-global state
(module singletons / caches) across instances inside the same Python process.

Real fix:
- Run each ingestion in a fresh Python process (subprocess / multiprocessing spawn).
  That guarantees hard isolation even if LightRAG uses module-level singletons.

This file implements that:
- /ingest-staged extracts text in main process
- then runs the ingestion itself in a separate spawned process
"""

from __future__ import annotations

import os
import re
import json
import shutil
import traceback
import multiprocessing as mp
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from dotenv import load_dotenv

# Local import for Supabase syncing
from server.routers.supabase_router import sync_lightrag_artifacts_to_supabase

try:
    from lightrag import LightRAG, QueryParam
    from lightrag.utils import EmbeddingFunc
    LIGHTRAG_AVAILABLE = True
except ImportError:
    LIGHTRAG_AVAILABLE = False

load_dotenv()
router = APIRouter(prefix="/lightrag", tags=["lightrag"])


# -----------------------------
# Models
# -----------------------------
class IngestStagedRequest(BaseModel):
    saved_name: str
    original_name: str | None = None
    doc_key: str | None = None


# -----------------------------
# Helpers
# -----------------------------
def _pdf_imports_dir() -> Path:
    d = Path(os.getenv("PDF_IMPORTS_DIR", "./pdf_imports"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _lightrag_root_dir() -> Path:
    root = Path(os.getenv("LIGHTRAG_WORKING_DIR", "./lightrag_cache"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slugify(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return name or f"doc-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _nuke_working_dir(working_dir: Path) -> None:
    """
    Delete the directory entirely and recreate it.
    (We do this before spawning the subprocess.)
    """
    if working_dir.exists():
        shutil.rmtree(working_dir)
    working_dir.mkdir(parents=True, exist_ok=True)


def _extract_text_from_pdf(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise HTTPException(status_code=500, detail="pypdf not installed. Run: pip install pypdf") from e

    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for i, page in enumerate(reader.pages):
        txt = page.extract_text() or ""
        if txt.strip():
            pages.append(f"--- Page {i+1} ---\n{txt}")
    return "\n\n".join(pages)


def _get_embedding_dim() -> int:
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


def _require_env() -> None:
    llm_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    emb_key = os.getenv("EMBEDDINGS_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    if not llm_key:
        raise HTTPException(status_code=500, detail="Missing LLM_API_KEY (or OPENAI_API_KEY)")
    if not emb_key:
        raise HTTPException(status_code=500, detail="Missing EMBEDDINGS_API_KEY (or OPENAI_API_KEY or LLM_API_KEY)")


def _read_json_safe(path: Path) -> Any | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# -----------------------------
# LLM / Embedding funcs
# NOTE: These must be top-level picklable functions because we use multiprocessing spawn.
# -----------------------------
async def llm_model_func(prompt, system_prompt=None, history_messages=None, **kwargs) -> str:
    import httpx

    base_url = os.getenv("LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    if not base_url:
        raise RuntimeError("LLM_BASE_URL not set")
    if not api_key:
        raise RuntimeError("LLM_API_KEY (or OPENAI_API_KEY) not set")

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(kwargs.get("temperature", 0.0)),
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]


async def embedding_func(texts: list[str]):
    import httpx
    import numpy as np

    base_url = os.getenv("EMBEDDINGS_BASE_URL") or os.getenv("LLM_BASE_URL")
    api_key = os.getenv("EMBEDDINGS_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY", "")
    model = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")

    if not base_url:
        raise RuntimeError("EMBEDDINGS_BASE_URL (or LLM_BASE_URL) not set")
    if not api_key:
        raise RuntimeError("EMBEDDINGS_API_KEY (or OPENAI_API_KEY or LLM_API_KEY) not set")

    url = f"{base_url.rstrip('/')}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"model": model, "input": texts}

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    embs = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
    return np.asarray(embs, dtype=np.float32)


# -----------------------------
# Subprocess ingestion (hard isolation)
# -----------------------------
def _ingest_worker_process(conn, working_dir_str: str, text: str) -> None:
    """
    Runs in a fresh spawned process.
    This is the key isolation boundary that prevents cross-digestion contamination.
    """
    try:
        from lightrag import LightRAG
        from lightrag.utils import EmbeddingFunc

        working_dir = Path(working_dir_str).resolve()
        working_dir.mkdir(parents=True, exist_ok=True)

        rag = LightRAG(
            working_dir=str(working_dir),
            llm_model_func=llm_model_func,
            embedding_func=EmbeddingFunc(
                embedding_dim=_get_embedding_dim(),
                max_token_size=8192,
                func=embedding_func,
            ),
        )

        # Important: initialize storages in the child process
        # (supported in most LightRAG versions)
        init = getattr(rag, "initialize_storages", None)
        if callable(init):
            # initialize_storages is async; run via asyncio
            import asyncio
            asyncio.run(init())

        # Insert text (async)
        import asyncio
        asyncio.run(rag.ainsert(text))

        # Finalize (if present)
        fin = getattr(rag, "finalize_storages", None)
        if callable(fin):
            import asyncio
            asyncio.run(fin())

        # Basic sanity read
        docs_path = working_dir / "kv_store_full_docs.json"
        docs = None
        if docs_path.exists():
            docs = json.loads(docs_path.read_text(encoding="utf-8"))
        count = len(docs.keys()) if isinstance(docs, dict) else None

        conn.send({"ok": True, "full_doc_count": count})
    except Exception:
        conn.send(
            {
                "ok": False,
                "error": "ingest_worker_failed",
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _run_ingest_in_spawned_process(working_dir: Path, text: str) -> dict[str, Any]:
    """
    Spawn a fresh process to run the ingestion so LightRAG cannot share module globals.
    """
    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    p = ctx.Process(
        target=_ingest_worker_process,
        args=(child_conn, str(working_dir.resolve()), text),
        daemon=True,
    )
    p.start()
    result = parent_conn.recv()
    p.join(timeout=5)

    # If it’s still alive for some reason, kill it (don’t let it hang the server)
    if p.is_alive():
        p.terminate()
        p.join(timeout=2)

    return result


# -----------------------------
# Routes
# -----------------------------
@router.post("/ingest-staged")
async def ingest_staged(req: IngestStagedRequest) -> dict[str, Any]:
    """
    Digest a staged PDF into ./lightrag_cache/<doc_key>/ with TRUE clean slate.

    This uses a spawned subprocess for ingestion to avoid LightRAG process-global caches.
    """
    if not LIGHTRAG_AVAILABLE:
        raise HTTPException(status_code=500, detail="LightRAG not installed. Run: pip install lightrag-hku")

    _require_env()

    saved = (req.saved_name or "").strip()
    if not saved:
        raise HTTPException(status_code=400, detail="saved_name is required")

    pdf_path = _pdf_imports_dir() / saved
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"Source PDF not found: {saved}")

    doc_key = (req.doc_key or "").strip()
    if not doc_key:
        doc_key = _slugify(req.original_name or saved)

    working_dir = (_lightrag_root_dir() / doc_key).resolve()

    # Hard nuke the folder on disk first
    _nuke_working_dir(working_dir)

    # Extract text in main process
    text = _extract_text_from_pdf(pdf_path)
    if not text.strip():
        raise HTTPException(status_code=400, detail="PDF contains no extractable text")

    # Run ingestion in a FRESH process (the actual fix)
    result = _run_ingest_in_spawned_process(working_dir, text)
    if not result.get("ok"):
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Subprocess ingestion failed",
                "error": result.get("error"),
                "traceback": result.get("traceback"),
            },
        )

    # Confirm what’s on disk now
    docs_path = working_dir / "kv_store_full_docs.json"
    docs = _read_json_safe(docs_path)
    disk_count = len(docs.keys()) if isinstance(docs, dict) else None

    warning = None
    if isinstance(disk_count, int) and disk_count != 1:
        warning = f"Expected 1 doc in kv_store_full_docs.json, found {disk_count}."

    return {
        "ok": True,
        "message": "Fresh digestion complete (spawned-process isolation).",
        "doc_key": doc_key,
        "working_dir": str(working_dir),
        "char_count": len(text),
        "word_count": len(text.split()),
        "full_doc_count_worker": result.get("full_doc_count"),
        "full_doc_count_on_disk": disk_count,
        "warning": warning,
    }


@router.post("/sync-to-supabase")
def sync_to_supabase_endpoint(working_dir: str):
    wd = Path(working_dir)
    if not wd.exists():
        raise HTTPException(status_code=404, detail="Working directory not found.")
    return sync_lightrag_artifacts_to_supabase(working_dir=wd)


@router.get("/status")
def get_status(working_dir: str):
    wd = Path(working_dir)
    return {"exists": wd.exists(), "path": str(wd)}
