# Handbook Generator  
**FastAPI · React · Supabase · LightRAG · Grok**

This repository implements an end-to-end **AI handbook generation system** built to satisfy an AI Engineering Assignment. The system supports PDF upload, knowledge ingestion, grounded chat, and long-form handbook generation (20,000+ words) using a modern RAG architecture.

At a high level:

- **Frontend:** Lightweight React dashboard  
- **Backend:** Python FastAPI server with modular routers  
- **RAG / chunking:** LightRAG  
- **Vector storage:** Supabase (Postgres + pgvector)  
- **LLM (chat + writing):** Grok  
- **LLM (ingestion / embeddings):** ChatGPT (via OpenAI-compatible APIs)

The design prioritizes **clarity, isolation, and traceability** over novelty.

---

## Assignment alignment

The assignment required:

- PDF upload  
- Knowledge graph / indexing via LightRAG  
- Chat interface grounded in uploaded documents  
- Ability to generate a **20,000+ word handbook** through chat  
- Use of FastAPI (backend), React (frontend), Supabase, and Grok  

All requirements are met directly and explicitly.

---

## System architecture

### Backend (FastAPI)

The FastAPI server is the backbone of the system. It:

- exposes all ingestion, retrieval, and generation APIs
- coordinates LightRAG ingestion and Supabase sync
- serves the React frontend as static assets
- enforces server-side access to secrets (Supabase service key, LLM keys)

Routers are mounted in `server/main.py`, keeping responsibilities isolated and explicit.

### Frontend (React)

The React UI is intentionally minimal and unstyled beyond what is needed to:

- upload PDFs
- trigger ingestion
- select documents
- run chat queries
- request long-form handbook generation

The assignment explicitly deprioritizes UI complexity; the focus is on backend correctness and data flow.

---

## Data & RAG pipeline

End-to-end flow:

1. **Upload**
   - PDF uploaded via the dashboard
   - Saved to disk in `./pdf_imports/`

2. **Ingestion**
   - LightRAG processes the staged PDF
   - Artifacts are written to a **per-document working directory**
     ```
     ./lightrag_cache/<doc_key>/
     ```

3. **Sync**
   - Chunks, embeddings, and metadata are pushed into Supabase
   - Stored in Postgres tables with pgvector embeddings

4. **Retrieval**
   - Supabase RPC functions perform vector similarity search

5. **Generation**
   - Grok produces grounded chat answers
   - Grok produces long-form handbook output using a LongWriter-style loop

---

## Router overview

Each major capability lives in its own router:

- `/dashboard`  
  Handles PDF upload and staging (no ingestion).

- `/lightrag`  
  Runs per-PDF LightRAG ingestion in isolated working directories.

- `/supabase`  
  Syncs artifacts to Supabase and performs vector retrieval via RPC.

- `/grok`  
  Grounded RAG chat with relevance gating and citation enforcement.

- `/longwrite`  
  Sequential long-form handbook generation (outline → sections → 20k+ words).

- `/ingest`  
  Legacy / scaffolding endpoints used earlier in development.

See `WHAT_EACH_FILE_DOES.md` for detailed router-level documentation.

---

## Setup

### Python environment

Recommended Python version: **3.12** (3.13 still works)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Supabase

Create a Supabase project with Postgres + pgvector enabled.

Run the SQL in `sql_tables.md` to create:

- `documents`
- `chunks`
- vector indexes
- retrieval RPC functions

### Environment variables

Create a `.env` file in the project root.

Variables include:

- Grok API configuration
- OpenAI-compatible API keys (for LightRAG ingestion & embeddings)
- Supabase URL and service role key
- LightRAG working directory

See `env_variables.md` for the complete list.

### Run the server

```bash
uvicorn server.main:app --reload
```

- UI: http://127.0.0.1:8000/
- API docs: http://127.0.0.1:8000/docs

---

## Testing

Tests are run using:

```bash
python -m pytest -vv -rA
```

Pytest is included in `requirements.txt`.

---

## AI-assisted development approach

This project was built with intentional use of AI tooling, as encouraged by the assignment.

**ChatGPT (primary)**
- architectural planning
- router decomposition
- LightRAG ingestion logic
- test scaffolding and refactors

**Claude & Gemini**
- cross-checking design decisions
- alternate reasoning paths for bugs
- prompt and flow validation

**Grok**
- production model for grounded chat
- production model for handbook generation

AI tools were used as accelerators, not substitutes: all functionality was validated through execution, database inspection, and retrieval verification.

---

## Design notes

### Per-document ingestion isolation

Each PDF is ingested into its own LightRAG working directory. This avoids global state bleed, makes debugging trivial, and guarantees document-level traceability.

### Server-side secret handling

Supabase service keys and LLM credentials never touch the frontend. The React UI only communicates with FastAPI.

### Fail-closed RAG behavior

If retrieval confidence is low, chat endpoints refuse to answer rather than hallucinate.

---

## Summary

This project demonstrates:

- clean FastAPI architecture
- disciplined router boundaries
- practical RAG design
- long-form AI generation at scale
- responsible use of multiple LLMs in a single system