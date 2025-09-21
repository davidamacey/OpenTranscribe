"""add_speaker_fields

Revision ID: 5a8c23df4578
Revises: initial_migration
Create Date: 2025-05-23 17:10:00.000000

"""

from uuid import uuid4

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "5a8c23df4578"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to speaker table
    op.add_column("speaker", sa.Column("display_name", sa.String(), nullable=True))
    op.add_column("speaker", sa.Column("uuid", sa.String(), nullable=True))
    op.add_column(
        "speaker",
        sa.Column("verified", sa.Boolean(), server_default="false", nullable=False),
    )

    # Create index on the uuid column
    op.create_index(op.f("ix_speaker_uuid"), "speaker", ["uuid"], unique=False)

    # Update existing speakers to have a UUID
    connection = op.get_bind()
    speakers = connection.execute(sa.text("SELECT id FROM speaker")).fetchall()

    for speaker in speakers:
        speaker_id = speaker[0]
        uuid_str = str(uuid4())
        connection.execute(
            sa.text("UPDATE speaker SET uuid = :uuid WHERE id = :id"),
            {"uuid": uuid_str, "id": speaker_id},
        )

    # Now make uuid not nullable after populating it
    op.alter_column("speaker", "uuid", nullable=False)


def downgrade():
    # Remove index first
    op.drop_index(op.f("ix_speaker_uuid"), table_name="speaker")

    # Remove columns
    op.drop_column("speaker", "verified")
    op.drop_column("speaker", "uuid")
    op.drop_column("speaker", "display_name")
