"""Chunking utilities.

Keep chunking deterministic so citations remain stable.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List
import re

@dataclass
class TextChunk:
    chunk_id: str
    text: str

def chunk_text(text: str, max_chars: int = 1500, overlap: int = 200) -> List[TextChunk]:
    """Simple character-based chunker with overlap.

    TODO: replace with token-aware chunking if needed.
    """
    cleaned = re.sub(r"\s+", " ", text).strip()
    chunks: List[TextChunk] = []
    start = 0
    i = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        chunk = cleaned[start:end]
        chunks.append(TextChunk(chunk_id=f"chunk_{i}", text=chunk))
        i += 1
        start = max(0, end - overlap)
        if end == len(cleaned):
            break
    return chunks
