"""v0.18.0 - Add speaker attribute detection columns

Revision ID: v180_add_speaker_attributes
Revises: v170_add_keycloak_refresh_token
Create Date: 2026-02-25

Adds predicted_gender, predicted_age_range, attribute_confidence, and
attributes_predicted_at columns to the speaker and speaker_profile tables.
These store AI-predicted voice attributes (gender, age range) detected
by SpeechBrain's wav2vec2 gender classifier from acoustic features.

GitHub issue: #141
"""

from alembic import op

revision = "v180_add_speaker_attributes"
down_revision = "v170_add_keycloak_refresh_token"
branch_labels = None
depends_on = None


def upgrade():
    """Add speaker attribute columns to speaker and speaker_profile tables."""
    # Speaker table additions
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'speaker' AND column_name = 'predicted_gender'
            ) THEN
                ALTER TABLE speaker
                    ADD COLUMN predicted_gender VARCHAR(20),
                    ADD COLUMN predicted_age_range VARCHAR(30),
                    ADD COLUMN attribute_confidence JSONB,
                    ADD COLUMN attributes_predicted_at TIMESTAMP WITH TIME ZONE;
            END IF;
        END $$;
        """
    )

    # SpeakerProfile table additions
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'speaker_profile' AND column_name = 'predicted_gender'
            ) THEN
                ALTER TABLE speaker_profile
                    ADD COLUMN predicted_gender VARCHAR(20),
                    ADD COLUMN predicted_age_range VARCHAR(30);
            END IF;
        END $$;
        """
    )


def downgrade():
    """Remove speaker attribute columns."""
    op.execute(
        """
        ALTER TABLE speaker
            DROP COLUMN IF EXISTS predicted_gender,
            DROP COLUMN IF EXISTS predicted_age_range,
            DROP COLUMN IF EXISTS attribute_confidence,
            DROP COLUMN IF EXISTS attributes_predicted_at;
        """
    )
    op.execute(
        """
        ALTER TABLE speaker_profile
            DROP COLUMN IF EXISTS predicted_gender,
            DROP COLUMN IF EXISTS predicted_age_range;
        """
    )
