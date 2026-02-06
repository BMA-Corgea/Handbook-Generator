"""Output storage helper.

Saves generated handbook artifacts to ./outputs/handbook for easy demoing.
"""

from __future__ import annotations
from pathlib import Path
import re
import datetime

OUT_DIR = Path(__file__).resolve().parents[2] / "outputs" / "handbook"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def _safe(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9\-_ ]+", "", name).strip().replace(" ", "_")
    return name[:80] or "handbook"

def save_handbook_markdown(*, document_id: str, title: str, markdown: str) -> Path:
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = f"{ts}_{_safe(title)}_{document_id[:8]}.md"
    path = OUT_DIR / fname
    path.write_text(markdown, encoding="utf-8")
    return path
