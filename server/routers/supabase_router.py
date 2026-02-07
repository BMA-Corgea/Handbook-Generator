"""
supabase_router.py

Purpose:
- Keep Supabase plumbing isolated from LightRAG logic.
- Provides a small API surface for syncing LightRAG on-disk artifacts into Supabase (pgvector).

Minimal sync (Phase 1):
- documents  <- kv_store_full_docs.json
- chunks     <- kv_store_text_chunks.json + vdb_chunks.json (decoded embeddings)

Env required:
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY
- (optional) LIGHTRAG_WORKING_DIR=./lightrag_cache
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
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

    dim = int(vdb.get("embedding_dim") or int(os.getenv("EMBEDDINGS_DIM", "1536")))

    # Build chunk_id -> embedding list[float]
    emb_map: dict[str, list[float]] = {}
    for item in vdb.get("data", []):
        chunk_id = item.get("__id__")
        vec_b64 = item.get("vector")
        if chunk_id and vec_b64:
            emb_map[chunk_id] = _decode_lightrag_vector(vec_b64, dim)

    # Documents upsert payload
    doc_rows: list[dict[str, Any]] = []
    for doc_id, rec in docs_kv.items():
        doc_rows.append(
            {
                "doc_id": doc_id,
                "file_path": rec.get("file_path"),
                "content": rec.get("content") if store_doc_text else None,
                "created_at": rec.get("created_at") or _epoch_to_iso(rec.get("create_time")),
                "updated_at": rec.get("updated_at") or _epoch_to_iso(rec.get("update_time")),
                "metadata": rec.get("metadata") or {
                    "source": rec.get("file_path"),
                    "create_time": rec.get("create_time"),
                    "update_time": rec.get("update_time"),
                    "lightrag": True,
                },
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

        chunk_rows.append(
            {
                "chunk_id": chunk_id,
                "doc_id": rec.get("full_doc_id"),
                "chunk_order_index": rec.get("chunk_order_index"),
                "file_path": rec.get("file_path"),
                "content": rec.get("content") or "",
                "tokens": rec.get("tokens"),
                "metadata": rec.get("metadata") or {
                    "create_time": rec.get("create_time"),
                    "update_time": rec.get("update_time"),
                    "lightrag": True,
                },
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
# Routes
# -----------------------------
@router.get("/ping")
def ping() -> dict[str, Any]:
    return {"ok": True, "service": "supabase_router"}


@router.post("/sync-lightrag")
def sync_lightrag(
    working_dir: str | None = None,
    batch_size: int = Query(default=200, ge=1, le=1000),
    store_doc_text: bool = Query(default=True),
) -> dict[str, Any]:
    """
    Sync LightRAG artifacts (from working_dir) into Supabase tables.
    """
    wd = Path(working_dir or os.getenv("LIGHTRAG_WORKING_DIR", "./lightrag_cache"))
    return sync_lightrag_artifacts_to_supabase(
        working_dir=wd,
        batch_size=batch_size,
        store_doc_text=store_doc_text,
    )
