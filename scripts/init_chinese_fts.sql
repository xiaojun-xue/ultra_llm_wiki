-- Chinese Full-Text Search Setup
-- This script enables Chinese word segmentation for PostgreSQL full-text search.
--
-- Option A: pg_jieba (recommended for Chinese)
--   Requires: pg_jieba extension installed in the Docker image
--
-- Option B: zhparser
--   Requires: zhparser extension installed in the Docker image
--
-- Run this AFTER init_db.sql if the extension is available.

-- Try pg_jieba first (better for modern Chinese)
DO $$
BEGIN
    -- Try pg_jieba
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pg_jieba;
        CREATE TEXT SEARCH CONFIGURATION chinese_jieba (PARSER = jieba);
        ALTER TEXT SEARCH CONFIGURATION chinese_jieba
            ADD MAPPING FOR n, v, a, i, e, l WITH simple;

        -- Update the full-text index to use Chinese config
        DROP INDEX IF EXISTS ix_documents_fts;
        CREATE INDEX ix_documents_fts ON documents
            USING gin(to_tsvector('chinese_jieba', coalesce(title, '') || ' ' || coalesce(content, '')));

        RAISE NOTICE 'Chinese FTS configured with pg_jieba';
        RETURN;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'pg_jieba not available, trying zhparser...';
    END;

    -- Try zhparser
    BEGIN
        CREATE EXTENSION IF NOT EXISTS zhparser;
        CREATE TEXT SEARCH CONFIGURATION chinese_zh (PARSER = zhparser);
        ALTER TEXT SEARCH CONFIGURATION chinese_zh
            ADD MAPPING FOR n, v, a, i, e, l WITH simple;

        DROP INDEX IF EXISTS ix_documents_fts;
        CREATE INDEX ix_documents_fts ON documents
            USING gin(to_tsvector('chinese_zh', coalesce(title, '') || ' ' || coalesce(content, '')));

        RAISE NOTICE 'Chinese FTS configured with zhparser';
        RETURN;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'zhparser not available, using simple config (bigram fallback)';
    END;

    -- Fallback: simple config handles CJK via character-level tokenization
    RAISE NOTICE 'Using default simple FTS config. Chinese search will rely on vector similarity.';
END $$;
