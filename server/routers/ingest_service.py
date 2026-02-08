"""
ingest_service.py (GIMS-style router module)

This file owns:
- The router (API endpoints)
- The small subroutines those endpoints need

For now we implement two "milestone" endpoints:
1) /pdf-stats   -> read local PDFs from ./lunar-reader and return word counts

Later, this same module can expand to real ingestion:
- upload PDF
- extract text
- chunk
- embed + store in Supabase
- LightRAG indexing
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
from pathlib import Path
from typing import Any
import os
import re
import httpx

load_dotenv()

router = APIRouter(prefix="/ingest", tags=["ingest"])


# -----------------------------
# Helpers (subroutines)
# -----------------------------
def _scan_pdf_paths(pdf_dir: str) -> list[Path]:
    folder = Path(pdf_dir)
    if not folder.exists():
        return []
    return sorted(folder.glob("*.pdf"))


def _extract_text_pypdf(pdf_path: Path) -> tuple[int, str]:
    """
    Return (page_count, extracted_text) using pypdf.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    text = "\n".join([(p.extract_text() or "") for p in reader.pages])
    return len(reader.pages), text


def _word_count(text: str) -> int:
    """
    Simple word count: good enough for sanity.
    """
    words = re.findall(r"\b\w+\b", text)
    return len(words)


async def _grok_chat_once(user_text: str) -> dict[str, Any]:
    """
    Minimal Grok chat call using environment variables.
    """
    grok_api_key = os.getenv("GROK_API_KEY")
    grok_base_url = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1").rstrip("/")
    grok_model = os.getenv("GROK_MODEL", "grok-4")

    if not grok_api_key:
        raise HTTPException(500, "Missing GROK_API_KEY")
    if not grok_base_url:
        raise HTTPException(500, "Missing GROK_BASE_URL")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {grok_api_key}",
    }

    payload = {
        "model": grok_model,
        "messages": [{"role": "user", "content": user_text}],
        "stream": False,
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{grok_base_url}/chat/completions", json=payload, headers=headers)

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


# -----------------------------
# Routes
# -----------------------------
@router.get("/", include_in_schema=False)
def root():
    return {"message": "Handbook Generator API", "docs": "/docs"}


@router.get("/pdf-stats")
def pdf_stats():
    """
    Read-only sanity endpoint:
    - scans ./lunar-reader/*.pdf
    - extracts text
    - returns filename + page count + word count
    """
    pdf_dir = "."
    pdf_paths = _scan_pdf_paths(pdf_dir)

    if not pdf_paths:
        folder = str(Path(pdf_dir))
        # Friendly response instead of a hard error.
        return {
            "folder": folder,
            "pdf_count": 0,
            "pdfs": [],
            "error": f"No PDFs found. Put PDFs in '{folder}/' (relative to project root).",
        }

    results: list[dict[str, Any]] = []
    for pdf_path in pdf_paths:
        try:
            pages, text = _extract_text_pypdf(pdf_path)
            wc = _word_count(text)
            results.append(
                {
                    "filename": pdf_path.name,
                    "pages": pages,
                    "word_count": wc,
                    "char_count": len(text),
                }
            )
        except Exception as e:
            results.append({"filename": pdf_path.name, "error": repr(e)})

    return {"folder": str(Path(pdf_dir)), "pdf_count": len(results), "pdfs": results}
