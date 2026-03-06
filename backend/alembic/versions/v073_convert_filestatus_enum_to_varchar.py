"""Convert FileStatus native enum to VARCHAR(50)

On databases where the status column was created as a PostgreSQL native enum type
(via SQLAlchemy Enum(FileStatus)), convert it to VARCHAR(50) for consistency with
init_db.sql which uses VARCHAR(50).

Revision ID: v073_convert_filestatus_enum_to_varchar
Revises: v072_add_queued_downloading_statuses
Create Date: 2026-02-15
"""

from alembic import op

revision = "v073_convert_filestatus_enum_to_varchar"
down_revision = "v072_add_queued_downloading_statuses"


def upgrade():
    """Convert native enum column to VARCHAR(50) if it exists."""
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'filestatus') THEN
                ALTER TABLE media_file ALTER COLUMN status TYPE VARCHAR(50) USING LOWER(status::text);
                DROP TYPE IF EXISTS filestatus;
            END IF;
        END $$;
    """
    )
    # Also fix any existing uppercase values from a previous migration run without LOWER
    op.execute(
        """
        UPDATE media_file SET status = LOWER(status) WHERE status != LOWER(status);
    """
    )


def downgrade():
    """No downgrade needed - VARCHAR is the canonical type."""
