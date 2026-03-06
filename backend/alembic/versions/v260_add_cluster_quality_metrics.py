"""Add quality metrics columns to speaker clustering tables.

Revision ID: v260_add_cluster_quality_metrics
Revises: v250_add_speaker_clustering_indexes
Create Date: 2026-03-05

Adds:
- speaker_cluster.min_similarity (Float) — tightest pairwise cosine similarity
- speaker_cluster.separation_score (Float) — nearest-neighbor separation metric
- speaker_cluster_member.margin (Float) — gap between best and second-best match
"""

from alembic import op

revision = "v260_add_cluster_quality_metrics"
down_revision = "v250_add_speaker_clustering_indexes"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("speaker_cluster", "min_similarity", "FLOAT"),
    ("speaker_cluster", "separation_score", "FLOAT"),
    ("speaker_cluster_member", "margin", "FLOAT"),
]


def upgrade():
    """Add quality metric columns to speaker clustering tables."""
    for table, column, col_type in _COLUMNS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = '{table}' AND column_name = '{column}'
                ) THEN
                    ALTER TABLE {table} ADD COLUMN {column} {col_type};
                END IF;
            END $$;
            """  # noqa: S608  # nosec B608
        )


def downgrade():
    """Remove quality metric columns."""
    for table, column, _ in _COLUMNS:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
