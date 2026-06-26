-- PostAI Database Setup
-- Run this once: psql -U postgres -c "CREATE DATABASE postai;"
-- Then: psql -U postgres -d postai -f init_db.sql

CREATE TABLE IF NOT EXISTS posts (
    id         SERIAL PRIMARY KEY,
    prompt     TEXT    NOT NULL,
    image_url  TEXT    NOT NULL,
    captions   JSONB,
    published  BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for feed queries (only published, newest first)
CREATE INDEX IF NOT EXISTS idx_posts_published_created
    ON posts (published, created_at DESC)
    WHERE published = TRUE;
