"""
Database migration utilities.

Runs Alembic migrations automatically on application startup.
Handles both fresh installs and upgrades from previous versions.
"""

import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy import inspect

from alembic import command  # type: ignore[attr-defined]
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
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


def _detect_schema_version(conn, tables: list[str]) -> str | None:
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
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables " "WHERE table_name='user_mfa')"
    )
    has_search_settings = "system_settings" in tables and _check_exists(
        "SELECT EXISTS(SELECT 1 FROM system_settings " "WHERE key = 'search.embedding_model')"
    )
    has_overlap_column = _check_exists(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name='transcript_segment' AND column_name='is_overlap')"
    )

    # Return the highest version stamp that matches
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

    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        detected_version = _detect_schema_version(conn, tables)

    config = get_alembic_config()

    if current_rev:
        logger.info(f"Current migration version: {current_rev}")
        command.upgrade(config, "head")
    elif detected_version:
        logger.info(f"Existing database detected, stamping {detected_version}...")
        command.stamp(config, detected_version)
        if detected_version != "v060_add_transcript_overlap":
            logger.info("Applying migrations to upgrade to current version...")
            command.upgrade(config, "head")
    elif tables:
        logger.info("Fresh database detected, stamping current version...")
        command.stamp(config, "head")
    else:
        logger.info("Empty database detected, running full migration...")
        command.upgrade(config, "head")

    logger.info("Database migrations complete")
