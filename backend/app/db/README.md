<div align="center">
  <img src="../../../assets/logo-banner.png" alt="OpenTranscribe Logo" width="200">
  
  # Database Layer Documentation
</div>

This directory contains core database configuration, session management, and the comprehensive database management approach for OpenTranscribe.

## 📁 Database Components

```
db/
├── base.py           # Core SQLAlchemy setup and configuration
├── session_utils.py  # Session management utilities
└── README.md         # This documentation
```

## 🔧 Core Database Setup (`base.py`)

### Purpose
Provides the fundamental SQLAlchemy configuration and database connection setup.

### Key Components
```python
# Database engine with connection pooling
engine = create_engine(settings.DATABASE_URL)

# Session factory for database transactions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all ORM models
Base = declarative_base()

# FastAPI dependency for database sessions
def get_db():
    """Dependency injection for database sessions in API endpoints."""
```

### Usage in API Endpoints
```python
@router.get("/files")
def get_files(db: Session = Depends(get_db)):
    """Automatic session management via dependency injection."""
    return db.query(MediaFile).all()
```

## 🔄 Session Management (`session_utils.py`)

### Purpose
Provides advanced session management patterns for different use cases, particularly background tasks and complex transactions.

### Key Utilities

#### Context Manager for Transactions
```python
@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    # Automatic commit/rollback handling
    # Exception safety with proper cleanup
```

**Usage:**
```python
# Background tasks with automatic transaction management
with session_scope() as db:
    file_obj = db.query(MediaFile).get(file_id)
    file_obj.status = FileStatus.PROCESSING
    # Automatic commit on success, rollback on exception
```

#### Object Refresh Utilities
```python
def get_refreshed_object(db: Session, model_class, obj_id: int):
    """Get a fresh copy of an object from the database."""
    # Handles detached objects in Celery tasks
    # Provides fallback session creation
    
def refresh_session_object(obj, session=None):
    """Refresh a detached object with a new session if needed."""
    # Re-attaches objects to active sessions
    # Handles session state management
```

**Usage:**
```python
# Celery task with detached object handling
@celery_app.task
def process_file_task(file_id: int):
    with session_scope() as db:
        # Get fresh object instance
        file_obj = get_refreshed_object(db, MediaFile, file_id)
        # Process with active session
```

### Session Patterns

#### API Endpoints (Dependency Injection)
```python
def api_endpoint(db: Session = Depends(get_db)):
    """FastAPI automatically manages session lifecycle."""
    # Session created for request
    # Automatic cleanup after response
```

#### Background Tasks (Context Manager)
```python
def background_task():
    """Background tasks manage their own sessions."""
    with session_scope() as db:
        # Explicit transaction control
        # Exception-safe cleanup
```

#### Service Layer (Injected Session)
```python
class FileService:
    def __init__(self, db: Session):
        self.db = db
    
    def process_file(self, file_id: int):
        # Uses injected session from endpoint
        # Participates in request transaction
```

# Database Management Approach

## Overview

OpenTranscribe uses a dual approach for database management:
- **Development**: Direct SQL initialization via `database/init_db.sql`
- **Production**: Alembic migrations for version control and deployment

## Development Approach

### Current Setup
- Database schema is defined in `database/init_db.sql`
- SQLAlchemy models in `app/models/` reflect the schema
- Pydantic schemas in `app/schemas/` handle API validation

### Development Workflow
1. **Schema Changes**: Update `database/init_db.sql` directly
2. **Model Updates**: Modify SQLAlchemy models in `app/models/`
3. **Schema Updates**: Update Pydantic schemas in `app/schemas/`
4. **Reset Database**: Run `./opentr.sh reset dev` to apply changes

### Why This Approach?
- **Faster iteration** during active development
- **Simpler debugging** with direct SQL control
- **No migration conflicts** during rapid prototyping
- **Easy reset** for development environments

## Production Approach

### Alembic Setup
- Alembic is configured in `alembic.ini`
- Migration files in `alembic/versions/`
- Current migrations:
  - `initial_migration.py` - Base schema
  - `add_speaker_fields.py` - Speaker enhancements

### Production Deployment
1. **Generate Migration**: Create Alembic migration from model changes
2. **Review Migration**: Ensure migration is safe and correct
3. **Deploy**: Run `alembic upgrade head` on production
4. **Verify**: Confirm schema changes applied correctly

### When to Switch to Alembic

The project will transition to full Alembic usage when:
- Core features are stable
- Schema changes become less frequent
- Production deployments begin
- Team decides to enforce migration discipline

## Directory Structure

```
backend/
├── alembic/                    # Alembic migration framework
│   ├── versions/              # Migration files
│   ├── env.py                 # Alembic environment config
│   └── script.py.mako         # Migration template
├── alembic.ini                # Alembic configuration
├── database/
│   └── init_db.sql           # Development schema (current)
└── app/
    ├── db/                   # Database layer (session management)
    ├── models/               # SQLAlchemy ORM models
    └── schemas/              # Pydantic validation schemas
```

## Commands Reference

### Development Commands
```bash
# Reset development database
./opentr.sh reset dev

# Inspect current database
python scripts/db_inspect.py
```

### Production Commands (Future)
```bash
# Generate new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Check current version
alembic current

# Rollback to previous version
alembic downgrade -1
```

## Best Practices

### During Development
- Always update all three: SQL, models, and schemas
- Test changes with `./opentr.sh reset dev`
- Document significant schema changes
- Keep SQLAlchemy models in sync with SQL

### Session Management
- Use `get_db()` dependency in API endpoints
- Use `session_scope()` context manager in background tasks
- Always handle detached objects in Celery tasks
- Prefer service layer injection for complex business logic

### For Production (Future)
- Review all auto-generated migrations
- Test migrations on staging database
- Backup database before applying migrations
- Use descriptive migration messages
- Never edit existing migration files

## Migration Strategy

When transitioning to production:

1. **Final Development Schema**: Ensure `init_db.sql` represents the final development state
2. **Create Base Migration**: Generate an Alembic migration that matches `init_db.sql`
3. **Mark as Applied**: Mark the base migration as applied to existing databases
4. **Switch to Alembic**: Use Alembic for all future schema changes
5. **Retire init_db.sql**: Keep for reference but use migrations for all changes

## Troubleshooting

### Common Issues
- **Model/Schema Mismatch**: Check that SQLAlchemy models match `init_db.sql`
- **Validation Errors**: Ensure Pydantic schemas match SQLAlchemy models
- **Database State**: Use `./opentr.sh reset dev` to start fresh
- **Session Errors**: Use `session_scope()` for background tasks
- **Detached Objects**: Use `get_refreshed_object()` in Celery tasks

### Debug Tools
- `scripts/db_inspect.py` - Inspect current database state
- `scripts/query_tags.py` - Debug tag-related tables
- Database logs via `./opentr.sh logs postgres`

## Performance Considerations

### Connection Pooling
```python
# Engine configuration for optimal performance
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,        # Connection pool size
    max_overflow=30,     # Additional connections when pool is full
    pool_pre_ping=True,  # Validate connections before use
    pool_recycle=3600    # Recycle connections every hour
)
```

### Session Best Practices
- Keep sessions short-lived
- Avoid long-running transactions
- Use bulk operations for large datasets
- Implement proper error handling and rollback

### Query Optimization
- Use eager loading for related objects
- Implement pagination for large result sets
- Use indexes for frequently queried columns
- Monitor query performance with logging

## References

- [SQLAlchemy Session Documentation](https://docs.sqlalchemy.org/en/14/orm/session_basics.html)
- [FastAPI Database Tutorial](https://fastapi.tiangolo.com/tutorial/sql-databases/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Connection Pooling](https://docs.sqlalchemy.org/en/14/core/pooling.html)

---

The database layer provides a robust foundation for data persistence with proper session management, transaction handling, and development/production workflow support.