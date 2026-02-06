"""PDF extraction utilities.

Swap between pypdf and pdfplumber as needed. Keep this pure and testable.
"""

from __future__ import annotations
from typing import Tuple

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract text from a PDF file in memory.

    TODO: implement robust extraction (pdfplumber is often better for layout; pypdf is simpler).
    """
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for p in reader.pages:
            pages.append(p.extract_text() or "")
        return "\n".join(pages).strip()
    except Exception:
        # Fallback approach can be added here (pdfplumber).
        return ""
