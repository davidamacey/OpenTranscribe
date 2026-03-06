"""
Database migration utilities.

Runs Alembic migrations automatically on application startup.
Alembic is the sole authority for database schema creation and upgrades.
Handles empty databases, existing untracked databases, and tracked databases.
"""

import logging
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy import inspect

from alembic import command  # type: ignore[attr-defined]
from app.core.config import settings

logger = logging.getLogger(__name__)


def get_alembic_config() -> Config:
    """Get Alembic configuration."""
    # Find alembic.ini relative to backend directory
    backend_dir = Path(__file__).parent.parent.parent
    alembic_ini = backend_dir / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return config


def _detect_schema_version(conn, tables: list[str]) -> str | None:  # noqa: C901
    """Detect the schema version of an existing untracked database.

    Returns the Alembic revision to stamp, or None if no user table exists.
    """
    if "user" not in tables:
        return None

    from sqlalchemy import text

    def _check_exists(query: str) -> bool:
        return bool(conn.execute(text(query)).scalar())

    has_ldap = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name='user' AND column_name='auth_type')"
    )
    has_keycloak_pki = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name='user' AND column_name='keycloak_id')"
    )
    has_fedramp = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='user_mfa')"
    )
    has_search_settings = "system_settings" in tables and _check_exists(
        "SELECT EXISTS(SELECT 1 FROM system_settings WHERE key = 'search.embedding_model')"
    )
    has_overlap_column = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name='transcript_segment' AND column_name='is_overlap')"
    )
    has_pki_fingerprint = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name='user' AND column_name='pki_fingerprint_sha256')"
    )
    has_auth_config = "auth_config" in tables
    has_error_category = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name='media_file' AND column_name='error_category')"
    )
    has_suggestion_source = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name='speaker' AND column_name='suggestion_source')"
    )
    has_perf_indexes = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM pg_indexes "
        "WHERE indexname='idx_media_file_user_status_upload')"
    )
    has_fk_indexes = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM pg_indexes WHERE indexname='idx_comment_media_file_id')"
    )
    has_remaining_fk_indexes = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM pg_indexes WHERE indexname='idx_speaker_user_id')"
    )
    has_model_tracking = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name='media_file' AND column_name='whisper_model')"
    )
    has_segment_unique_constraint = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='uq_transcript_segment_content')"
    )
    has_queued_downloading_statuses = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM pg_enum e "
        "JOIN pg_type t ON e.enumtypid = t.oid "
        "WHERE t.typname = 'filestatus' AND e.enumlabel = 'queued')"
    )
    # v073: filestatus native enum was converted to VARCHAR(50)
    # If the status column is VARCHAR and no native enum exists, we're at v073+
    has_varchar_status = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'media_file' AND column_name = 'status' "
        "AND data_type = 'character varying')"
    )
    filestatus_enum_exists = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM pg_type WHERE typname = 'filestatus')"
    )
    has_word_timestamps = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'transcript_segment' AND column_name = 'words')"
    )
    has_allow_local_fallback = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'user' AND column_name = 'allow_local_fallback')"
    )
    has_keycloak_refresh_token = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'user' AND column_name = 'keycloak_refresh_token')"
    )
    has_speaker_attributes = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'speaker' AND column_name = 'predicted_gender')"
    )
    has_collection_default_prompt = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'collection' AND column_name = 'default_summary_prompt_id')"
    )

    has_refresh_token_jti = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name='refresh_token' AND column_name='jti')"
    )
    has_mfa_uuid = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name='user_mfa' AND column_name='uuid')"
    )
    has_user_group = (
        "user_group" in tables and "user_group_member" in tables and "collection_share" in tables
    )

    has_sharing_constraints = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM pg_constraint "
        "WHERE conname = '_collection_share_permission_check')"
    )

    has_speaker_cluster = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'speaker_cluster')"
    )
    has_speaker_clustering_indexes = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM pg_indexes "
        "WHERE indexname = 'idx_speaker_cluster_member_speaker_id')"
    )
    has_cluster_quality_metrics = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'speaker_cluster' AND column_name = 'min_similarity')"
    )
    has_avatar_path = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'speaker_profile' AND column_name = 'avatar_path')"
    )

    # Return the highest version stamp that matches (newest first)
    # v270: profile avatar_path column
    if has_speaker_cluster and has_cluster_quality_metrics and has_avatar_path:
        return "v270_add_profile_avatar"
    # v260: cluster quality metrics (min_similarity, separation_score, margin)
    if has_speaker_cluster and has_cluster_quality_metrics:
        return "v260_add_cluster_quality_metrics"
    # v250: speaker clustering FK indexes
    if has_speaker_cluster and has_speaker_clustering_indexes:
        return "v250_add_speaker_clustering_indexes"
    # v220: speaker clustering tables
    if has_speaker_cluster:
        return "v220_add_speaker_clusters"
    # v211: CHECK constraints and indexes on groups/sharing tables
    if has_user_group and has_sharing_constraints:
        return "v211_add_sharing_constraints_and_indexes"
    # v210: user groups and collection sharing tables
    if has_user_group:
        return "v210_add_groups_and_sharing"
    # v200: schema reconciliation (jti on refresh_token + uuid on user_mfa)
    if has_collection_default_prompt and has_refresh_token_jti and has_mfa_uuid:
        return "v200_schema_reconciliation"
    # v190: default_summary_prompt_id column on collection table
    if has_collection_default_prompt:
        return "v190_add_collection_default_prompt"
    # v180: speaker attribute detection columns
    if has_speaker_attributes:
        return "v180_add_speaker_attributes"
    # v170: keycloak_refresh_token column for federated logout
    if has_keycloak_refresh_token:
        return "v170_add_keycloak_refresh_token"
    # v160: allow_local_fallback column added to user table
    if has_allow_local_fallback:
        return "v160_add_allow_local_fallback"
    # v140: words column added to transcript_segment
    if has_word_timestamps and has_varchar_status and not filestatus_enum_exists:
        return "v140_add_word_timestamps"
    # v073: status column is VARCHAR and no native enum exists
    # (This also matches fresh installs from init_db.sql which use VARCHAR)
    if has_varchar_status and not filestatus_enum_exists and has_segment_unique_constraint:
        return "v073_convert_filestatus_enum_to_varchar"
    if has_queued_downloading_statuses:
        return "v072_add_queued_downloading_statuses"
    if has_segment_unique_constraint:
        return "v071_add_transcript_segment_unique_constraint"
    if has_model_tracking:
        return "v130_add_processing_model_tracking"
    if has_remaining_fk_indexes:
        return "v120_add_remaining_fk_indexes"
    if has_fk_indexes:
        return "v110_add_missing_fk_indexes"
    if has_perf_indexes:
        return "v100_optimize_query_performance"
    if has_suggestion_source:
        return "v091_add_speaker_suggestion_source"
    if has_error_category:
        return "v090_add_error_category"
    if has_auth_config:
        return "v080_add_auth_config"
    if has_pki_fingerprint:
        return "v070_pki_security"
    if has_overlap_column:
        return "v060_add_transcript_overlap"
    if has_fedramp and has_search_settings:
        return "v050_add_search_settings"
    if has_fedramp:
        return "v040_add_fedramp_compliance"
    if has_keycloak_pki:
        return "v031_add_keycloak_pki_auth"
    if has_ldap:
        return "v030_add_ldap_auth"
    if "system_settings" in tables:
        return "v020_add_system_settings"
    return "v010_baseline"


def run_migrations() -> None:
    """Run database migrations on startup.

    Alembic is the sole authority for database schema. Handles:
    1. Empty database: Run all migrations from scratch (alembic upgrade head)
    2. Existing untracked DB: Detect version, stamp, then upgrade
    3. Already tracked: Apply any pending migrations

    Uses a PostgreSQL advisory lock to prevent concurrent migration runs
    when multiple backend instances start simultaneously.
    """
    from sqlalchemy import text

    logger.info("Checking database migrations...")

    engine = create_engine(settings.DATABASE_URL)

    # Acquire advisory lock to prevent concurrent migration runs
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(42)"))
        conn.commit()

    try:
        # Ensure alembic_version column is wide enough for long revision IDs
        with engine.connect() as conn:
            if "alembic_version" in inspect(engine).get_table_names():
                conn.execute(
                    text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
                )
                conn.commit()

        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            detected_version = _detect_schema_version(conn, tables)

        # Dispose the engine to release all pooled connections before Alembic opens its own
        engine.dispose()

        config = get_alembic_config()

        # Get the head revision from Alembic scripts
        from alembic.script import ScriptDirectory

        script_dir = ScriptDirectory.from_config(config)
        head_rev = script_dir.get_current_head()

        if current_rev:
            logger.info(f"Current migration version: {current_rev}")
            if current_rev == head_rev:
                logger.info("Database is up to date, no migrations needed")
            else:
                logger.info(f"Upgrading from {current_rev} to {head_rev}...")
                command.upgrade(config, "head")
        elif detected_version:
            logger.info(f"Existing database detected, stamping {detected_version}...")
            command.stamp(config, detected_version)
            if detected_version != head_rev:
                logger.info("Applying migrations to upgrade to current version...")
                command.upgrade(config, "head")
        elif tables:
            logger.info("Existing untracked database detected, stamping current version...")
            command.stamp(config, "head")
        else:
            logger.info("Empty database detected, running full migration...")
            command.upgrade(config, "head")

        logger.info("Database migrations complete")
    finally:
        # Release advisory lock - use a fresh engine since the previous one may be disposed
        unlock_engine = create_engine(settings.DATABASE_URL)
        try:
            with unlock_engine.connect() as conn:
                conn.execute(text("SELECT pg_advisory_unlock(42)"))
                conn.commit()
        finally:
            unlock_engine.dispose()
