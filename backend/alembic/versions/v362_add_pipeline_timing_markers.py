"""Add imohash/url/prepare/error markers to file_pipeline_timing.

Phase 2 PR #9/#10 of the timing audit plan. The code already emits these
markers into the ``benchmark:{task_id}`` Redis hash; without the matching
columns the ``pipeline_timing_service`` flush silently drops them at
insert time, so long-term analysis of imohash compute cost, yt-dlp
download time, prepare-upload RPC latency, and error-mode wall-clock
could not be reconstructed from SQL.

All columns are nullable BIGINT (epoch-ms), matching the existing schema
convention so durations can be subtracted cheaply.

Revision ID: v362_add_pipeline_timing_markers
Revises: v361_add_media_file_imohash
Create Date: 2026-04-24
"""

from alembic import op

revision = "v362_add_pipeline_timing_markers"
down_revision = "v361_add_media_file_imohash"
branch_labels = None
depends_on = None


_NEW_COLUMNS: tuple[str, ...] = (
    "imohash_start_ms",
    "imohash_end_ms",
    "prepare_upload_end_ms",
    "url_download_start_ms",
    "url_download_end_ms",
    "pipeline_error_end_ms",
)


def upgrade():
    # Idempotent — each column is guarded by a not-exists check so the
    # migration is safe to re-run against partially-upgraded databases.
    for col in _NEW_COLUMNS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'file_pipeline_timing'
                      AND column_name = '{col}'
                ) THEN
                    ALTER TABLE file_pipeline_timing ADD COLUMN {col} BIGINT;
                END IF;
            END $$;
            """
        )


def downgrade():
    for col in _NEW_COLUMNS:
        op.execute(f"ALTER TABLE file_pipeline_timing DROP COLUMN IF EXISTS {col}")
