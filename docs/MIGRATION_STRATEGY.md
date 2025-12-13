# OpenTranscribe Database Migration Strategy

## Overview

Starting with v0.2.0, OpenTranscribe uses Alembic for database migrations. **Migrations run automatically on backend startup** - no manual intervention required for most users.

## How It Works

When the backend container starts, it automatically:

1. **Detects the database state** (fresh, v0.1.0, or already migrated)
2. **Stamps the appropriate version** if Alembic tracking doesn't exist
3. **Applies any pending migrations**

### Upgrade Scenarios

| Scenario | What Happens |
|----------|--------------|
| Fresh install | Tables created by `init_db.sql`, Alembic stamps as current version |
| Upgrade from v0.1.0 | Alembic stamps baseline, applies v0.2.0 migration |
| Already migrated | Alembic applies any pending migrations |

## Upgrading from v0.1.0 to v0.2.0

For existing users, the upgrade is automatic:

```bash
# 1. Backup your database (recommended)
./opentr.sh backup

# 2. Pull new version
git pull origin main

# 3. Restart services - migrations run automatically
./opentr.sh stop
./opentr.sh start dev  # or: ./opentr.sh start prod
```

That's it! The backend will automatically detect your v0.1.0 database and apply the v0.2.0 migration.

## Schema Changes: v0.1.0 → v0.2.0

### New: `system_settings` Table

Global configuration store for runtime-adjustable settings:

| Setting Key | Default | Description |
|-------------|---------|-------------|
| `transcription.max_retries` | `3` | Max retry attempts for failed transcriptions |
| `transcription.retry_limit_enabled` | `true` | Whether to enforce retry limits |
| `transcription.garbage_cleanup_enabled` | `true` | Clean up garbage words during transcription |
| `transcription.max_word_length` | `50` | Max word length threshold for garbage detection |

### No Breaking Changes

- No columns removed or renamed
- No data type changes
- Existing data is preserved

## Rollback (If Needed)

If you need to rollback after upgrading:

```bash
# 1. Stop services
./opentr.sh stop

# 2. Restore from backup
./opentr.sh restore backups/your_backup.sql

# 3. Checkout previous version
git checkout v0.1.0

# 4. Restart
./opentr.sh start dev
```

## Manual Migration Commands (Advanced)

For advanced users who need manual control:

```bash
# Enter backend container
./opentr.sh shell backend

# Check current version
alembic current

# Show migration history
alembic history --verbose

# Manually upgrade
alembic upgrade head

# Manually downgrade
alembic downgrade v010_baseline

# Stamp without running migration
alembic stamp v020_add_system_settings
```

## Verification

After upgrade, verify the migration succeeded:

```sql
-- Check system_settings table exists and has data
SELECT * FROM system_settings;

-- Should return 4 rows:
-- transcription.max_retries = '3'
-- transcription.retry_limit_enabled = 'true'
-- transcription.garbage_cleanup_enabled = 'true'
-- transcription.max_word_length = '50'

-- Check Alembic version
SELECT * FROM alembic_version;
-- Should show: v020_add_system_settings
```

## Migration File Naming

Migration files in `backend/alembic/versions/`:

```
v010_baseline.py              # v0.1.0 baseline schema
v020_add_system_settings.py   # v0.2.0 system settings
```

Format: `v{MAJOR}{MINOR}{PATCH}_{description}.py`

## Technical Reference

- **Config**: `backend/alembic.ini`
- **Migrations**: `backend/alembic/versions/`
- **Auto-migration code**: `backend/app/db/migrations.py`
- **Startup integration**: `backend/app/main.py` (lifespan handler)
