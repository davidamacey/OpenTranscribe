"""v0.30.0 - Add gender_confirmed_by_user column to speaker table

Revision ID: v300_add_gender_confirmed
Revises: v290_add_password_reset_tokens
Create Date: 2026-03-08

Adds a boolean flag to track whether a user has manually confirmed
the AI-predicted gender for a speaker instance.
"""

from alembic import op

revision = "v300_add_gender_confirmed"
down_revision = "v290_add_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'speaker' AND column_name = 'gender_confirmed_by_user'
            ) THEN
                ALTER TABLE speaker ADD COLUMN gender_confirmed_by_user BOOLEAN DEFAULT FALSE;
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("ALTER TABLE speaker DROP COLUMN IF EXISTS gender_confirmed_by_user")
