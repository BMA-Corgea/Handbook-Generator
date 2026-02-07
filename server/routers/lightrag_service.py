"""
lightrag_service.py (GIMS-style router module)

This file owns:
- The router (API endpoints)
- The small subroutines those endpoints need

Milestone endpoint (today):
1) /lightrag/dump-pdf-json
   - scans local PDFs from project root (same as ingest_service.py right now)
   - extracts text
   - writes a JSON file into ./outputs/
   - returns output path + basic stats

Later (next milestone):
- chunk text
- embed + store in Supabase (pgvector)
- LightRAG indexing + query endpoints
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
from pathlib import Path
from typing import Any
import json
import re
from datetime import datetime

load_dotenv()

router = APIRouter(prefix="/lightrag", tags=["lightrag"])


# -----------------------------
# Helpers (subroutines)
# -----------------------------
def _project_root() -> Path:
    """
    Assumes uvicorn is launched from project root.
    (Matches your ingest_service assumption: pdf_dir=".")
    """
    return Path(".")


def _outputs_dir() -> Path:
    out = _project_root() / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    return out


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
    words = re.findall(r"\b\w+\b", text)
    return len(words)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# -----------------------------
# Routes
# -----------------------------
@router.get("/dump-pdf-json")
def dump_pdf_json() -> dict[str, Any]:
    """
    Milestone endpoint:
    - scans project root for *.pdf (same behavior as ingest_service currently)
    - extracts text + stats
    - writes JSON to ./outputs/
    """
    pdf_dir = "."
    pdf_paths = _scan_pdf_paths(pdf_dir)

    if not pdf_paths:
        folder = str(Path(pdf_dir))
        return {
            "ok": False,
            "folder": folder,
            "pdf_count": 0,
            "pdfs": [],
            "error": f"No PDFs found. Put PDFs in '{folder}/' (relative to project root).",
        }

    pdfs: list[dict[str, Any]] = []
    for pdf_path in pdf_paths:
        try:
            pages, text = _extract_text_pypdf(pdf_path)
            pdfs.append(
                {
                    "filename": pdf_path.name,
                    "pages": pages,
                    "word_count": _word_count(text),
                    "char_count": len(text),
                    # keep text for now since this is a milestone dump;
                    # later we’ll store chunks/embeddings, not raw text.
                    "text": text,
                }
            )
        except Exception as e:
            pdfs.append({"filename": pdf_path.name, "error": repr(e)})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _outputs_dir() / f"lightrag_pdf_dump_{timestamp}.json"

    payload: dict[str, Any] = {
        "created_at": datetime.now().isoformat(),
        "folder": str(Path(pdf_dir)),
        "pdf_count": len(pdfs),
        "pdfs": pdfs,
    }

    try:
        _write_json(out_path, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed writing {out_path}: {e}")

    return {
        "ok": True,
        "output_file": str(out_path),
        "pdf_count": len(pdfs),
        "filenames": [p.get("filename") for p in pdfs],
    }
