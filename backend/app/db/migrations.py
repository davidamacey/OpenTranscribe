"""
Database migration utilities.

Runs Alembic migrations automatically on application startup.
Handles both fresh installs and upgrades from previous versions.
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

    # Return the highest version stamp that matches
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

    Handles three scenarios:
    1. Fresh install: Tables exist from init_db.sql, stamp current version
    2. Existing v0.1.0+: Stamp detected version, apply new migrations
    3. Already tracked: Apply any pending migrations
    """
    logger.info("Checking database migrations...")

    engine = create_engine(settings.DATABASE_URL)

    # Ensure alembic_version column is wide enough for long revision IDs
    with engine.connect() as conn:
        from sqlalchemy import text

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
        logger.info("Fresh database detected, stamping current version...")
        command.stamp(config, "head")
    else:
        logger.info("Empty database detected, running full migration...")
        command.upgrade(config, "head")

    logger.info("Database migrations complete")
