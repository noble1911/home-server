-- Update embedding column for nomic-embed-text (768 dimensions)
-- Previous schema used VECTOR(1536) for OpenAI ada-003; we're switching to
-- local Ollama embeddings which produce 768-dimensional vectors.
--
-- Usage:
--   docker exec immich-postgres psql -U postgres -d immich -f /app/migrations/003_update_embedding_dimensions.sql

-- Drop existing HNSW index (dimension is baked into the index)
DROP INDEX IF EXISTS butler.idx_user_facts_embedding;

-- Alter column to new dimension size
-- Note: existing rows with NULL embedding are unaffected
ALTER TABLE butler.user_facts
    ALTER COLUMN embedding TYPE VECTOR(768);

-- Recreate HNSW index with correct dimension
-- Only indexes non-null embeddings to save space
CREATE INDEX IF NOT EXISTS idx_user_facts_embedding
    ON butler.user_facts
    USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;
