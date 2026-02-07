#If you make a .env file and add these parameters, the app will use them accordingly. 
#One would need to make a supabase database with the SQL code found in sql_tables.md

# -----------------------------
# Grok / xAI credentials
# -----------------------------
GROK_API_KEY=xai-
GROK_BASE_URL=https://api.x.ai/v1
GROK_MODEL=grok-4

# -----------------------------
# Embeddings (OpenAI)
# Used by lightrag_service.py
# -----------------------------
EMBEDDINGS_API_KEY=sk-proj-
EMBEDDINGS_BASE_URL=https://api.openai.com/v1
EMBEDDINGS_MODEL=text-embedding-3-small

# -----------------------------
# LLM for Entity Extraction (OpenAI)
# Used by lightrag_service.py for building knowledge graph
# -----------------------------
LLM_API_KEY=sk-proj-
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# Optional
EMBEDDINGS_TIMEOUT_SECONDS=60

# -----------------------------
# Supabase (pgvector storage)
# Server-side only (use service role key)
# -----------------------------
SUPABASE_URL=https://######.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sb_secret_

# -----------------------------
# LightRAG working directory
# Local on-disk cache for derived artifacts
# -----------------------------
LIGHTRAG_WORKING_DIR=./lightrag_cache
