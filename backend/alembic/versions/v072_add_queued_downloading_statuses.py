"""Add QUEUED and DOWNLOADING file statuses

Revision ID: v072_add_queued_downloading_statuses
Revises: v071_add_transcript_segment_unique_constraint
Create Date: 2026-02-11
"""

revision = "v072_add_queued_downloading_statuses"
down_revision = "v071_add_transcript_segment_unique_constraint"


def upgrade():
    """
    Add QUEUED and DOWNLOADING status values to FileStatus.

    QUEUED: For playlist placeholders waiting for download
    DOWNLOADING: For files actively being downloaded from external sources

    This prevents startup recovery from treating download-pending files as abandoned.

    Note: The status column is VARCHAR(50), not an enum type, so no database
    schema changes are needed. The new values are defined in the Python FileStatus
    enum and can be used immediately. This migration exists for version tracking only.
    """
    # No database changes needed - status is a VARCHAR column, not an enum
    # The Python code (models/media.py FileStatus enum) defines the new values


def downgrade():
    """
    No database changes to downgrade - status is a VARCHAR column.
    """
