"""v0.23.0 - Add auto-labeling support columns and upload_batch table

Revision ID: v230_add_auto_labeling
Revises: v220_add_speaker_clusters
Create Date: 2026-03-04

Adds columns and tables for AI-powered auto-labeling (Issue #140):
- tag: source, normalized_name (with index)
- file_tag: source, ai_confidence, created_at
- collection: source
- collection_member: source, ai_confidence
- topic_suggestion: auto_applied_tags, auto_applied_collections, auto_apply_completed_at
- upload_batch: new table for tracking multi-file imports
- media_file: upload_batch_id FK
- Backfills normalized_name on existing tags
"""

from alembic import op

revision = "v230_add_auto_labeling"
down_revision = "v220_add_speaker_clusters"
branch_labels = None
depends_on = None


def upgrade():
    """Add auto-labeling columns and upload_batch table."""

    # --- tag table: add source, normalized_name ---
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'tag' AND column_name = 'source'
            ) THEN
                ALTER TABLE tag ADD COLUMN source VARCHAR(50);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'tag' AND column_name = 'normalized_name'
            ) THEN
                ALTER TABLE tag ADD COLUMN normalized_name VARCHAR;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ix_tag_normalized_name'
            ) THEN
                CREATE INDEX ix_tag_normalized_name ON tag(normalized_name);
            END IF;
        END $$;
        """
    )

    # --- file_tag table: add source, ai_confidence, created_at ---
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'file_tag' AND column_name = 'source'
            ) THEN
                ALTER TABLE file_tag ADD COLUMN source VARCHAR(50);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'file_tag' AND column_name = 'ai_confidence'
            ) THEN
                ALTER TABLE file_tag ADD COLUMN ai_confidence FLOAT;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'file_tag' AND column_name = 'created_at'
            ) THEN
                ALTER TABLE file_tag ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();
            END IF;
        END $$;
        """
    )

    # --- collection table: add source ---
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'collection' AND column_name = 'source'
            ) THEN
                ALTER TABLE collection ADD COLUMN source VARCHAR(50);
            END IF;
        END $$;
        """
    )

    # --- collection_member table: add source, ai_confidence ---
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'collection_member' AND column_name = 'source'
            ) THEN
                ALTER TABLE collection_member ADD COLUMN source VARCHAR(50);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'collection_member' AND column_name = 'ai_confidence'
            ) THEN
                ALTER TABLE collection_member ADD COLUMN ai_confidence FLOAT;
            END IF;
        END $$;
        """
    )

    # --- topic_suggestion table: add auto_applied_tags, auto_applied_collections,
    #     auto_apply_completed_at ---
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'topic_suggestion'
                AND column_name = 'auto_applied_tags'
            ) THEN
                ALTER TABLE topic_suggestion
                ADD COLUMN auto_applied_tags JSONB DEFAULT '[]'::jsonb;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'topic_suggestion'
                AND column_name = 'auto_applied_collections'
            ) THEN
                ALTER TABLE topic_suggestion
                ADD COLUMN auto_applied_collections JSONB DEFAULT '[]'::jsonb;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'topic_suggestion'
                AND column_name = 'auto_apply_completed_at'
            ) THEN
                ALTER TABLE topic_suggestion
                ADD COLUMN auto_apply_completed_at TIMESTAMPTZ;
            END IF;
        END $$;
        """
    )

    # --- upload_batch table ---
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'upload_batch'
            ) THEN
                CREATE TABLE upload_batch (
                    id SERIAL PRIMARY KEY,
                    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                    source VARCHAR(50) NOT NULL,
                    file_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    grouping_status VARCHAR(50) DEFAULT 'pending'
                );
            END IF;
        END $$;
        """
    )
    # --- media_file table: add upload_batch_id FK ---
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'media_file' AND column_name = 'upload_batch_id'
            ) THEN
                ALTER TABLE media_file
                ADD COLUMN upload_batch_id INTEGER
                REFERENCES upload_batch(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ix_media_file_upload_batch_id'
            ) THEN
                CREATE INDEX ix_media_file_upload_batch_id ON media_file(upload_batch_id);
            END IF;
        END $$;
        """
    )

    # --- Backfill normalized_name on existing tags ---
    op.execute(
        """
        UPDATE tag
        SET normalized_name = LOWER(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(name, '[-_]+', ' ', 'g'), '\\s+', ' ', 'g')))
        WHERE normalized_name IS NULL;
        """
    )


def downgrade():
    """Remove auto-labeling columns and upload_batch table."""
    # media_file FK and index
    op.execute("DROP INDEX IF EXISTS ix_media_file_upload_batch_id")
    op.execute("ALTER TABLE media_file DROP COLUMN IF EXISTS upload_batch_id")

    # upload_batch table
    op.execute("DROP TABLE IF EXISTS upload_batch CASCADE")

    # topic_suggestion columns
    op.execute("ALTER TABLE topic_suggestion DROP COLUMN IF EXISTS auto_apply_completed_at")
    op.execute("ALTER TABLE topic_suggestion DROP COLUMN IF EXISTS auto_applied_collections")
    op.execute("ALTER TABLE topic_suggestion DROP COLUMN IF EXISTS auto_applied_tags")

    # collection_member columns
    op.execute("ALTER TABLE collection_member DROP COLUMN IF EXISTS ai_confidence")
    op.execute("ALTER TABLE collection_member DROP COLUMN IF EXISTS source")

    # collection columns
    op.execute("ALTER TABLE collection DROP COLUMN IF EXISTS source")

    # file_tag columns (created_at is NOT dropped — it pre-existed from v010 baseline)
    op.execute("ALTER TABLE file_tag DROP COLUMN IF EXISTS ai_confidence")
    op.execute("ALTER TABLE file_tag DROP COLUMN IF EXISTS source")

    # tag columns
    op.execute("DROP INDEX IF EXISTS ix_tag_normalized_name")
    op.execute("ALTER TABLE tag DROP COLUMN IF EXISTS normalized_name")
    op.execute("ALTER TABLE tag DROP COLUMN IF EXISTS source")
