# What each file/folder does (quick map)

## Root
- `README.md` — how to run + architecture overview
- `.env.example` — environment variables template (Grok + Supabase)
- `requirements.txt` — Python dependencies

## server/
- `server/main.py` — FastAPI app + router wiring
- `server/api/upload.py` — `/api/upload` PDF upload + kicks off ingestion
- `server/api/chat.py` — `/api/chat` RAG chat endpoint
- `server/api/handbook.py` — `/api/handbook` handbook generation endpoint

### server/services/
- `pdf_service.py` — extract text from PDF bytes
- `chunking_service.py` — deterministic chunking with overlap
- `supabase_service.py` — pgvector storage adapter (TODO)
- `lightrag_service.py` — LightRAG indexing + retrieval adapter (TODO)
- `grok_client.py` — Grok 4.1 API client wrapper (single place for LLM calls)
- `ingest_service.py` — orchestration: extract → chunk → store → index

### server/retrieval/
- `retrieval_service.py` — shared retrieval used by BOTH chat + handbook; returns context + citations

### server/workflows/chat/
- `chat_workflow.py` — chat orchestration: retrieve → grounded prompt → Grok → answer

### server/workflows/handbook/
- `prompts.py` — plan/write templates (LongWriter-inspired)
- `handbook_workflow.py` — plan → iterative write loop; saves markdown artifact

### server/utils/
- `word_count.py` — counts words (used to stop when target reached)
- `output_store.py` — saves handbook markdown into outputs folder

## ui/
- `streamlit_app.py` — minimal UI demonstrating upload/chat/handbook with clear sections
- `ui/README.md` — how to run UI

## outputs/
- `outputs/README.md` — describes saved artifacts
- `outputs/handbook/` — generated handbook markdown
- `outputs/chat/` — optional logs/traces
