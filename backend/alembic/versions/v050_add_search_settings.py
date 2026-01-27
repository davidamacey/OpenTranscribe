"""v0.5.0 - Add search and RAG settings

Revision ID: v050_add_search_settings
Revises: v040_add_fedramp_compliance
Create Date: 2026-01-27

Seeds search-related settings into the system_settings table for
the new hybrid BM25 + vector search feature (Issues #65, #52).

These settings are used by the search embedding service to persist
the active embedding model and dimension across API and worker processes.

New system_settings rows:
    - search.embedding_model: Active embedding model ID (default: all-MiniLM-L6-v2)
    - search.embedding_dimension: Vector dimension matching the model (default: 384)

OpenSearch changes (handled lazily at runtime, not in this migration):
    - transcript_chunks index created on first indexing or search
    - transcript-hybrid-search pipeline created on first search
"""


from alembic import op

# revision identifiers, used by Alembic.
revision = "v050_add_search_settings"
down_revision = "v040_add_fedramp_compliance"
branch_labels = None
depends_on = None


def upgrade():
    """Add search settings to system_settings table."""
    # Seed search settings (idempotent - ON CONFLICT DO NOTHING)
    op.execute(
        """
        INSERT INTO system_settings (key, value, description) VALUES
            ('search.embedding_model', 'all-MiniLM-L6-v2',
             'Search embedding model ID used for semantic search'),
            ('search.embedding_dimension', '384',
             'Search embedding vector dimension matching the current model')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    """Remove search settings from system_settings table."""
    op.execute(
        """
        DELETE FROM system_settings
        WHERE key IN ('search.embedding_model', 'search.embedding_dimension')
        """
    )
