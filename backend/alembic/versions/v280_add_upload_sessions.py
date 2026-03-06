"""v0.28.0 - Add upload_session table for TUS resumable uploads

Revision ID: v280_add_upload_sessions
Revises: v220_add_speaker_clusters
Create Date: 2026-03-05

Adds the upload_session table to track TUS 1.0.0 protocol resumable upload state.
Each row represents one in-flight or completed resumable upload session.

GitHub issue: #10
"""

from alembic import op

revision = "v280_add_upload_sessions"
down_revision = "v220_add_speaker_clusters"
branch_labels = None
depends_on = None


def upgrade():
    """Create upload_session table with indexes."""

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'upload_session'
            ) THEN
                CREATE TABLE upload_session (
                    id SERIAL PRIMARY KEY,
                    upload_id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                    -- UNIQUE constraint on media_file_id prevents two concurrent
                    -- TUS POST requests for the same file from both succeeding.
                    media_file_id INTEGER NOT NULL UNIQUE REFERENCES media_file(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                    minio_upload_id VARCHAR(1024),
                    storage_path VARCHAR(1024) NOT NULL,
                    offset BIGINT NOT NULL DEFAULT 0,
                    total_size BIGINT NOT NULL,
                    content_type VARCHAR(256) NOT NULL DEFAULT 'application/octet-stream',
                    filename VARCHAR(512) NOT NULL,
                    tus_metadata TEXT,
                    parts_json TEXT NOT NULL DEFAULT '[]',
                    chunk_buffer BYTEA,
                    min_speakers INTEGER,
                    max_speakers INTEGER,
                    num_speakers INTEGER,
                    extracted_from_video_json TEXT,
                    status VARCHAR(32) NOT NULL DEFAULT 'active',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    completed_at TIMESTAMPTZ
                );
            END IF;
        END $$;
    """)

    # Index on upload_id (UUID) for TUS HEAD/PATCH/DELETE lookups
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'idx_upload_session_upload_id'
            ) THEN
                CREATE INDEX idx_upload_session_upload_id ON upload_session(upload_id);
            END IF;
        END $$;
    """)

    # Index on user_id for per-user session counts
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'idx_upload_session_user_id'
            ) THEN
                CREATE INDEX idx_upload_session_user_id ON upload_session(user_id);
            END IF;
        END $$;
    """)

    # Index on media_file_id for cascade operations
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'idx_upload_session_media_file_id'
            ) THEN
                CREATE INDEX idx_upload_session_media_file_id ON upload_session(media_file_id);
            END IF;
        END $$;
    """)

    # Partial index on (status, expires_at) for efficient cleanup queries
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'idx_upload_session_status_expires'
            ) THEN
                CREATE INDEX idx_upload_session_status_expires
                    ON upload_session(expires_at)
                    WHERE status = 'active';
            END IF;
        END $$;
    """)


def downgrade():
    """Drop upload_session table and indexes."""
    op.execute("DROP TABLE IF EXISTS upload_session CASCADE;")
