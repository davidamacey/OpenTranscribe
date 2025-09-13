<div align="center">
  <img src="../../assets/logo-banner.png" alt="OpenTranscribe Logo" width="200">
  
  # Alembic Database Migration Management
</div>

## Database Initialization Approach

OpenTranscribe uses a hybrid approach to database management:

1. **Development & Testing Phases**: The `database/init_db.sql` file is considered the source of truth for the database schema. This approach allows for rapid iterations during development.

2. **Production & Post-Release**: Once the application reaches a stable release, we will use Alembic migrations for all schema changes to ensure proper versioning and backward compatibility.

## Current Setup

During development:
- The `./opentr.sh reset dev` script uses `database/init_db.sql` to initialize the database with a clean schema
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

## Future Migration Approach

When the application reaches the release phase:
- We will use Alembic to manage all database migrations
- The workflow will be:
  1. Make changes to SQLAlchemy models
  2. Generate migration scripts with `alembic revision --autogenerate`
  3. Review and edit the generated migration as needed
  4. Apply migrations with `alembic upgrade head`

## Speaker Identification System

The application uses a UUID-based system to track speakers across different videos:
- Each speaker has a unique UUID
- In the UI, speakers are displayed with either:
  - Their original label (SPEAKER_01, SPEAKER_02, etc.)
  - A user-assigned display name (if set)
- When a user identifies a speaker in one video and assigns a name, the system can link that speaker to appearances in other videos

## Maintaining Database Consistency

- Always check for any schema changes in SQLAlchemy models and update init_db.sql accordingly
- Keep the schema in the SQL file and the SQLAlchemy models in sync
- Document any breaking changes to the schema
