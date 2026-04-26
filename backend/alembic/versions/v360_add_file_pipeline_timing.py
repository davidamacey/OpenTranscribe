"""Add file_pipeline_timing table for durable end-to-end wall-clock metrics.

Part of the Phase 1 timing instrumentation plan (see
``/home/superdave/.claude/plans/i-need-a-full-snoopy-popcorn.md``). This table
stores a flush of the ``benchmark:{task_id}`` Redis hash at the moment
``postprocess_end`` fires — one row per completed transcription task_id.

The schema is purely additive. No running pipeline reads from it, so the
migration is safe to apply online.

Revision ID: v360_add_file_pipeline_timing
Revises: v355_add_diarization_settings
Create Date: 2026-04-24
"""

from alembic import op

revision = "v360_add_file_pipeline_timing"
down_revision = "v355_add_diarization_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS file_pipeline_timing (
            task_id                         VARCHAR(64) PRIMARY KEY,
            file_id                         INTEGER NOT NULL REFERENCES media_file(id) ON DELETE CASCADE,
            user_id                         INTEGER REFERENCES "user"(id) ON DELETE CASCADE,

            -- Stage 0: client-side (frontend instrumentation, optional)
            client_hash_start_ms            BIGINT,
            client_hash_end_ms              BIGINT,
            client_put_start_ms             BIGINT,
            client_put_end_ms               BIGINT,

            -- Stage 1-5: API ingress (legacy flow only)
            http_request_received_ms        BIGINT,
            http_read_complete_ms           BIGINT,
            http_validation_end_ms          BIGINT,
            minio_put_start_ms              BIGINT,
            minio_put_end_ms                BIGINT,
            thumbnail_start_ms              BIGINT,
            thumbnail_end_ms                BIGINT,
            db_commit_start_ms              BIGINT,
            db_commit_end_ms                BIGINT,
            http_response_end_ms            BIGINT,

            -- Stage 6-10: CPU preprocess
            dispatch_timestamp_ms           BIGINT,
            preprocess_task_prerun_ms       BIGINT,
            media_download_start_ms         BIGINT,
            media_download_end_ms           BIGINT,
            ffmpeg_start_ms                 BIGINT,
            ffmpeg_end_ms                   BIGINT,
            metadata_start_ms               BIGINT,
            metadata_end_ms                 BIGINT,
            temp_upload_start_ms            BIGINT,
            temp_upload_end_ms              BIGINT,
            preprocess_end_ms               BIGINT,

            -- Stage 11-12: GPU transcribe + diarize
            gpu_received_ms                 BIGINT,
            gpu_task_prerun_ms              BIGINT,
            gpu_audio_load_start_ms         BIGINT,
            gpu_audio_load_end_ms           BIGINT,
            gpu_end_ms                      BIGINT,

            -- Stage 13-15: CPU postprocess + completion
            postprocess_received_ms         BIGINT,
            postprocess_task_prerun_ms      BIGINT,
            postprocess_end_ms              BIGINT,
            completion_notified_ms          BIGINT,

            -- Stage 17-22: async enrichment
            search_index_start_ms           BIGINT,
            search_index_end_ms             BIGINT,
            search_index_chunks_start_ms    BIGINT,
            search_index_chunks_end_ms      BIGINT,
            speaker_upsert_start_ms         BIGINT,
            speaker_upsert_end_ms           BIGINT,
            waveform_start_ms               BIGINT,
            waveform_end_ms                 BIGINT,
            clustering_start_ms             BIGINT,
            clustering_end_ms               BIGINT,
            summary_start_ms                BIGINT,
            summary_end_ms                  BIGINT,

            -- Derived durations (stored for query speed)
            user_perceived_duration_ms      BIGINT,
            fully_indexed_duration_ms       BIGINT,

            -- Per-task context
            audio_duration_s                DOUBLE PRECISION,
            file_size_bytes                 BIGINT,
            content_type                    VARCHAR(128),
            whisper_model                   VARCHAR(64),
            asr_provider                    VARCHAR(64),
            asr_model                       VARCHAR(128),
            gpu_device                      VARCHAR(128),
            http_flow                       VARCHAR(32),
            queue_depth_at_dispatch         JSONB,
            concurrent_files_at_dispatch    INTEGER,
            cpu_worker_cold                 VARCHAR(8),
            gpu_worker_cold                 VARCHAR(8),
            cpu_transcribe_worker_cold      VARCHAR(8),
            retry_count                     INTEGER,
            per_retry_timings               JSONB,

            created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS ix_file_pipeline_timing_file_id
            ON file_pipeline_timing(file_id);
        CREATE INDEX IF NOT EXISTS ix_file_pipeline_timing_user_id
            ON file_pipeline_timing(user_id);
        CREATE INDEX IF NOT EXISTS ix_file_pipeline_timing_created_at
            ON file_pipeline_timing(created_at);
        CREATE INDEX IF NOT EXISTS ix_file_pipeline_timing_dispatch_ms
            ON file_pipeline_timing(dispatch_timestamp_ms);
        CREATE INDEX IF NOT EXISTS ix_file_pipeline_timing_completion_ms
            ON file_pipeline_timing(completion_notified_ms);
        CREATE INDEX IF NOT EXISTS ix_file_pipeline_timing_user_perceived
            ON file_pipeline_timing(user_perceived_duration_ms);
        CREATE INDEX IF NOT EXISTS ix_file_pipeline_timing_fully_indexed
            ON file_pipeline_timing(fully_indexed_duration_ms);
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS file_pipeline_timing")
