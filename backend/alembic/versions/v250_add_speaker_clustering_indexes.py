"""Add missing indexes on FK columns for speaker clustering performance.

Revision ID: v250_add_speaker_clustering_indexes
Revises: v230_add_auto_labeling
Create Date: 2026-03-05

The v220 migration created speaker_cluster_member with a UNIQUE constraint
on (cluster_id, speaker_id). That composite index covers cluster_id lookups
(leftmost column) but does NOT cover speaker_id-only lookups.

Also adds an index on speaker_profile.source_cluster_id which was added
in v220 without an index.
"""

from alembic import op

revision = "v250_add_speaker_clustering_indexes"
down_revision = "v230_add_auto_labeling"
branch_labels = None
depends_on = None

_INDEXES = [
    ("idx_speaker_cluster_member_speaker_id", "speaker_cluster_member", "speaker_id"),
    ("idx_speaker_profile_source_cluster_id", "speaker_profile", "source_cluster_id"),
]


def upgrade():
    """Add missing FK indexes on speaker clustering tables."""
    for idx_name, table, column in _INDEXES:
        op.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column});
            """
        )


def downgrade():
    """Remove indexes. Safe - no data loss."""
    for idx_name, _, _ in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {idx_name};")
