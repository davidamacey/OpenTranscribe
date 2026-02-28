<div align="center">
  <img src="../../assets/logo-banner.png" alt="OpenTranscribe Logo" width="200">

  # Alembic Database Migration Management
</div>

## Database Initialization Approach

OpenTranscribe uses a hybrid approach to database management:

1. **All Environments**: The Alembic migration chain in `backend/alembic/versions/` is the sole authority for the database schema. The bootstrap migration (`v000_bootstrap.py`) creates the full schema from scratch, and subsequent migrations handle schema evolution.

2. **Legacy Reference**: The `database/init_db.sql` file is retained for historical reference only and is no longer used for schema initialization.

## Current Setup

Current setup:
- The `./opentr.sh reset dev` script drops the database and runs the full Alembic migration chain (`alembic upgrade head`) to recreate the schema
- The script also calls `app/initial_data.py` to create initial test data and admin user
- The database can be completely reset using: `./opentr.sh reset dev` (⚠️ **WARNING**: This deletes ALL data)
- Individual services can be restarted without data loss using: `./opentr.sh restart-backend`

### Enhanced Database Features

The current schema includes several new features and improvements:

#### User Settings System
- **User-specific settings** for recording preferences (duration, quality, auto-stop)
- **LLM configurations** with encrypted API key storage per user
- **Custom AI prompts** for different content types and workflows

#### Advanced AI Integration
- **LLM provider settings** with multi-provider support (OpenAI, Claude, vLLM, Ollama, etc.)
- **Summarization history** tracking with versioning and status management
- **Custom prompt templates** for different content types (meetings, interviews, podcasts)

#### Enhanced Media Processing
- **YouTube URL processing** with metadata extraction and enhanced error handling
- **Improved file upload handling** with concurrent processing and retry logic
- **Enhanced notification system** with WebSocket integration and progress tracking

## Migration Workflow

All schema changes use Alembic migrations:
1. Create a new migration file in `backend/alembic/versions/`
2. Update SQLAlchemy models in `backend/app/models/` to match
3. Update Pydantic schemas in `backend/app/schemas/` if needed
4. Update `backend/app/db/migrations.py` detection logic for the new version
5. Test with `./opentr.sh reset dev` (runs full migration chain from scratch)

## Speaker Identification System

The application uses a UUID-based system to track speakers across different videos:
- Each speaker has a unique UUID
- In the UI, speakers are displayed with either:
  - Their original label (SPEAKER_01, SPEAKER_02, etc.)
  - A user-assigned display name (if set)
- When a user identifies a speaker in one video and assigns a name, the system can link that speaker to appearances in other videos

## Maintaining Database Consistency

- Always create Alembic migrations for any schema changes
- Keep the Alembic migrations and SQLAlchemy models in sync
- Document any breaking changes to the schema
