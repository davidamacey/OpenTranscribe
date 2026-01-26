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


def run_migrations() -> None:
    """
    Run database migrations on startup.

    Handles three scenarios:
    1. Fresh install: Tables exist from init_db.sql, stamp current version
    2. Existing v0.1.0: Stamp baseline, apply new migrations
    3. Already tracked: Apply any pending migrations
    """
    logger.info("Checking database migrations...")

    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        # Check if Alembic is already tracking this database
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()

        inspector = inspect(engine)
        tables = inspector.get_table_names()

        # Check for LDAP columns (v0.3.0)
        has_ldap_columns = False
        # Check for Keycloak/PKI columns (v0.3.1)
        has_keycloak_pki_columns = False
        # Check for FedRAMP security tables (v0.4.0)
        has_fedramp_tables = False
        if "user" in tables:
            from sqlalchemy import text

            result = conn.execute(
                text(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='user' AND column_name='auth_type')"
                )
            )
            has_ldap_columns = bool(result.scalar())

            # Check for keycloak_id column
            result = conn.execute(
                text(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='user' AND column_name='keycloak_id')"
                )
            )
            has_keycloak_pki_columns = bool(result.scalar())

            # Check for user_mfa table (FedRAMP v0.3.2)
            result = conn.execute(
                text(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                    "WHERE table_name='user_mfa')"
                )
            )
            has_fedramp_tables = bool(result.scalar())

    # Determine what action to take (connection is now closed)
    if current_rev:
        # Alembic already tracking - just upgrade
        logger.info(f"Current migration version: {current_rev}")
        config = get_alembic_config()
        command.upgrade(config, "head")
    elif "user" in tables:
        # Existing database without Alembic tracking
        if has_fedramp_tables:
            # Has v0.4.0 schema (FedRAMP security tables) - stamp as current
            logger.info(
                "Existing v0.4.0 database detected (has FedRAMP tables), stamping version..."
            )
            config = get_alembic_config()
            command.stamp(config, "v040_add_fedramp_compliance")
        elif has_keycloak_pki_columns:
            # Has v0.3.1 schema - stamp as current
            logger.info(
                "Existing v0.3.1 database detected (has Keycloak/PKI columns), stamping version..."
            )
            config = get_alembic_config()
            command.stamp(config, "v031_add_keycloak_pki_auth")
        elif has_ldap_columns:
            # Has v0.3.0 schema - stamp and upgrade
            logger.info(
                "Existing v0.3.0 database detected (has LDAP columns), stamping and upgrading..."
            )
            config = get_alembic_config()
            command.stamp(config, "v030_add_ldap_auth")
            logger.info("Applying migrations to upgrade to current version...")
            command.upgrade(config, "head")
        elif "system_settings" in tables:
            # Has v0.2.0 schema - stamp and upgrade
            logger.info("Existing v0.2.0 database detected, stamping and upgrading...")
            config = get_alembic_config()
            command.stamp(config, "v020_add_system_settings")
            logger.info("Applying migrations to upgrade to current version...")
            command.upgrade(config, "head")
        else:
            # v0.1.0 database - stamp baseline then upgrade
            logger.info("Existing v0.1.0 database detected, stamping baseline...")
            config = get_alembic_config()
            command.stamp(config, "v010_baseline")
            logger.info("Applying migrations to upgrade to current version...")
            command.upgrade(config, "head")
    elif tables:
        # Fresh install with init_db.sql tables - stamp head
        logger.info("Fresh database detected, stamping current version...")
        config = get_alembic_config()
        command.stamp(config, "head")
    else:
        # Empty database - let Alembic create everything
        logger.info("Empty database detected, running full migration...")
        config = get_alembic_config()
        command.upgrade(config, "head")

    logger.info("Database migrations complete")
