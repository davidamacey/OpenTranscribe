"""v0.21.0 - Add speaker clustering tables for pre-clustering and batch labeling

Revision ID: v210_add_speaker_clusters
Revises: v200_schema_reconciliation
Create Date: 2026-02-26

Adds tables for speaker pre-clustering across files:
- speaker_cluster: Auto-discovered speaker groups
- speaker_cluster_member: Cluster membership with confidence
- speaker_audio_clip: Short audio clips for speaker identification
- Adds cluster_id FK to speaker table
- Adds source_cluster_id FK to speaker_profile table

GitHub issue: #144
"""

from alembic import op

revision = "v210_add_speaker_clusters"
down_revision = "v200_schema_reconciliation"
branch_labels = None
depends_on = None


def upgrade():
    """Create speaker clustering tables and add FK columns."""

    # --- speaker_cluster table ---
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'speaker_cluster'
            ) THEN
                CREATE TABLE speaker_cluster (
                    id SERIAL PRIMARY KEY,
                    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                    label VARCHAR(255),
                    description TEXT,
                    member_count INTEGER DEFAULT 0,
                    promoted_to_profile_id INTEGER REFERENCES speaker_profile(id) ON DELETE SET NULL,
                    representative_speaker_id INTEGER,
                    quality_score FLOAT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            END IF;
        END $$;
        """
    )

    # Indexes for speaker_cluster
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ix_speaker_cluster_id'
            ) THEN
                CREATE INDEX ix_speaker_cluster_id ON speaker_cluster(id);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ix_speaker_cluster_uuid'
            ) THEN
                CREATE INDEX ix_speaker_cluster_uuid ON speaker_cluster(uuid);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'idx_speaker_cluster_user_id'
            ) THEN
                CREATE INDEX idx_speaker_cluster_user_id ON speaker_cluster(user_id);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'idx_speaker_cluster_promoted'
            ) THEN
                CREATE INDEX idx_speaker_cluster_promoted
                ON speaker_cluster(promoted_to_profile_id);
            END IF;
        END $$;
        """
    )

    # --- speaker_cluster_member table ---
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'speaker_cluster_member'
            ) THEN
                CREATE TABLE speaker_cluster_member (
                    id SERIAL PRIMARY KEY,
                    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                    cluster_id INTEGER NOT NULL REFERENCES speaker_cluster(id) ON DELETE CASCADE,
                    speaker_id INTEGER NOT NULL REFERENCES speaker(id) ON DELETE CASCADE,
                    confidence FLOAT DEFAULT 0.0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(cluster_id, speaker_id)
                );
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ix_speaker_cluster_member_id'
            ) THEN
                CREATE INDEX ix_speaker_cluster_member_id ON speaker_cluster_member(id);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ix_speaker_cluster_member_uuid'
            ) THEN
                CREATE INDEX ix_speaker_cluster_member_uuid ON speaker_cluster_member(uuid);
            END IF;
        END $$;
        """
    )

    # --- speaker_audio_clip table ---
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'speaker_audio_clip'
            ) THEN
                CREATE TABLE speaker_audio_clip (
                    id SERIAL PRIMARY KEY,
                    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                    speaker_id INTEGER NOT NULL REFERENCES speaker(id) ON DELETE CASCADE,
                    media_file_id INTEGER NOT NULL REFERENCES media_file(id) ON DELETE CASCADE,
                    storage_path VARCHAR(512) NOT NULL,
                    start_time FLOAT NOT NULL,
                    end_time FLOAT NOT NULL,
                    duration FLOAT NOT NULL,
                    is_representative BOOLEAN DEFAULT FALSE,
                    quality_score FLOAT DEFAULT 0.0,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ix_speaker_audio_clip_id'
            ) THEN
                CREATE INDEX ix_speaker_audio_clip_id ON speaker_audio_clip(id);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ix_speaker_audio_clip_uuid'
            ) THEN
                CREATE INDEX ix_speaker_audio_clip_uuid ON speaker_audio_clip(uuid);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'idx_speaker_audio_clip_speaker'
            ) THEN
                CREATE INDEX idx_speaker_audio_clip_speaker ON speaker_audio_clip(speaker_id);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'idx_speaker_audio_clip_media'
            ) THEN
                CREATE INDEX idx_speaker_audio_clip_media ON speaker_audio_clip(media_file_id);
            END IF;
        END $$;
        """
    )

    # --- Add cluster_id to speaker table ---
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'speaker' AND column_name = 'cluster_id'
            ) THEN
                ALTER TABLE speaker
                ADD COLUMN cluster_id INTEGER REFERENCES speaker_cluster(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'idx_speaker_cluster_id'
            ) THEN
                CREATE INDEX idx_speaker_cluster_id ON speaker(cluster_id);
            END IF;
        END $$;
        """
    )

    # --- Add source_cluster_id to speaker_profile table ---
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'speaker_profile'
                AND column_name = 'source_cluster_id'
            ) THEN
                ALTER TABLE speaker_profile
                ADD COLUMN source_cluster_id INTEGER
                REFERENCES speaker_cluster(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )


def downgrade():
    """Remove speaker clustering tables and FK columns."""
    op.execute("ALTER TABLE speaker_profile DROP COLUMN IF EXISTS source_cluster_id")
    op.execute("DROP INDEX IF EXISTS idx_speaker_cluster_id")
    op.execute("ALTER TABLE speaker DROP COLUMN IF EXISTS cluster_id")
    op.execute("DROP TABLE IF EXISTS speaker_audio_clip CASCADE")
    op.execute("DROP TABLE IF EXISTS speaker_cluster_member CASCADE")
    op.execute("DROP TABLE IF EXISTS speaker_cluster CASCADE")
