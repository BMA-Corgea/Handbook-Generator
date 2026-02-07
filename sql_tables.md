-- =========================================
-- 0) Extensions
-- =========================================
create extension if not exists vector;

-- =========================================
-- 1) Drop existing objects (clean slate)
-- =========================================
drop function if exists public.match_chunks;
drop table if exists public.chunks cascade;
drop table if exists public.documents cascade;

-- =========================================
-- 2) Documents table
-- =========================================
create table public.documents (
  doc_id        text primary key,

  -- Human-friendly name (PDF title / original filename)
  title         text not null,

  -- Where the PDF came from (dashboard upload path, S3 key, etc.)
  file_path     text,

  -- Optional: full document text (useful for re-chunking later)
  content       text,

  metadata      jsonb not null default '{}'::jsonb,

  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- Helpful indexes
create index documents_title_idx on public.documents (title);
create index documents_file_path_idx on public.documents (file_path);

-- =========================================
-- 3) Chunks table
-- =========================================
create table public.chunks (
  chunk_id          text primary key,

  doc_id            text not null
    references public.documents(doc_id)
    on delete cascade,

  chunk_order_index integer,
  file_path         text,

  content           text not null,
  tokens            integer,

  metadata          jsonb not null default '{}'::jsonb,

  -- pgvector embedding (adjust dim if you ever change models)
  embedding         vector(1536),

  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

-- =========================================
-- 4) Indexes
-- =========================================

-- Vector similarity (cosine)
create index chunks_embedding_cosine_idx
  on public.chunks
  using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

-- Lookups
create index chunks_doc_id_idx on public.chunks (doc_id);
create index chunks_file_path_idx on public.chunks (file_path);

-- Optional FTS (debug / fallback only)
create index chunks_content_fts_idx
  on public.chunks
  using gin (to_tsvector('english', content));

-- =========================================
-- 5) RPC: vector similarity search (doc-scoped)
-- =========================================
create or replace function public.match_chunks (
  query_embedding vector(1536),
  match_doc_id text,
  match_count int default 8
)
returns table (
  chunk_id text,
  doc_id text,
  title text,
  file_path text,
  content text,
  chunk_order_index integer,
  metadata jsonb,
  similarity float
)
language sql
stable
as $$
  select
    c.chunk_id,
    c.doc_id,
    d.title,
    c.file_path,
    c.content,
    c.chunk_order_index,
    c.metadata,
    1 - (c.embedding <=> query_embedding) as similarity
  from public.chunks c
  join public.documents d on d.doc_id = c.doc_id
  where c.embedding is not null
    and c.doc_id = match_doc_id
  order by c.embedding <=> query_embedding
  limit match_count;
$$;
