"""v0.15.0 - Add file retention settings

Revision ID: v150_add_file_retention_settings
Revises: v140_add_word_timestamps
Create Date: 2026-02-21

Adds system_settings entries for automatic file retention / auto-deletion.
Admins can configure a retention period (in days) after which completed
transcription files are automatically deleted. Disabled by default.

Feature requested by @Politiezone-MIDOW (GitHub issue #134):
    "[FEATURE] Delete files older than x-amount of days for all users (admin setting)"
    Use cases: disk space management and GDPR compliance for environments
    handling sensitive information that must be deleted after a retention window.

New system_settings keys:
    - files.retention_enabled: Master switch (default: false)
    - files.retention_days: Retention window in days (default: 90)
    - files.delete_error_files: Also purge error-status files (default: false)
    - files.retention_run_time: HH:MM daily schedule time (default: 02:00)
    - files.retention_timezone: IANA timezone string (default: UTC)
    - files.retention_last_run: ISO UTC timestamp of last run (default: null)
    - files.retention_last_run_deleted: Files deleted in last run (default: 0)
"""

from alembic import op

revision = "v150_add_file_retention_settings"
down_revision = "v140_add_word_timestamps"
branch_labels = None
depends_on = None


def upgrade():
    """Seed file retention settings into system_settings table."""
    op.execute(
        """
        INSERT INTO system_settings (key, value, description) VALUES
            ('files.retention_enabled', 'false',
             'Enable automatic deletion of old completed transcription files'),
            ('files.retention_days', '90',
             'Delete completed files older than this many days (requires retention_enabled=true)'),
            ('files.delete_error_files', 'false',
             'Also delete files in error status during retention runs'),
            ('files.retention_run_time', '02:00',
             'Daily scheduled run time in HH:MM format'),
            ('files.retention_timezone', 'UTC',
             'IANA timezone for the scheduled run (e.g. America/New_York)'),
            ('files.retention_last_run', NULL,
             'ISO UTC timestamp of last successful retention run'),
            ('files.retention_last_run_deleted', '0',
             'Number of files deleted in last retention run')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    """Remove file retention settings from system_settings table."""
    op.execute(
        """
        DELETE FROM system_settings WHERE key IN (
            'files.retention_enabled',
            'files.retention_days',
            'files.delete_error_files',
            'files.retention_run_time',
            'files.retention_timezone',
            'files.retention_last_run',
            'files.retention_last_run_deleted'
        )
        """
    )
