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

import server.routers.supabase_router as supabase_router_mod

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

# -----------------------------
# Fakes for new endpoints (documents + RPC)
# -----------------------------
class _FakeResponse:
    def __init__(self, data: Any):
        self.data = data


class _FakeRpcCall:
    """
    supabase-py pattern: sb.rpc(...).execute()
    """
    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = rows

    def execute(self):
        return _FakeResponse(self._rows)


class _FakeTableQuery:
    def __init__(self, table_name: str, fake_db: Dict[str, List[Dict[str, Any]]]):
        self._table_name = table_name
        self._db = fake_db
        self._eq_filters: Dict[str, Any] = {}
        self._limit: Optional[int] = None
        self._range: Optional[tuple[int, int]] = None
        self._order_col: Optional[str] = None
        self._order_desc: bool = False

    def select(self, _cols: str):
        return self

    def order(self, col: str, desc: bool = False):
        self._order_col = col
        self._order_desc = bool(desc)
        return self

    def range(self, start: int, end: int):
        self._range = (int(start), int(end))
        return self

    def eq(self, col: str, value: Any):
        self._eq_filters[col] = value
        return self

    def limit(self, n: int):
        self._limit = int(n)
        return self

    def execute(self):
        rows = list(self._db.get(self._table_name, []))

        # apply eq filters
        for k, v in self._eq_filters.items():
            rows = [r for r in rows if r.get(k) == v]

        # apply order
        if self._order_col:
            rows.sort(key=lambda r: (r.get(self._order_col) is None, r.get(self._order_col)))
            if self._order_desc:
                rows.reverse()

        # apply range
        if self._range:
            s, e = self._range
            rows = rows[s : e + 1]

        # apply limit
        if self._limit is not None:
            rows = rows[: self._limit]

        return _FakeResponse(rows)


class _FakeSupabaseClient:
    def __init__(self, fake_db: Dict[str, List[Dict[str, Any]]], rpc_rows: List[Dict[str, Any]]):
        self._db = fake_db
        self._rpc_rows = rpc_rows
        self._rpc_calls: List[tuple[str, Dict[str, Any]]] = []

    def table(self, name: str):
        return _FakeTableQuery(name, self._db)

    def rpc(self, fn_name: str, payload: Dict[str, Any]):
        self._rpc_calls.append((fn_name, payload))
        return _FakeRpcCall(self._rpc_rows)

    @property
    def rpc_calls(self):
        return list(self._rpc_calls)


@pytest.fixture
def fake_supabase(monkeypatch):
    # minimal documents data
    fake_db = {
        "documents": [
            {
                "doc_id": "doc_1",
                "file_path": "pdf_imports/a.pdf",
                "created_at": "2026-02-01T00:00:00Z",
                "updated_at": "2026-02-01T00:00:00Z",
                "metadata": {"source": "pdf_imports/a.pdf"},
                "content": "FULL DOC (optional)",
            },
            {
                "doc_id": "doc_2",
                "file_path": "pdf_imports/b.pdf",
                "created_at": "2026-02-02T00:00:00Z",
                "updated_at": "2026-02-02T00:00:00Z",
                "metadata": {"source": "pdf_imports/b.pdf"},
                "content": "FULL DOC (optional)",
            },
        ]
    }

    # rows returned by match_chunks/match_chunks_multi
    rpc_rows = [
        {
            "chunk_id": "chunk_1",
            "doc_id": "doc_1",
            "chunk_order_index": 0,
            "file_path": "pdf_imports/a.pdf",
            "content": "Chunk content 1",
            "similarity": 0.88,
            "metadata": {"page": 1},
        },
        {
            "chunk_id": "chunk_2",
            "doc_id": "doc_1",
            "chunk_order_index": 1,
            "file_path": "pdf_imports/a.pdf",
            "content": "Chunk content 2",
            "similarity": 0.84,
            "metadata": {"page": 2},
        },
    ]

    sb = _FakeSupabaseClient(fake_db=fake_db, rpc_rows=rpc_rows)

    # Patch supabase client getter to return our fake
    monkeypatch.setattr(supabase_router_mod, "_get_supabase_client", lambda: sb)

    # Patch embeddings to avoid network
    async def _fake_embed_query(_text: str) -> List[float]:
        return [0.0, 0.1, 0.2]

    monkeypatch.setattr(supabase_router_mod, "_embed_query", _fake_embed_query)

    return sb


# -----------------------------
# New endpoint tests
# -----------------------------
def test_supabase_list_documents_ok(client: TestClient, fake_supabase: _FakeSupabaseClient) -> None:
    r = client.get("/supabase/documents")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["count"] == 2
    assert isinstance(body["documents"], list)
    assert {d["doc_id"] for d in body["documents"]} == {"doc_1", "doc_2"}


def test_supabase_get_document_ok(client: TestClient, fake_supabase: _FakeSupabaseClient) -> None:
    r = client.get("/supabase/documents/doc_1")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["document"]["doc_id"] == "doc_1"
    assert "file_path" in body["document"]


def test_supabase_get_document_404(client: TestClient, fake_supabase: _FakeSupabaseClient) -> None:
    r = client.get("/supabase/documents/does_not_exist")
    assert r.status_code == 404
    detail = r.json().get("detail", "")
    assert "Document not found" in detail


def test_supabase_retrieve_ok_calls_rpc(client: TestClient, fake_supabase: _FakeSupabaseClient) -> None:
    payload = {"doc_id": "doc_1", "query": "What is this about?", "top_k": 2}
    r = client.post("/supabase/retrieve", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["doc_id"] == "doc_1"
    assert body["top_k"] == 2
    assert isinstance(body["chunks"], list)
    assert len(body["chunks"]) == 2

    # Ensure RPC was called with expected function + keys
    calls = fake_supabase.rpc_calls
    assert len(calls) == 1
    fn_name, rpc_payload = calls[0]
    assert fn_name == "match_chunks"
    assert rpc_payload["match_doc_id"] == "doc_1"
    assert rpc_payload["match_count"] == 2
    assert isinstance(rpc_payload["query_embedding"], list)


def test_supabase_retrieve_rejects_empty_query(client: TestClient, fake_supabase: _FakeSupabaseClient) -> None:
    payload = {"doc_id": "doc_1", "query": "   ", "top_k": 3}
    r = client.post("/supabase/retrieve", json=payload)
    assert r.status_code == 400
    assert "Query cannot be empty" in (r.json().get("detail") or "")


def test_supabase_retrieve_passes_min_similarity_when_set(client: TestClient, fake_supabase: _FakeSupabaseClient) -> None:
    payload = {"doc_id": "doc_1", "query": "test", "top_k": 5, "min_similarity": 0.77}
    r = client.post("/supabase/retrieve", json=payload)
    assert r.status_code == 200

    calls = fake_supabase.rpc_calls
    assert len(calls) == 1
    fn_name, rpc_payload = calls[0]
    assert fn_name == "match_chunks"
    assert "min_similarity" in rpc_payload
    assert float(rpc_payload["min_similarity"]) == 0.77


def test_supabase_retrieve_multi_ok_calls_rpc(client: TestClient, fake_supabase: _FakeSupabaseClient) -> None:
    payload = {"doc_ids": ["doc_1", "doc_2"], "query": "hello", "top_k": 4}
    r = client.post("/supabase/retrieve-multi", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["doc_ids"] == ["doc_1", "doc_2"]
    assert body["top_k"] == 4
    assert isinstance(body["chunks"], list)

    calls = fake_supabase.rpc_calls
    assert len(calls) == 1
    fn_name, rpc_payload = calls[0]
    assert fn_name == "match_chunks_multi"
    assert rpc_payload["match_doc_ids"] == ["doc_1", "doc_2"]
    assert rpc_payload["match_count"] == 4
    assert isinstance(rpc_payload["query_embedding"], list)


def test_supabase_retrieve_multi_rejects_empty_query(client: TestClient, fake_supabase: _FakeSupabaseClient) -> None:
    # NOTE: Your actual response is 422 (schema validation) per your test output.
    payload = {"doc_ids": ["doc_1"], "query": "", "top_k": 4}
    r = client.post("/supabase/retrieve-multi", json=payload)
    assert r.status_code == 422
