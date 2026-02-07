"""
server/routers/dashboard_router.py

Purpose:
- Accept PDF uploads from the dashboard UI
- Save them into ./pdf_imports/
- Return a small JSON payload the UI can display (and store locally)

Notes:
- This router intentionally does NOT ingest into LightRAG.
  It only stages PDFs on disk for the rest of your pipeline.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from dotenv import load_dotenv
from pathlib import Path
from typing import Any
from datetime import datetime
import os
import re

load_dotenv()

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _safe_filename(name: str) -> str:
    # keep it simple: letters/numbers/._- and spaces -> underscores
    name = name.strip().replace(" ", "_")
    name = re.sub(r"[^a-zA-Z0-9._-]+", "", name)
    return name or "upload.pdf"


def _unique_path(dirpath: Path, filename: str) -> Path:
    base = _safe_filename(filename)
    stem = Path(base).stem
    suffix = Path(base).suffix or ".pdf"
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    candidate = dirpath / f"{stem}_{ts}{suffix}"
    return candidate


@router.get("/ping")
def ping() -> dict[str, Any]:
    return {"ok": True, "service": "dashboard_router"}


@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    import_dir = Path(os.getenv("PDF_IMPORTS_DIR", "./pdf_imports")).resolve()
    import_dir.mkdir(parents=True, exist_ok=True)

    dest = _unique_path(import_dir, file.filename)

    try:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty file upload")

        dest.write_bytes(data)

        return {
            "ok": True,
            "original_name": file.filename,
            "saved_name": dest.name,
            "saved_path": str(dest),
            "bytes": len(data),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "ready",  # UI will render as "!"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save PDF: {str(e)}")
