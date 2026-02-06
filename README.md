# LunarTech Handbook Generator — FastAPI Scaffold

This is a **starter file structure** for the LunarTech AI Engineering Assignment:
- Upload PDFs → ingest/index with **LightRAG** + **Supabase (pgvector)**
- Chat with context grounded in uploaded PDFs
- Generate a **20,000+ word handbook** using LongWriter-style orchestration
- Use **Grok 4.1 via API** for all LLM calls

> This scaffold includes placeholders and clean interfaces so you can implement each integration step-by-step.

## Quick start

### 1) Create venv + install deps
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure env
Copy `.env.example` to `.env` and fill in values.

### 3) Run API
```bash
uvicorn server.main:app --reload
```

### 4) Run UI (Streamlit)
```bash
streamlit run ui/streamlit_app.py
```

## High-level Architecture

- `server/ingest/` — PDF extraction + chunking + embedding + storage + LightRAG indexing
- `server/retrieval/` — shared retrieval API used by BOTH chat and handbook workflows
- `server/workflows/chat/` — single-turn RAG answer generation
- `server/workflows/handbook/` — plan → iterative write loop to reach 20k+ words
- `ui/` — thin UI that calls the FastAPI endpoints

## Notes
- This scaffold is intentionally minimal and **not** a full working implementation.
- Replace the `TODO:` sections with your actual LightRAG + Supabase + Grok client code.
