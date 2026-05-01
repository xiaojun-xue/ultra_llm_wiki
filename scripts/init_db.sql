-- LLM Wiki - Database Initialization
-- Run this after PostgreSQL + pgvector container is up

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable full-text search for Chinese (requires zhparser or pg_jieba in production)
-- For now we use the default 'simple' config; swap to 'zhparser' when available
-- CREATE EXTENSION IF NOT EXISTS zhparser;
-- CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);

-- ── Documents ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    doc_type VARCHAR(50) NOT NULL,
    content TEXT,
    content_html TEXT,
    metadata JSONB DEFAULT '{}',
    file_path VARCHAR(1000),
    mime_type VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100)
);

-- Full-text search index on title + content
CREATE INDEX IF NOT EXISTS ix_documents_fts
    ON documents USING gin(to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, '')));

CREATE INDEX IF NOT EXISTS ix_documents_doc_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS ix_documents_created_at ON documents(created_at DESC);

-- ── Chunks ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024),
    metadata JSONB DEFAULT '{}',
    token_count INTEGER
);

-- Vector similarity index (IVFFlat, good for 1K-1M vectors)
CREATE INDEX IF NOT EXISTS ix_chunks_embedding
    ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS ix_chunks_document_id ON chunks(document_id);

-- ── Document Relations ────────────────────────────────────

CREATE TABLE IF NOT EXISTS document_relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,
    description TEXT,
    confidence FLOAT DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_relation UNIQUE (source_id, target_id, relation_type)
);

CREATE INDEX IF NOT EXISTS ix_relations_source ON document_relations(source_id);
CREATE INDEX IF NOT EXISTS ix_relations_target ON document_relations(target_id);
CREATE INDEX IF NOT EXISTS ix_relations_type ON document_relations(relation_type);

-- ── Tags ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS document_tags (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, tag_id)
);
