<div align="center">
  <img src="../../assets/logo-banner.png" alt="OpenTranscribe Logo" width="200">

  # Alembic Database Migration Management
</div>

## Database Authority

Alembic migrations in `backend/alembic/versions/` are the **sole authority** for the database schema in all environments. There is no `init_db.sql` — the baseline migration (`v010_baseline.py`) creates the full schema from scratch and subsequent migrations handle schema evolution.

## Current Migration Chain

The migration chain spans v010 (baseline) through v355 (v0.4.0), covering ~35 migrations:

| Range | Description |
|-------|-------------|
| v010 | Baseline schema (all core tables) |
| v020–v079 | System settings, auth methods (LDAP, Keycloak, PKI), FedRAMP, search |
| v080–v140 | Auth config, error categories, speaker suggestions, performance indexes, word timestamps |
| v150–v210 | Speaker profiles, embedding migration, sharing, groups |
| v220–v260 | Speaker clustering, auto-labeling, cluster quality |
| v270–v300 | ASR provider support, upload sessions, password reset, gender |
| v310–v355 | Speaker constraints, shared configs/prompts, user media sources, diarization settings, AI summary settings, requested whisper model |

## Startup Runner (`app/db/migrations.py`)

On backend startup, `migrations.py` automatically:
1. Detects current database schema version
2. Stamps untracked databases with the appropriate version
3. Runs `alembic upgrade head` to bring the DB to the current version

This means migrations apply automatically on every deploy — no manual `alembic upgrade head` needed.

## Migration Workflow

All schema changes must use Alembic migrations:

1. Create a new migration file in `backend/alembic/versions/`
   - Use idempotent SQL with `IF NOT EXISTS` for safety
   - Set correct `down_revision` to the previous migration ID
2. Update SQLAlchemy models in `backend/app/models/` to match
3. Update Pydantic schemas in `backend/app/schemas/` if needed
4. Update `backend/app/db/migrations.py` version detection logic
5. Test with `./opentr.sh reset dev` (drops DB, runs full chain from v010)

### Example Migration Pattern
```python
# backend/alembic/versions/v356_add_new_column.py
revision = "v356_add_new_column"
down_revision = "v355_add_diarization_settings"

def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'media_file' AND column_name = 'new_column'
            ) THEN
                ALTER TABLE "media_file" ADD COLUMN new_column VARCHAR(256);
            END IF;
        END $$;
    """)

def downgrade():
    op.execute('ALTER TABLE "media_file" DROP COLUMN IF EXISTS new_column')
```

## Reset vs Restart

- `./opentr.sh reset dev` — **Deletes all data**, drops DB, reruns full migration chain (v010→latest)
- `./opentr.sh restart-backend` — Restarts backend container; migrations run automatically, no data loss

## Maintaining Consistency

- Never edit migration files that have already been deployed
- Keep SQLAlchemy models (`app/models/`) in sync with migrations
- Document breaking schema changes
- Speaker UUIDs provide cross-video speaker identity — do not alter UUID columns in migrations
