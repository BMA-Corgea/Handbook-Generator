"""
tests/test_api_dashboard.py

Comprehensive API test suite for Lunar-Reader.
Covers:
1. Dashboard Router (PDF Uploads)
2. Ingest Router (Local PDF Stats)
3. Grok Router (Smoke Tests)
4. LightRAG Router (Staged Ingestion, Sync, Status)
5. Supabase Router (Sync Logic, Retrieval, Document Listing)

Run with: python -m pytest tests/test_api_dashboard.py
"""

from __future__ import annotations

import os
import json
import base64
import zlib
import pytest
import struct
from pathlib import Path
from typing import Any, List, Dict
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Import the main app
from server.main import app

# Import router modules to patch dependencies
import server.routers.supabase_router as supabase_router_mod
import server.routers.lightrag_service as lightrag_service_mod
import server.routers.grok_router as grok_router_mod

# -----------------------------------------------------------------------------
# 1. HELPER CLASSES (Mocks)
# -----------------------------------------------------------------------------

class FakeSupabaseResponse:
    def __init__(self, data: Any):
        self.data = data

class FakeSupabaseQuery:
    """Mocks the chainable Supabase query builder: .table().select().eq()..."""
    def __init__(self, data: List[Dict[str, Any]]):
        self._data = data
        self._filtered_data = data

    def select(self, cols: str):
        return self

    def upsert(self, data: Any, on_conflict: str = None):
        if isinstance(data, list):
            self._data.extend(data)
        else:
            self._data.append(data)
        self._filtered_data = self._data
        return self

    def eq(self, col: str, val: Any):
        self._filtered_data = [x for x in self._filtered_data if x.get(col) == val]
        return self

    def limit(self, n: int):
        self._filtered_data = self._filtered_data[:n]
        return self
    
    def order(self, col: str, desc: bool=False):
        self._filtered_data.sort(key=lambda x: x.get(col, ""), reverse=desc)
        return self

    def range(self, start: int, end: int):
        self._filtered_data = self._filtered_data[start:end+1]
        return self

    def execute(self):
        return FakeSupabaseResponse(self._filtered_data)

class FakeSupabaseClient:
    """Mocks the Supabase Client entry point."""
    def __init__(self):
        self.db = {
            "documents": [],
            "chunks": []
        }
        self.rpc_calls = []

    def table(self, name: str):
        if name not in self.db:
            self.db[name] = []
        return FakeSupabaseQuery(self.db[name])

    def rpc(self, fn_name: str, params: Dict[str, Any]):
        self.rpc_calls.append((fn_name, params))
        # Return dummy data for retrieval RPCs
        if "match" in fn_name:
            return FakeSupabaseQuery([
                {
                    "chunk_id": "ch_1", 
                    "doc_id": "doc_1", 
                    "title": "Doc Title",
                    "content": "Fake content", 
                    "similarity": 0.9,
                    "metadata": {"page": 1}
                }
            ])
        return FakeSupabaseQuery([])

class FakeGrokClient:
    def __init__(self):
        self.model = "grok-fake"
    
    async def chat_text(self, messages, temperature=0.0, max_tokens=50):
        return "I am a mocked Grok response."

class FakeLightRAG:
    """Mocks the heavy LightRAG class."""
    def __init__(self, working_dir, **kwargs):
        self.working_dir = working_dir
    
    async def initialize_storages(self):
        pass
    
    async def ainsert(self, text):
        pass
    
    async def aquery(self, query, param):
        return "Mocked RAG answer"

# -----------------------------------------------------------------------------
# 2. FIXTURES
# -----------------------------------------------------------------------------

@pytest.fixture
def client() -> TestClient:
    return TestClient(app)

@pytest.fixture
def mock_fs(tmp_path, monkeypatch):
    """Sets up temp directories for PDF imports and LightRAG cache."""
    pdf_dir = tmp_path / "pdf_imports"
    pdf_dir.mkdir()
    
    rag_dir = tmp_path / "lightrag_cache"
    rag_dir.mkdir()
    
    # Crucial: Ensure the service modules pick up these paths
    monkeypatch.setenv("PDF_IMPORTS_DIR", str(pdf_dir))
    monkeypatch.setenv("LIGHTRAG_WORKING_DIR", str(rag_dir))
    
    return {"pdf": pdf_dir, "rag": rag_dir}

@pytest.fixture
def mock_supabase(monkeypatch):
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr(supabase_router_mod, "_get_supabase_client", lambda: fake_client)
    
    # Fix: Mock _embed_query with an ASYNC function
    async def fake_embed(text: str):
        return [0.1] * 1536
    
    monkeypatch.setattr(supabase_router_mod, "_embed_query", fake_embed)
    return fake_client

@pytest.fixture
def mock_lightrag(monkeypatch):
    monkeypatch.setattr(lightrag_service_mod, "LightRAG", FakeLightRAG)
    monkeypatch.setattr(lightrag_service_mod, "LIGHTRAG_AVAILABLE", True)
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("EMBEDDINGS_API_KEY", "fake-key")

# -----------------------------------------------------------------------------
# 3. TESTS: Dashboard Router (PDF Uploads)
# -----------------------------------------------------------------------------

def test_dashboard_ping(client):
    response = client.get("/dashboard/ping")
    assert response.status_code == 200
    assert response.json()["ok"] is True

def test_dashboard_upload_pdf_success(client, mock_fs):
    file_content = b"%PDF-1.4 mock pdf content"
    files = {"file": ("test.pdf", file_content, "application/pdf")}
    
    response = client.post("/dashboard/upload-pdf", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["original_name"] == "test.pdf"
    
    saved_path = Path(data["saved_path"])
    assert saved_path.exists()
    assert saved_path.read_bytes() == file_content

def test_dashboard_upload_invalid_file(client, mock_fs):
    files = {"file": ("test.txt", b"text content", "text/plain")}
    response = client.post("/dashboard/upload-pdf", files=files)
    assert response.status_code == 400
    assert "must be a PDF" in response.json()["detail"]

# -----------------------------------------------------------------------------
# 4. TESTS: Ingest Router (Local Stats)
# -----------------------------------------------------------------------------

def test_ingest_pdf_stats_empty(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path) 
    response = client.get("/ingest/pdf-stats")
    assert response.status_code == 200
    assert response.json()["pdf_count"] == 0

def test_ingest_pdf_stats_with_files(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4 content")
    
    with patch("server.routers.ingest_service._extract_text_pypdf", return_value=(5, "word " * 10)):
        response = client.get("/ingest/pdf-stats")
        assert response.status_code == 200
        data = response.json()
        assert data["pdf_count"] == 1
        assert data["pdfs"][0]["filename"] == "doc.pdf"

# -----------------------------------------------------------------------------
# 5. TESTS: Grok Router
# -----------------------------------------------------------------------------

def test_grok_smoke_test(client, monkeypatch):
    monkeypatch.setattr(grok_router_mod, "GrokClient", FakeGrokClient)
    response = client.get("/grok/test_grok")
    assert response.status_code == 200
    assert response.json()["response"] == "I am a mocked Grok response."

# -----------------------------------------------------------------------------
# 6. TESTS: LightRAG Router (Staged Ingestion)
# -----------------------------------------------------------------------------

def test_ingest_staged_success(client, mock_fs, mock_lightrag):
    """Tests the /lightrag/ingest-staged endpoint."""
    saved_name = "test_123.pdf"
    (mock_fs["pdf"] / saved_name).write_bytes(b"%PDF-1.4...")
    
    with patch("server.routers.lightrag_service._extract_text_from_pdf", return_value="Extracted text"):
        payload = {
            "saved_name": saved_name,
            "original_name": "My Resume.pdf",
            "doc_key": "my-resume"
        }
        response = client.post("/lightrag/ingest-staged", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["doc_key"] == "my-resume"
        assert data["ok"] is True
        
        expected_wd = mock_fs["rag"] / "my-resume"
        assert expected_wd.exists()

def test_ingest_staged_missing_file(client, mock_fs):
    payload = {"saved_name": "missing.pdf"}
    response = client.post("/lightrag/ingest-staged", json=payload)
    assert response.status_code == 404

def test_lightrag_status(client, mock_fs, mock_lightrag):
    wd = mock_fs["rag"] / "my-resume"
    wd.mkdir()
    (wd / "vdb_chunks.json").touch()

    response = client.get(f"/lightrag/status?working_dir={str(wd)}")
    assert response.status_code == 200
    data = response.json()

    # New LightRAG /status contract: minimal shape
    assert data["exists"] is True
    assert Path(data["path"]).resolve() == wd.resolve()

    # If you still want "vdb_chunks exists" coverage, test the filesystem directly
    assert (wd / "vdb_chunks.json").exists() is True
    assert (wd / "kv_store_full_docs.json").exists() is False
    
# -----------------------------------------------------------------------------
# 7. TESTS: Supabase Router (Sync & Retrieval)
# -----------------------------------------------------------------------------

def create_mock_lightrag_artifacts(wd: Path, doc_key: str):
    """Helper to write valid JSON artifacts for Supabase sync test."""
    wd.mkdir(parents=True, exist_ok=True)
    
    # 1. Create a valid float16 byte stream for dimension 2 (simple test)
    # LightRAG logic: vector = base64(zlib(float16_bytes))
    # Using dim=2 to make it easy.
    import numpy as np
    
    # Create array of 2 float16s
    arr = np.array([0.1, 0.2], dtype=np.float16)
    compressed = zlib.compress(arr.tobytes())
    vec_b64 = base64.b64encode(compressed).decode("utf-8")
    
    # Docs
    (wd / "kv_store_full_docs.json").write_text(json.dumps({
        "doc_1": {
            "content": "Full text",
            "file_path": "unknown_source", 
            "create_time": 1000,
            "update_time": 1000,
            "metadata": {"source": "unknown_source"}
        }
    }))
    
    # Chunks
    (wd / "kv_store_text_chunks.json").write_text(json.dumps({
        "chunk_1": {
            "full_doc_id": "doc_1",
            "content": "Chunk text",
            "tokens": 10,
            "create_time": 1000,
            "update_time": 1000,
            "metadata": {}
        }
    }))
    
    # VDB
    (wd / "vdb_chunks.json").write_text(json.dumps({
        "embedding_dim": 2, # Matching our tiny vector above
        "data": [
            {
                "__id__": "chunk_1",
                "vector": vec_b64
            }
        ]
    }))

def test_supabase_sync_unknown_source_fix(client, mock_fs, mock_supabase):
    """
    CRITICAL: Validates that 'unknown_source' is replaced by 'doc_key'
    """
    doc_key = "clean-folder-name"
    wd = mock_fs["rag"] / doc_key
    create_mock_lightrag_artifacts(wd, doc_key)
    
    # We must patch the router's dim retrieval to accept our test dim of 2
    # otherwise it might try to default to 1536 and fail validation
    with patch.dict(os.environ, {"EMBEDDINGS_DIM": "2"}):
        response = client.post(
            "/supabase/sync-lightrag", 
            params={"doc_key": doc_key}
        )
    
    assert response.status_code == 200
    
    # Inspect what was sent to Supabase "documents" table
    docs_upserted = mock_supabase.db["documents"]
    assert len(docs_upserted) == 1
    doc = docs_upserted[0]
    
    # Assertions for the fix
    assert doc["title"] == "clean-folder-name"
    assert doc["metadata"]["doc_key"] == "clean-folder-name"

def test_supabase_retrieve_endpoint(client, mock_supabase):
    payload = {
        "doc_id": "doc_1",
        "query": "test query",
        "top_k": 3
    }
    response = client.post("/supabase/retrieve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["chunks"]) == 1
    
    # Verify the RPC call
    assert len(mock_supabase.rpc_calls) == 1
    fn_name, params = mock_supabase.rpc_calls[0]
    assert fn_name == "match_chunks"
    assert params["match_doc_id"] == "doc_1"

def test_supabase_get_document(client, mock_supabase):
    mock_supabase.db["documents"] = [{
        "doc_id": "xyz", 
        "title": "My Doc", 
        "created_at": "2023-01-01"
    }]
    
    response = client.get("/supabase/documents/xyz")
    assert response.status_code == 200
    assert response.json()["document"]["title"] == "My Doc"

def test_supabase_get_document_404(client, mock_supabase):
    response = client.get("/supabase/documents/non_existent")
    assert response.status_code == 404

# -----------------------------------------------------------------------------
# 8. TESTS: Longwrite Router (Handbook Generation)
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_grok_longwrite(monkeypatch):
    """Mock Grok client for longwrite tests."""
    async def fake_chat_text(messages, temperature=0.0, max_tokens=1600):
        # Return different responses based on system prompt
        sys_content = messages[0].get("content", "") if messages else ""
        
        if "outline" in sys_content.lower():
            return (
                "Section 1: Introduction (~800 words)\n"
                "Section 2: Core Concepts (~850 words)\n"
                "Section 3: Practical Applications (~900 words)\n"
            )
        else:
            # Writing section content
            return "This is mocked section content. " * 50  # ~350 words
    
    fake_client = FakeGrokClient()
    fake_client.chat_text = fake_chat_text
    
    import server.routers.longwrite_router as longwrite_mod
    monkeypatch.setattr(longwrite_mod, "GrokClient", lambda: fake_client)
    return fake_client

@pytest.fixture
def mock_longwrite_retrieval(monkeypatch):
    """Mock the retrieval calls in longwrite router."""
    import server.routers.longwrite_router as longwrite_mod
    
    async def fake_retrieve_single(doc_id, query, top_k, min_similarity):
        return {
            "chunks": [
                {
                    "chunk_id": f"ch_{i}",
                    "doc_id": doc_id,
                    "title": "Test Document",
                    "content": f"Mock content for query: {query[:30]}",
                    "similarity": 0.85,
                    "chunk_order_index": i,
                    "file_path": "test.pdf"
                }
                for i in range(min(top_k, 5))
            ]
        }
    
    async def fake_retrieve_multi(doc_ids, query, top_k, min_similarity):
        all_chunks = []
        for doc_id in doc_ids[:2]:  # Limit to 2 docs for testing
            result = await fake_retrieve_single(doc_id, query, top_k // len(doc_ids), min_similarity)
            all_chunks.extend(result["chunks"])
        return {"chunks": all_chunks}
    
    monkeypatch.setattr(longwrite_mod, "_retrieve_single", fake_retrieve_single)
    monkeypatch.setattr(longwrite_mod, "_retrieve_multi", fake_retrieve_multi)

def test_longwrite_ping(client):
    """Test the longwrite router ping endpoint."""
    response = client.get("/longwrite/ping")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["service"] == "longwrite_router"

def test_longwrite_handbook_missing_doc_scope(client):
    """Test that handbook endpoint requires doc_id or doc_ids."""
    payload = {
        "handbook_request": "Create a handbook"
    }
    response = client.post("/longwrite/handbook", json=payload)
    assert response.status_code == 400
    assert "doc_id or doc_ids" in response.json()["detail"]

def test_longwrite_handbook_both_doc_scopes(client):
    """Test that handbook endpoint rejects both doc_id and doc_ids."""
    payload = {
        "doc_id": "doc1",
        "doc_ids": ["doc2", "doc3"],
        "handbook_request": "Create a handbook"
    }
    response = client.post("/longwrite/handbook", json=payload)
    assert response.status_code == 400
    assert "not both" in response.json()["detail"]

def test_longwrite_handbook_single_doc_success(client, mock_grok_longwrite, mock_longwrite_retrieval):
    """Test successful handbook generation for a single document."""
    payload = {
        "doc_id": "test-doc-1",
        "handbook_request": "Create a comprehensive handbook about this document",
        "target_words": 2000,
        "min_section_words": 300,
        "max_section_words": 600,
        "max_sections": 3,
        "temperature": 0.2,
        "max_tokens": 800,
        "retrieve_top_k": 10
    }
    
    response = client.post("/longwrite/handbook", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is True
    assert data["model"] == "grok-fake"
    assert "Section 1" in data["outline"]
    assert "Section 2" in data["outline"]
    assert len(data["text"]) > 0
    assert len(data["used_chunks"]) > 0
    
    # Check diagnostics
    diag = data["diagnostics"]
    assert diag["sections_planned"] == 3
    assert diag["sections_written"] > 0
    assert diag["unbounded_context"] is True

def test_longwrite_handbook_multi_doc_success(client, mock_grok_longwrite, mock_longwrite_retrieval):
    """Test successful handbook generation for multiple documents."""
    payload = {
        "doc_ids": ["doc1", "doc2"],
        "handbook_request": "Create a handbook combining insights from these documents",
        "target_words": 1500,
        "min_section_words": 300,
        "max_section_words": 600,
        "max_sections": 3
    }
    
    response = client.post("/longwrite/handbook", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is True
    assert len(data["used_chunks"]) > 0
    assert data["diagnostics"]["retrieved_chunks"] > 0

def test_longwrite_handbook_empty_retrieval(client, mock_grok_longwrite, monkeypatch):
    """Test handbook generation when retrieval returns no chunks."""
    import server.routers.longwrite_router as longwrite_mod
    
    async def fake_empty_retrieve(*args, **kwargs):
        return {"chunks": []}
    
    monkeypatch.setattr(longwrite_mod, "_retrieve_single", fake_empty_retrieve)
    
    payload = {
        "doc_id": "empty-doc",
        "handbook_request": "Create a handbook"
    }
    
    response = client.post("/longwrite/handbook", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is True
    assert "No outline" in data["outline"]
    assert "no relevant content" in data["text"]
    assert len(data["used_chunks"]) == 0
    assert data["diagnostics"]["retrieved_chunks"] == 0

def test_longwrite_handbook_respects_target_words(client, mock_grok_longwrite, mock_longwrite_retrieval):
    """Test that handbook generation respects target word count."""
    payload = {
        "doc_id": "test-doc",
        "handbook_request": "Create a short handbook",
        "target_words": 1200,  # Minimum is 1000, so use 1200 for a low target
        "min_section_words": 200,
        "max_section_words": 400,
        "max_sections": 10
    }
    
    response = client.post("/longwrite/handbook", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    diag = data["diagnostics"]
    
    # Either: stops early due to word count, OR generates content
    # Our mock generates ~350 words per section, so it may complete all planned sections
    # The key is that it respects the target_words parameter
    assert diag["final_word_count"] > 0
    assert diag["target_words"] == 1200
    
    # Verify it doesn't wildly exceed the target (allow some overshoot)
    assert diag["final_word_count"] <= diag["target_words"] * 1.5

def test_longwrite_handbook_custom_parameters(client, mock_grok_longwrite, mock_longwrite_retrieval):
    """Test handbook generation with custom parameters."""
    payload = {
        "doc_id": "test-doc",
        "handbook_request": "Create a detailed technical handbook",
        "target_words": 5000,
        "min_section_words": 400,
        "max_section_words": 1000,
        "max_sections": 20,
        "temperature": 0.7,
        "max_tokens": 2000,
        "retrieve_top_k": 50,
        "min_similarity": 0.7
    }
    
    response = client.post("/longwrite/handbook", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is True
    
    diag = data["diagnostics"]
    assert diag["target_words"] == 5000
    assert diag["max_tokens"] == 2000
    assert diag["temperature"] == 0.7