"""
tests/test_api_dashboard.py

API test suite (unit + integration-ish) for all mounted routers.

Notes:
- Run with:  python -m pytest -q
- We avoid real external network calls (Grok / OpenAI / Supabase) by:
  - mocking GrokClient in /grok/test_grok
  - asserting deterministic validation failures (400) for endpoints that gate early
  - asserting deterministic "missing file" failures (500) for sync endpoints when working_dir is empty
  - using tmp_path + monkeypatch for filesystem isolation
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


# Import your FastAPI app
from server.main import app


# -----------------------------
# Fixtures
# -----------------------------
@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def tmp_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _make_minimal_pdf_bytes(text: str = "hello") -> bytes:
    """
    Create a tiny valid PDF in-memory using pypdf.
    (Keeps tests self-contained and avoids committing fixtures.)
    """
    from pypdf import PdfWriter

    writer = PdfWriter()
    # pypdf can add a blank page; text content isn't essential for stats endpoint
    writer.add_blank_page(width=72, height=72)

    out_path = Path(".") / "_tmp_test.pdf"
    with out_path.open("wb") as f:
        writer.write(f)

    data = out_path.read_bytes()
    out_path.unlink(missing_ok=True)
    return data


# -----------------------------
# Dashboard router tests
# -----------------------------
def test_dashboard_ping_ok(client: TestClient) -> None:
    r = client.get("/dashboard/ping")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("service") == "dashboard_router"


def test_dashboard_upload_pdf_success(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolate PDF_IMPORTS_DIR so the test never writes into your repo folders
    import_dir = tmp_path / "pdf_imports"
    monkeypatch.setenv("PDF_IMPORTS_DIR", str(import_dir))

    pdf_bytes = _make_minimal_pdf_bytes()
    files = {"file": ("test.pdf", pdf_bytes, "application/pdf")}

    r = client.post("/dashboard/upload-pdf", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["original_name"] == "test.pdf"
    assert body["status"] == "ready"
    assert body["bytes"] == len(pdf_bytes)

    saved_path = Path(body["saved_path"])
    assert saved_path.exists()
    assert saved_path.parent.resolve() == import_dir.resolve()
    assert saved_path.suffix.lower() == ".pdf"


def test_dashboard_upload_pdf_rejects_non_pdf(client: TestClient) -> None:
    files = {"file": ("not_a_pdf.txt", b"hello", "text/plain")}
    r = client.post("/dashboard/upload-pdf", files=files)
    assert r.status_code == 400
    assert "PDF" in r.json().get("detail", "")


def test_dashboard_upload_pdf_rejects_empty_file(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_IMPORTS_DIR", str(tmp_path / "pdf_imports"))
    files = {"file": ("empty.pdf", b"", "application/pdf")}
    r = client.post("/dashboard/upload-pdf", files=files)
    assert r.status_code == 400
    assert "Empty" in r.json().get("detail", "")


# -----------------------------
# Ingest router tests
# -----------------------------
def test_ingest_pdf_stats_no_pdfs_returns_friendly_payload(client: TestClient, tmp_cwd: Path) -> None:
    # working directory contains no PDFs
    r = client.get("/ingest/pdf-stats")
    assert r.status_code == 200
    body = r.json()
    assert body["pdf_count"] == 0
    assert body["pdfs"] == []
    assert "No PDFs found" in body.get("error", "")


def test_ingest_pdf_stats_counts_one_pdf(client: TestClient, tmp_cwd: Path) -> None:
    # create one pdf in cwd (the endpoint scans ".")
    pdf_path = tmp_cwd / "one.pdf"
    pdf_path.write_bytes(_make_minimal_pdf_bytes())

    r = client.get("/ingest/pdf-stats")
    assert r.status_code == 200
    body = r.json()
    assert body["pdf_count"] == 1
    assert isinstance(body["pdfs"], list)
    first = body["pdfs"][0]
    assert first["filename"] == "one.pdf"
    assert first["pages"] >= 1
    assert "word_count" in first
    assert "char_count" in first


# -----------------------------
# Grok router tests (mocked; no external network)
# -----------------------------
def test_grok_test_grok_smoke_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    /grok/test_grok calls GrokClient().chat_text(...) and returns its response.
    We patch GrokClient inside the router module to avoid network.
    """
    from server.routers import grok_router as grok_router_module

    class FakeGrokClient:
        def __init__(self) -> None:
            self.model = "fake-grok-model"

        async def chat_text(self, messages: list[dict[str, Any]], temperature: float = 0.0, max_tokens: int = 50) -> str:
            return "hello there friend pal"  # 5 words

    monkeypatch.setattr(grok_router_module, "GrokClient", FakeGrokClient)

    r = client.get("/grok/test_grok")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["model"] == "fake-grok-model"
    assert isinstance(body["response"], str)
    assert body["response"] == "hello there friend pal"


# -----------------------------
# LightRAG router tests (validation-first + deterministic failures)
# -----------------------------
def test_lightrag_query_rejects_empty_query(client: TestClient) -> None:
    # query endpoint validates before any env/key checks
    r = client.post("/lightrag/query", params={"query": "   "})
    assert r.status_code == 400
    assert "empty" in r.json().get("detail", "").lower()


def test_lightrag_ingest_pdf_rejects_non_pdf(client: TestClient) -> None:
    files = {"file": ("bad.txt", b"not a pdf", "text/plain")}
    r = client.post("/lightrag/ingest-pdf", files=files)
    assert r.status_code == 400
    assert "pdf" in r.json().get("detail", "").lower()


def test_lightrag_status_returns_ok_false_when_missing_keys(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure keys are absent so _get_lightrag fails and /status returns ok:false
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDINGS_API_KEY", raising=False)

    r = client.get("/lightrag/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "Missing" in body.get("error", "")


def test_lightrag_sync_to_supabase_missing_artifacts_returns_500(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Point LIGHTRAG_WORKING_DIR to an empty temp dir to force a deterministic failure
    wd = tmp_path / "empty_lightrag_cache"
    wd.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LIGHTRAG_WORKING_DIR", str(wd))

    r = client.post("/lightrag/sync-to-supabase")
    assert r.status_code == 500
    detail = r.json().get("detail", "")
    assert "Missing file" in detail


# -----------------------------
# Supabase router tests (no real Supabase calls)
# -----------------------------
def test_supabase_ping_ok(client: TestClient) -> None:
    r = client.get("/supabase/ping")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("service") == "supabase_router"


def test_supabase_sync_lightrag_missing_artifacts_returns_500(client: TestClient, tmp_path: Path) -> None:
    # Provide an empty working_dir explicitly
    wd = tmp_path / "empty_lightrag_cache"
    wd.mkdir(parents=True, exist_ok=True)

    r = client.post("/supabase/sync-lightrag", params={"working_dir": str(wd)})
    assert r.status_code == 500
    detail = r.json().get("detail", "")
    assert "Missing file" in detail
