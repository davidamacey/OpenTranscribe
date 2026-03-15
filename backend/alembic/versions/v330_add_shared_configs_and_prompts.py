"""Add sharing columns to LLM settings, ASR settings, and prompts.

Revision ID: v330_add_shared_configs_and_prompts
Revises: v320_add_cluster_suggested_name
Create Date: 2026-03-13
"""

from alembic import op

revision = "v330_add_shared_configs_and_prompts"
down_revision = "v320_add_cluster_suggested_name"
branch_labels = None
depends_on = None


def upgrade():
    # --- user_llm_settings ---
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'user_llm_settings' AND column_name = 'is_shared'
            ) THEN
                ALTER TABLE user_llm_settings
                    ADD COLUMN is_shared BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'user_llm_settings' AND column_name = 'shared_at'
            ) THEN
                ALTER TABLE user_llm_settings
                    ADD COLUMN shared_at TIMESTAMPTZ;
            END IF;
        END $$;
    """)

    # --- user_asr_settings ---
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'user_asr_settings' AND column_name = 'is_shared'
            ) THEN
                ALTER TABLE user_asr_settings
                    ADD COLUMN is_shared BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'user_asr_settings' AND column_name = 'shared_at'
            ) THEN
                ALTER TABLE user_asr_settings
                    ADD COLUMN shared_at TIMESTAMPTZ;
            END IF;
        END $$;
    """)

    # --- summary_prompt ---
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'summary_prompt' AND column_name = 'is_shared'
            ) THEN
                ALTER TABLE summary_prompt
                    ADD COLUMN is_shared BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'summary_prompt' AND column_name = 'shared_at'
            ) THEN
                ALTER TABLE summary_prompt
                    ADD COLUMN shared_at TIMESTAMPTZ;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'summary_prompt' AND column_name = 'tags'
            ) THEN
                ALTER TABLE summary_prompt
                    ADD COLUMN tags JSONB NOT NULL DEFAULT '[]'::jsonb;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'summary_prompt' AND column_name = 'usage_count'
            ) THEN
                ALTER TABLE summary_prompt
                    ADD COLUMN usage_count INTEGER NOT NULL DEFAULT 0;
            END IF;
        END $$;
    """)

    # --- Partial indexes for shared configs ---
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_llm_settings_shared
            ON user_llm_settings(is_shared) WHERE is_shared = TRUE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_asr_settings_shared
            ON user_asr_settings(is_shared) WHERE is_shared = TRUE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_summary_prompt_shared
            ON summary_prompt(is_shared, shared_at DESC) WHERE is_shared = TRUE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_summary_prompt_tags
            ON summary_prompt USING GIN (tags)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_summary_prompt_tags")
    op.execute("DROP INDEX IF EXISTS ix_summary_prompt_shared")
    op.execute("DROP INDEX IF EXISTS ix_user_asr_settings_shared")
    op.execute("DROP INDEX IF EXISTS ix_user_llm_settings_shared")

    op.execute("ALTER TABLE summary_prompt DROP COLUMN IF EXISTS usage_count")
    op.execute("ALTER TABLE summary_prompt DROP COLUMN IF EXISTS tags")
    op.execute("ALTER TABLE summary_prompt DROP COLUMN IF EXISTS shared_at")
    op.execute("ALTER TABLE summary_prompt DROP COLUMN IF EXISTS is_shared")

    op.execute("ALTER TABLE user_asr_settings DROP COLUMN IF EXISTS shared_at")
    op.execute("ALTER TABLE user_asr_settings DROP COLUMN IF EXISTS is_shared")

    op.execute("ALTER TABLE user_llm_settings DROP COLUMN IF EXISTS shared_at")
    op.execute("ALTER TABLE user_llm_settings DROP COLUMN IF EXISTS is_shared")
