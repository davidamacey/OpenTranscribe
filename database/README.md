<div align="center">
  <img src="../assets/logo-banner.png" alt="OpenTranscribe Logo" width="300">

  # Database Schema & Initialization
</div>

This directory contains the database schema initialization scripts and documentation for OpenTranscribe.

## 📁 Contents

```
database/
├── init_db.sql    # Complete database schema definition
└── README.md      # This documentation
```

## 🗄️ Database Schema Overview

OpenTranscribe uses PostgreSQL as its primary database with a comprehensive schema supporting:

### Core Tables

#### **Users & Authentication**
- **`users`**: User accounts with role-based access control
- **`user_settings`**: User-specific configuration storage (recording preferences, UI settings)

#### **Media & Content Management**
- **`media_files`**: Core media file metadata with processing status
- **`transcript_segments`**: Word-level transcript data with precise timing
- **`speakers`**: Speaker identification and cross-video matching
- **`comments`**: Time-stamped user annotations
- **`tags`**: Content organization and categorization
- **`collections`**: File organization into themed groups

#### **AI-Powered Features**
- **`user_llm_configurations`**: LLM provider settings with encrypted API keys
- **`summary_prompts`**: Custom AI prompts for different content types
- **`file_summaries`**: AI-generated summaries with BLUF format
- **`summary_opensearch`**: Integration with OpenSearch for summary indexing

### Key Features

#### **Enhanced User Settings System**
- **Recording Preferences**: Duration limits, quality settings, auto-stop configuration
- **LLM Integration**: Multi-provider support (OpenAI, Claude, vLLM, Ollama, etc.)
- **Custom Prompts**: User-defined templates for different content types

#### **Advanced Media Processing**
- **YouTube Integration**: URL processing with metadata extraction
- **Progress Tracking**: Granular status updates for long-running operations
- **Error Recovery**: Comprehensive error handling and retry mechanisms

#### **Real-Time Features**
- **WebSocket Notifications**: Persistent notification system
- **Upload Progress**: Concurrent file processing with queue management
- **AI Processing Status**: Real-time updates for transcription and summarization

## 🚀 Database Initialization

### Development Setup

The database is initialized using the `init_db.sql` script during development:

```bash
# Reset and initialize development database
./opentr.sh reset dev
```

**⚠️ WARNING**: This command deletes ALL existing data and recreates the database from scratch.

### Schema Management Approach

#### Development Phase (Current)
- **Source of Truth**: `database/init_db.sql` contains the complete schema
- **Rapid Iteration**: Direct SQL modification for fast development cycles
- **Easy Reset**: Simple database recreation for testing and development

#### Production Phase (Future)
- **Migration-Based**: Alembic migrations for version control and deployment
- **Backward Compatibility**: Incremental schema changes with rollback support
- **Production Safety**: Tested migrations with backup and recovery procedures

## 📊 Schema Details

### User Management

```sql
-- Core user table with role-based access
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Flexible user settings with key-value storage
CREATE TABLE user_settings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    setting_key VARCHAR(100) NOT NULL,
    setting_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### AI Integration

```sql
-- LLM provider configurations with encrypted storage
CREATE TABLE user_llm_configurations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    model_name VARCHAR(100),
    api_key_encrypted TEXT,
    base_url VARCHAR(500),
    -- Additional configuration fields...
);

-- Custom AI prompts for different content types
CREATE TABLE summary_prompts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    prompt_text TEXT NOT NULL,
    content_type VARCHAR(50) DEFAULT 'general',
    is_active BOOLEAN DEFAULT TRUE,
    -- Metadata fields...
);
```

### Media Processing

```sql
-- Enhanced media files with comprehensive metadata
CREATE TABLE media_files (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255),
    file_size BIGINT,
    duration FLOAT,
    status VARCHAR(50) DEFAULT 'pending',
    -- Processing metadata...
    youtube_url VARCHAR(500),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    -- Timestamps...
);

-- AI-generated summaries with status tracking
CREATE TABLE file_summaries (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES media_files(id) ON DELETE CASCADE,
    summary_data JSONB,
    processing_status VARCHAR(50) DEFAULT 'pending',
    -- Additional fields...
);
```

## 🔧 Database Operations

### Common Operations

#### Reset Development Database
```bash
# Complete database reset (DESTRUCTIVE)
./opentr.sh reset dev
```

#### Check Database Status
```bash
# Inspect database state
python backend/scripts/db_inspect.py
```

#### Create Admin User
```bash
# Create initial admin account
python backend/scripts/create_admin.py
```

### Production Operations (Future)

#### Apply Migrations
```bash
# Apply all pending migrations
alembic upgrade head
```

#### Backup Database
```bash
# Create database backup
./opentr.sh backup
```

#### Restore Database
```bash
# Restore from backup
./opentr.sh restore backups/backup_file.sql
```

## 📈 Performance Optimizations

### Indexing Strategy
- **Primary Keys**: All tables have efficient primary key indexes
- **Foreign Keys**: Automatic indexing on all foreign key relationships
- **Search Fields**: Optimized indexes for frequently searched columns
- **Composite Indexes**: Multi-column indexes for complex queries

### Connection Management
- **Connection Pooling**: Efficient database connection reuse
- **Transaction Management**: Proper isolation and rollback handling
- **Session Optimization**: Context-aware session management

## 🔒 Security Features

### Data Protection
- **API Key Encryption**: All sensitive credentials encrypted at rest
- **User Isolation**: Row-level security for multi-tenant data
- **Input Validation**: Comprehensive SQL injection protection
- **Audit Logging**: Track sensitive data modifications

### Access Control
- **Role-Based Permissions**: Admin and user role separation
- **Resource Ownership**: Users can only access their own data
- **Session Security**: Secure JWT-based authentication

## 🚨 Migration Strategy

### Transition to Production

When moving to production deployment:

1. **Schema Finalization**: Ensure `init_db.sql` represents final development schema
2. **Base Migration Creation**: Generate Alembic migration matching current schema
3. **Production Deployment**: Apply base migration to production database
4. **Future Changes**: Use Alembic migrations for all subsequent schema modifications

### Migration Best Practices
- **Review Generated Migrations**: Always verify auto-generated migration scripts
- **Test on Staging**: Validate migrations on staging environment first
- **Backup Before Migration**: Create full database backup before applying changes
- **Rollback Planning**: Ensure rollback procedures are tested and documented

## 🛠️ Development Guidelines

### Schema Modifications

When modifying the database schema:

1. **Update `init_db.sql`**: Make changes to the master schema file
2. **Update SQLAlchemy Models**: Modify corresponding models in `backend/app/models/`
3. **Update Pydantic Schemas**: Adjust validation schemas in `backend/app/schemas/`
4. **Reset Development Database**: Run `./opentr.sh reset dev` to apply changes
5. **Test Thoroughly**: Verify all functionality works with new schema

### Best Practices
- **Keep Schemas in Sync**: Ensure SQL, SQLAlchemy, and Pydantic schemas match
- **Document Changes**: Add comments for complex schema modifications
- **Test Data Migration**: Ensure existing data can be migrated safely
- **Performance Impact**: Consider query performance implications of schema changes

## 📚 References

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [SQLAlchemy ORM Documentation](https://docs.sqlalchemy.org/)
- [Alembic Migration Documentation](https://alembic.sqlalchemy.org/)
- [FastAPI Database Integration](https://fastapi.tiangolo.com/tutorial/sql-databases/)

---

The database layer provides a robust foundation for all OpenTranscribe functionality with comprehensive schema design, security features, and development workflow support.