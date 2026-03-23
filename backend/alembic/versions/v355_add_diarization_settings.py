"""Add user_diarization_settings table and migrate disable_diarization to diarization_source.

Revision ID: v355_add_diarization_settings
Revises: v353_fix_segment_unique_index
Create Date: 2026-03-22
"""

from alembic import op

revision = "v355_add_diarization_settings"
down_revision = "v353_fix_segment_unique_index"
branch_labels = None
depends_on = None


def upgrade():
    # Create user_diarization_settings table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_diarization_settings (
            id          SERIAL PRIMARY KEY,
            uuid        UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            user_id     INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            name        VARCHAR(100) NOT NULL,
            provider    VARCHAR(50) NOT NULL,
            model_name  VARCHAR(100) NOT NULL,
            api_key     TEXT,
            base_url    VARCHAR(500),
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            last_tested TIMESTAMPTZ,
            test_status VARCHAR(20),
            test_message TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT _user_diarization_config_name_unique UNIQUE (user_id, name)
        );
        CREATE INDEX IF NOT EXISTS ix_user_diarization_settings_uuid
            ON user_diarization_settings(uuid);
        CREATE INDEX IF NOT EXISTS ix_user_diarization_settings_user_id
            ON user_diarization_settings(user_id);
    """
    )

    # Migrate transcription_disable_diarization=true -> transcription_diarization_source=off
    op.execute(
        """
        DO $$
        BEGIN
            -- For each user who had diarization disabled, insert the new setting
            -- (only if the new key doesn't already exist for that user)
            INSERT INTO user_setting (user_id, setting_key, setting_value, created_at, updated_at)
            SELECT user_id, 'transcription_diarization_source', 'off', NOW(), NOW()
            FROM user_setting
            WHERE setting_key = 'transcription_disable_diarization'
              AND setting_value = 'true'
              AND NOT EXISTS (
                  SELECT 1 FROM user_setting us2
                  WHERE us2.user_id = user_setting.user_id
                    AND us2.setting_key = 'transcription_diarization_source'
              );

            -- Delete the old keys
            DELETE FROM user_setting
            WHERE setting_key = 'transcription_disable_diarization';
        END $$;
    """
    )


def downgrade():
    # Reverse the setting migration: diarization_source=off -> disable_diarization=true
    op.execute(
        """
        DO $$
        BEGIN
            INSERT INTO user_setting (user_id, setting_key, setting_value, created_at, updated_at)
            SELECT user_id, 'transcription_disable_diarization', 'true', NOW(), NOW()
            FROM user_setting
            WHERE setting_key = 'transcription_diarization_source'
              AND setting_value = 'off'
              AND NOT EXISTS (
                  SELECT 1 FROM user_setting us2
                  WHERE us2.user_id = user_setting.user_id
                    AND us2.setting_key = 'transcription_disable_diarization'
              );
        END $$;
    """
    )

    op.execute("DROP TABLE IF EXISTS user_diarization_settings")
