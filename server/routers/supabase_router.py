"""
supabase_router.py

Purpose:
- Keep Supabase plumbing isolated from LightRAG logic.
- Provides a small API surface for:
  (A) syncing LightRAG on-disk artifacts into Supabase (pgvector)
  (B) retrieving doc lists + top-k chunks for Grok RAG

Updated for your new workflow:
- LightRAG digestion happens per-PDF into: ./lightrag_cache/<doc_key>/
- Supabase sync should target ONE such folder at a time.
- Adds helpers so the UI can discover “staged/digested” working dirs.

Env required:
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY
- EMBEDDINGS_API_KEY
- EMBEDDINGS_BASE_URL
- EMBEDDINGS_MODEL
- (optional) EMBEDDINGS_DIM
- (optional) LIGHTRAG_WORKING_DIR=./lightrag_cache
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from pathlib import Path
from typing import Any, Iterable
import os
import json
import base64
import zlib
from datetime import datetime

load_dotenv()

router = APIRouter(prefix="/supabase", tags=["supabase"])


# -----------------------------
# Models (API payloads)
# -----------------------------
class RetrieveRequest(BaseModel):
    doc_id: str = Field(..., description="The document id to scope retrieval to")
    query: str = Field(..., min_length=1, description="User question / search query")
    top_k: int = Field(8, ge=1, le=50)
    min_similarity: float | None = Field(
        default=None,
        description="Optional similarity cutoff (depends on your RPC; may be ignored).",
    )


class RetrieveMultiRequest(BaseModel):
    doc_ids: list[str] = Field(..., min_length=1, description="Document ids to scope retrieval to")
    query: str = Field(..., min_length=1)
    top_k: int = Field(8, ge=1, le=50)
    min_similarity: float | None = None


# -----------------------------
# Supabase client
# -----------------------------
def _get_supabase_client():
    try:
        from supabase import create_client  # type: ignore
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="supabase-py not installed. Run: pip install supabase",
        ) from e

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise HTTPException(
            status_code=500,
            detail="Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env",
        )
    return create_client(url, key)


# -----------------------------
# Embeddings (OpenAI-compatible)
# -----------------------------
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


async def _embed_query(text: str) -> list[float]:
    """
    Produce a single embedding vector (list[float]) for pgvector RPC calls.
    Uses OpenAI-compatible embeddings endpoint configured by EMBEDDINGS_* env vars.
    """
    import httpx

    base_url = os.getenv("EMBEDDINGS_BASE_URL", "https://api.openai.com/v1")
    api_key = os.getenv("EMBEDDINGS_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")
    timeout_s = float(os.getenv("EMBEDDINGS_TIMEOUT_SECONDS", "60"))

    if not api_key:
        raise HTTPException(status_code=500, detail="Missing EMBEDDINGS_API_KEY (or OPENAI_API_KEY) in .env")

    url = f"{base_url.rstrip('/')}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "input": [text]}

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        emb = data["data"][0]["embedding"]
        if not isinstance(emb, list):
            raise HTTPException(status_code=500, detail="Embeddings API returned an unexpected payload.")
        return [float(x) for x in emb]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=500, detail=f"Embeddings API error ({e.response.status_code}): {e.response.text}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embeddings API request failed: {str(e)}") from e


# -----------------------------
# LightRAG artifact readers
# -----------------------------
def _read_json(path: Path) -> Any:
    if not path.exists():
        raise HTTPException(status_code=500, detail=f"Missing file: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _epoch_to_iso(ts: int | float | None) -> str:
    if ts is None:
        return datetime.utcnow().isoformat() + "Z"
    try:
        return datetime.utcfromtimestamp(float(ts)).isoformat() + "Z"
    except Exception:
        return datetime.utcnow().isoformat() + "Z"


def _batched(items: list[dict[str, Any]], batch_size: int) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


# -----------------------------
# Working dir helpers (new dashboard flow)
# -----------------------------
def _lightrag_root_dir() -> Path:
    root = Path(os.getenv("LIGHTRAG_WORKING_DIR", "./lightrag_cache"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_working_dir(working_dir: str | None, doc_key: str | None) -> Path:
    """
    Accept either:
      - explicit working_dir (full path)
      - doc_key (subfolder under LIGHTRAG_WORKING_DIR)

    This lets the UI pass doc_key without worrying about paths.
    """
    if doc_key and str(doc_key).strip():
        return (_lightrag_root_dir() / str(doc_key).strip()).resolve()
    return Path(working_dir or os.getenv("LIGHTRAG_WORKING_DIR", "./lightrag_cache")).resolve()


def _is_valid_lightrag_artifact_dir(wd: Path) -> bool:
    required = [
        "vdb_chunks.json",
        "kv_store_full_docs.json",
        "kv_store_text_chunks.json",
    ]
    return wd.exists() and wd.is_dir() and all((wd / f).exists() for f in required)


# -----------------------------
# Title derivation
# -----------------------------
def _derive_title(doc_id: str, rec: dict[str, Any], *, fallback: str | None = None) -> str:
    # 1. Highest priority: The actual file name if it exists
    fp = rec.get("file_path")
    if isinstance(fp, str) and fp.strip() and "unknown_source" not in fp:
        return Path(fp).name

    # 2. Strongest fallback: Use the doc_key (the folder name like 'cheese-50-words')
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()

    # 3. Final safety: check metadata source
    meta = rec.get("metadata") or {}
    src = meta.get("source")
    if isinstance(src, str) and src.strip() and "unknown_source" not in src:
        return Path(src).name

    return doc_id


def _derive_file_path(rec: dict[str, Any], *, fallback: str | None = None) -> str | None:
    """
    Make file_path actually useful.

    Priority:
    1) rec.file_path
    2) rec.metadata.source
    3) provided fallback (e.g., saved_name, original_name, doc_key)
    """
    fp = rec.get("file_path")
    if isinstance(fp, str) and fp.strip():
        return fp.strip()

    meta = rec.get("metadata") or {}
    if isinstance(meta, dict):
        src = meta.get("source")
        if isinstance(src, str) and src.strip():
            return src.strip()

        # sometimes you may store this
        orig = meta.get("original_name")
        if isinstance(orig, str) and orig.strip():
            return orig.strip()

        saved = meta.get("saved_name")
        if isinstance(saved, str) and saved.strip():
            return saved.strip()

    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()

    return None


# -----------------------------
# Vector decoding (LightRAG format)
# -----------------------------
def _decode_lightrag_vector(vector_b64: str, dim: int) -> list[float]:
    """
    LightRAG stores embeddings as:
      base64( zlib( float16_bytes ) )

    Returns a pgvector-ready Python list[float] (float32).
    """
    try:
        import numpy as np  # type: ignore
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="numpy is required to decode LightRAG vectors. Run: pip install numpy",
        ) from e

    raw = base64.b64decode(vector_b64)
    buf = zlib.decompress(raw)
    arr = np.frombuffer(buf, dtype=np.float16)

    if int(arr.size) != int(dim):
        raise HTTPException(
            status_code=500,
            detail=f"Embedding dim mismatch: expected {dim}, got {arr.size}",
        )

    return arr.astype(np.float32).tolist()


# -----------------------------
# Core sync routine (callable from other routers)
# -----------------------------
def sync_lightrag_artifacts_to_supabase(
    *,
    working_dir: Path,
    batch_size: int = 200,
    store_doc_text: bool = True,
) -> dict[str, Any]:
    wd = working_dir.resolve()

    docs_path = wd / "kv_store_full_docs.json"
    chunks_path = wd / "kv_store_text_chunks.json"
    vdb_path = wd / "vdb_chunks.json"

    docs_kv = _read_json(docs_path)     # { doc_id: {...} }
    chunks_kv = _read_json(chunks_path) # { chunk_id: {...} }
    vdb = _read_json(vdb_path)          # { embedding_dim: 1536, data: [...] }

    dim = int(vdb.get("embedding_dim") or int(os.getenv("EMBEDDINGS_DIM", str(_get_embedding_dim()))))

    # Build chunk_id -> embedding list[float]
    emb_map: dict[str, list[float]] = {}
    for item in vdb.get("data", []):
        chunk_id = item.get("__id__")
        vec_b64 = item.get("vector")
        if chunk_id and vec_b64:
            emb_map[chunk_id] = _decode_lightrag_vector(vec_b64, dim)

    # Useful fallback for title/file_path when LightRAG didn't store them
    wd_fallback = wd.name  # doc_key folder name

    # Documents upsert payload
    doc_rows: list[dict[str, Any]] = []
    for doc_id, rec in docs_kv.items():
        title = _derive_title(doc_id, rec, fallback=wd_fallback)

        # Ensure metadata is a dict, and inject useful provenance (non-destructive)
        md = rec.get("metadata")
        if not isinstance(md, dict):
            md = {}
        # Ensure we don't carry over "unknown_source" strings in the merge
        md = {
            **md,
            "doc_key": wd_fallback,
            "lightrag": True,
            "create_time": rec.get("create_time"),
            "update_time": rec.get("update_time"),
        }
        
        # Overwrite problematic fields explicitly
        md["title"] = title 
        md["source"] = title # This ensures 'source' in JSON matches the title column

        file_path = _derive_file_path(rec, fallback=wd_fallback)

        doc_rows.append(
            {
                "doc_id": doc_id,
                "title": title,  # ✅ expects documents.title column in your SQL
                "file_path": file_path,
                "content": rec.get("content") if store_doc_text else None,
                "created_at": rec.get("created_at") or _epoch_to_iso(rec.get("create_time")),
                "updated_at": rec.get("updated_at") or _epoch_to_iso(rec.get("update_time")),
                "metadata": md,
            }
        )

    # Chunks upsert payload
    chunk_rows: list[dict[str, Any]] = []
    missing_embeddings = 0

    for chunk_id, rec in chunks_kv.items():
        emb = emb_map.get(chunk_id)
        if emb is None:
            missing_embeddings += 1
            continue

        md = rec.get("metadata")
        if not isinstance(md, dict):
            md = {}
        md = {
            **{
                "create_time": rec.get("create_time"),
                "update_time": rec.get("update_time"),
                "lightrag": True,
                "doc_key": wd_fallback,
            },
            **md,
        }

        chunk_rows.append(
            {
                "chunk_id": chunk_id,
                "doc_id": rec.get("full_doc_id"),
                "chunk_order_index": rec.get("chunk_order_index"),
                "file_path": rec.get("file_path") or md.get("source") or wd_fallback,
                "content": rec.get("content") or "",
                "tokens": rec.get("tokens"),
                "metadata": md,
                "embedding": emb,
                "created_at": rec.get("created_at") or _epoch_to_iso(rec.get("create_time")),
                "updated_at": rec.get("updated_at") or _epoch_to_iso(rec.get("update_time")),
            }
        )

    sb = _get_supabase_client()

    # Upsert documents first (FK)
    docs_upserted = 0
    for batch in _batched(doc_rows, batch_size):
        sb.table("documents").upsert(batch, on_conflict="doc_id").execute()
        docs_upserted += len(batch)

    chunks_upserted = 0
    for batch in _batched(chunk_rows, batch_size):
        sb.table("chunks").upsert(batch, on_conflict="chunk_id").execute()
        chunks_upserted += len(batch)

    return {
        "ok": True,
        "working_dir": str(wd),
        "embedding_dim": dim,
        "documents_total": len(doc_rows),
        "chunks_total": len(chunks_kv),
        "chunks_with_embeddings": len(chunk_rows),
        "chunks_missing_embeddings_skipped": missing_embeddings,
        "documents_upserted": docs_upserted,
        "chunks_upserted": chunks_upserted,
    }


# -----------------------------
# Retrieval helpers (pgvector RPC)
# -----------------------------
def _safe_execute_rpc(sb, fn_name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Runs a Supabase RPC function and returns rows (list[dict]).
    If the RPC is missing or fails, raise a clear HTTPException.
    """
    try:
        res = sb.rpc(fn_name, payload).execute()
        data = getattr(res, "data", None)
        if data is None:
            data = res.get("data") if isinstance(res, dict) else None
        if data is None:
            raise HTTPException(status_code=500, detail=f"Supabase RPC '{fn_name}' returned no data.")
        if not isinstance(data, list):
            raise HTTPException(status_code=500, detail=f"Supabase RPC '{fn_name}' returned non-list data.")
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Supabase RPC '{fn_name}' failed. "
                f"Make sure the SQL function exists and accepts the payload keys. Error: {str(e)}"
            ),
        ) from e


# -----------------------------
# Routes
# -----------------------------
@router.get("/ping")
def ping() -> dict[str, Any]:
    return {"ok": True, "service": "supabase_router"}


@router.get("/staged")
def list_staged(
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    Lists local, per-PDF LightRAG working dirs under LIGHTRAG_WORKING_DIR that look “ready”.

    This is for the new dashboard "LightRAG → Supabase" dropdown:
    user selects a doc_key (folder) to upload to Supabase.
    """
    root = _lightrag_root_dir()
    dirs = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
    ready = [p for p in dirs if _is_valid_lightrag_artifact_dir(p)]

    sliced = ready[offset : offset + limit]
    items = []
    for p in sliced:
        items.append(
            {
                "doc_key": p.name,
                "working_dir": str(p.resolve()),
                "ready": True,
                "files": {
                    "vdb_chunks.json": (p / "vdb_chunks.json").exists(),
                    "kv_store_full_docs.json": (p / "kv_store_full_docs.json").exists(),
                    "kv_store_text_chunks.json": (p / "kv_store_text_chunks.json").exists(),
                },
            }
        )

    return {"ok": True, "root": str(root.resolve()), "count": len(sliced), "staged": items}


@router.post("/sync-lightrag")
def sync_lightrag(
    working_dir: str | None = None,
    doc_key: str | None = Query(default=None, description="Optional: subfolder under LIGHTRAG_WORKING_DIR"),
    batch_size: int = Query(default=200, ge=1, le=1000),
    store_doc_text: bool = Query(default=True),
) -> dict[str, Any]:
    """
    Sync LightRAG artifacts (from ONE working dir) into Supabase tables.

    New workflow:
      - UI should pass doc_key=<folder name> OR working_dir=<full path>.
    """
    wd = _resolve_working_dir(working_dir, doc_key)
    if not _is_valid_lightrag_artifact_dir(wd):
        raise HTTPException(
            status_code=500,
            detail=f"working_dir does not look like a valid LightRAG artifact dir: {str(wd)}",
        )
    return sync_lightrag_artifacts_to_supabase(
        working_dir=wd,
        batch_size=batch_size,
        store_doc_text=store_doc_text,
    )


@router.get("/documents")
def list_documents(
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_content: bool = Query(default=False),
) -> dict[str, Any]:
    """
    List documents for the dashboard dropdown.
    """
    sb = _get_supabase_client()

    cols = "doc_id,title,file_path,created_at,updated_at,metadata"
    if include_content:
        cols += ",content"

    try:
        res = (
            sb.table("documents")
            .select(cols)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        data = getattr(res, "data", None)
        if data is None and isinstance(res, dict):
            data = res.get("data")
        return {"ok": True, "count": len(data or []), "documents": data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}") from e


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, include_content: bool = Query(default=False)) -> dict[str, Any]:
    """
    Fetch a single document record by doc_id.
    """
    sb = _get_supabase_client()
    cols = "doc_id,title,file_path,created_at,updated_at,metadata"
    if include_content:
        cols += ",content"

    try:
        res = sb.table("documents").select(cols).eq("doc_id", doc_id).limit(1).execute()
        data = getattr(res, "data", None)
        if data is None and isinstance(res, dict):
            data = res.get("data")
        if not data:
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
        return {"ok": True, "document": data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch document: {str(e)}") from e


@router.post("/retrieve")
async def retrieve_chunks(req: RetrieveRequest) -> dict[str, Any]:
    """
    Given doc_id + query, return top-k most similar chunks (pgvector).

    Requires a Supabase SQL RPC function named: match_chunks
    Payload keys:
      - query_embedding
      - match_doc_id
      - match_count (top_k)
      - (optional) min_similarity
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    sb = _get_supabase_client()
    query_embedding = await _embed_query(req.query)

    payload: dict[str, Any] = {
        "query_embedding": query_embedding,
        "match_doc_id": req.doc_id,
        "match_count": req.top_k,
    }
    if req.min_similarity is not None:
        payload["min_similarity"] = float(req.min_similarity)

    rows = _safe_execute_rpc(sb, "match_chunks", payload)

    chunks = []
    for r in rows:
        chunks.append(
            {
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "title": r.get("title"),
                "page": (r.get("metadata") or {}).get("page"),
                "chunk_order_index": r.get("chunk_order_index"),
                "file_path": r.get("file_path"),
                "content": r.get("content") or "",
                "similarity": r.get("similarity"),
                "metadata": r.get("metadata") or {},
            }
        )

    return {
        "ok": True,
        "doc_id": req.doc_id,
        "top_k": req.top_k,
        "chunks": chunks,
        "embedding_dim_expected": _get_embedding_dim(),
    }


@router.post("/retrieve-multi")
async def retrieve_chunks_multi(req: RetrieveMultiRequest) -> dict[str, Any]:
    """
    Multi-doc retrieval.

    Requires RPC: match_chunks_multi
    Payload keys:
      - query_embedding
      - match_doc_ids
      - match_count
      - (optional) min_similarity
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    sb = _get_supabase_client()
    query_embedding = await _embed_query(req.query)

    payload: dict[str, Any] = {
        "query_embedding": query_embedding,
        "match_doc_ids": req.doc_ids,
        "match_count": req.top_k,
    }
    if req.min_similarity is not None:
        payload["min_similarity"] = float(req.min_similarity)

    rows = _safe_execute_rpc(sb, "match_chunks_multi", payload)

    chunks = []
    for r in rows:
        chunks.append(
            {
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "title": r.get("title"),
                "page": (r.get("metadata") or {}).get("page"),
                "chunk_order_index": r.get("chunk_order_index"),
                "file_path": r.get("file_path"),
                "content": r.get("content") or "",
                "similarity": r.get("similarity"),
                "metadata": r.get("metadata") or {},
            }
        )

    return {
        "ok": True,
        "doc_ids": req.doc_ids,
        "top_k": req.top_k,
        "chunks": chunks,
        "embedding_dim_expected": _get_embedding_dim(),
    }
