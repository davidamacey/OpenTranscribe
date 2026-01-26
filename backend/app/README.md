<div align="center">
  <img src="../../assets/logo-banner.png" alt="OpenTranscribe Logo" width="300">

  # Application Architecture
</div>

This directory contains the main OpenTranscribe application code, organized following modern FastAPI and Python best practices.

## 🏗️ Architecture Overview

The application follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────┐
│   API Layer    │  ← HTTP endpoints, request/response handling
├─────────────────┤
│ Service Layer   │  ← Business logic, orchestration
├─────────────────┤
│  Data Layer     │  ← Models, schemas, database operations
├─────────────────┤
│ Infrastructure  │  ← External services, utilities, config
└─────────────────┘
```

## 📁 Directory Structure

```
app/
├── api/                    # 🌐 API Layer
│   ├── endpoints/         # Route handlers organized by resource
│   │   ├── files/        # Modular file management
│   │   │   ├── streaming.py    # Video/audio streaming support
│   │   │   ├── upload.py       # Enhanced upload handling
│   │   │   └── url_processing.py # URL processing endpoints
│   │   ├── admin.py      # Admin operations
│   │   ├── auth.py       # Authentication
│   │   ├── comments.py   # Comment system
│   │   ├── search.py     # Search functionality
│   │   ├── speakers.py   # Speaker management
│   │   ├── summarization.py    # NEW: LLM-powered summarization
│   │   ├── tags.py       # Tag operations
│   │   ├── tasks.py      # Task monitoring
│   │   ├── user_settings.py    # NEW: User settings management
│   │   └── users.py      # User management
│   ├── router.py         # Main API router configuration
│   └── websockets.py     # Real-time WebSocket handlers
├── auth/                  # 🔐 Authentication & Authorization
│   └── direct_auth.py    # Authentication utilities
├── core/                  # ⚙️ Core Configuration
│   ├── celery.py         # Background task configuration
│   ├── config.py         # Application settings
│   ├── constants.py      # NEW: Application constants and defaults
│   └── security.py       # Security utilities (JWT, hashing)
├── db/                    # 🗄️ Database Layer
│   ├── base.py           # Database connection and base setup
│   └── session_utils.py  # Session management utilities
├── middleware/            # 🔄 Request/Response Middleware
│   ├── __init__.py
│   └── route_fixer.py    # URL normalization middleware
├── models/                # 📊 Data Models (SQLAlchemy ORM)
│   ├── media.py          # Media file and transcript models
│   └── user.py           # User and authentication models
├── schemas/               # 📝 Data Validation (Pydantic)
│   ├── media.py          # Media file schemas
│   └── user.py           # User schemas
├── services/              # 🔧 Business Logic Layer
│   ├── file_service.py        # File management service
│   ├── transcription_service.py # Transcription workflows
│   ├── minio_service.py       # Object storage service
│   └── opensearch_service.py  # Search service
├── tasks/                 # ⚡ Background Processing
│   ├── transcription/    # Modular transcription pipeline
│   │   └── notifications.py # Enhanced WebSocket notifications
│   ├── analytics.py      # Analytics processing
│   ├── summarization.py  # Multi-provider LLM summarization
│   ├── transcription.py  # Main transcription router
│   └── youtube_processing.py # NEW: Enhanced YouTube URL processing
├── utils/                 # 🛠️ Common Utilities
│   ├── auth_decorators.py    # Authorization decorators
│   ├── db_helpers.py         # Database query helpers
│   ├── error_handlers.py     # Error handling utilities
│   ├── filename.py           # NEW: Filename processing utilities
│   ├── task_utils.py         # Task management utilities
│   └── thumbnail.py          # Enhanced thumbnail generation
├── main.py               # 🚀 FastAPI Application Entry Point
└── initial_data.py       # 📋 Database Initialization
```

## 🔄 Request Flow

### Typical API Request Flow
```
1. HTTP Request → FastAPI Router
2. Router → Endpoint Handler (api/endpoints/)
3. Endpoint → Service Layer (services/)
4. Service → Database (models/) + External Services
5. Response ← Pydantic Schema (schemas/)
6. HTTP Response ← FastAPI
```

### Background Task Flow
```
1. API Request → Endpoint
2. Endpoint → Task Dispatch (tasks/)
3. Celery Worker → Task Processing
4. Task → Services + Models
5. WebSocket Notification → Client
```

## 🌐 API Layer (`api/`)

### Organization Principle
- **Resource-based routing**: Each file handles one resource type
- **Modular endpoints**: Complex endpoints split into sub-modules
- **Consistent patterns**: Standard CRUD operations
- **Clear separation**: HTTP handling separate from business logic

### Endpoint Structure
```python
# Standard endpoint pattern
@router.get("/resource/{id}", response_model=ResourceSchema)
def get_resource(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific resource by ID."""
    return resource_service.get_by_id(db, id, current_user)
```

### Files Module (`api/endpoints/files/`)
Special modular organization for complex file operations:
- `upload.py` - Enhanced file upload processing with concurrency control
- `crud.py` - Basic CRUD operations
- `filtering.py` - Advanced filtering logic
- `streaming.py` - Video/audio streaming support
- `url_processing.py` - **NEW**: Enhanced URL processing for video links

### New API Endpoints
- **User Settings (`user_settings.py`)**:
  - Recording preferences management
  - User-specific configuration storage
  - Settings validation and defaults
- **Summarization (`summarization.py`)**:
  - Multi-provider LLM integration
  - BLUF format summary generation
  - Intelligent section processing

## 🔧 Service Layer (`services/`)

### Purpose
- **Business logic encapsulation**: Keep endpoints thin
- **Reusable operations**: Share logic between endpoints
- **Transaction management**: Handle database transactions
- **External service integration**: Manage third-party APIs

### Service Pattern
```python
class ResourceService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: CreateSchema, user: User) -> Resource:
        """Create a new resource with business logic."""
        # Validation
        # Business rules
        # Database operations
        # Return result
```

## 📊 Data Layer (`models/` & `schemas/`)

### Models (`models/`)
- **SQLAlchemy ORM models**: Database table definitions
- **Relationships**: Foreign keys and joins
- **Constraints**: Database-level validation
- **Indexes**: Performance optimization

### Schemas (`schemas/`)
- **Pydantic models**: Request/response validation
- **Type safety**: Runtime type checking
- **Serialization**: JSON conversion
- **Documentation**: Automatic API docs

### Model-Schema Relationship
```python
# SQLAlchemy Model (database)
class MediaFile(Base):
    __tablename__ = "media_file"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)

# Pydantic Schema (API)
class MediaFileResponse(BaseModel):
    id: int
    filename: str

    class Config:
        from_attributes = True  # Enable ORM mode
```

## ⚡ Background Tasks (`tasks/`)

### Organization
- **Modular design**: Complex tasks split into modules
- **Single responsibility**: Each task has one clear purpose
- **Error handling**: Robust error recovery
- **Progress tracking**: Real-time status updates

### Transcription Pipeline (`tasks/transcription/`)
```
transcription/
├── core.py              # Main orchestrator
├── metadata_extractor.py # File metadata processing
├── audio_processor.py   # Audio conversion/extraction
├── whisperx_service.py  # AI transcription service
├── speaker_processor.py # Speaker diarization
├── storage.py          # Database storage
└── notifications.py    # WebSocket updates
```

## 🛠️ Utilities (`utils/`)

### Common Patterns
- **Error handling**: Standardized HTTP exceptions
- **Authorization**: Reusable permission decorators
- **Database helpers**: Common query patterns
- **Task management**: Celery task utilities

### Usage Examples
```python
# Error handling
from app.utils.error_handlers import ErrorHandler
raise ErrorHandler.not_found_error("Resource")

# Authorization
from app.utils.auth_decorators import require_file_ownership
@require_file_ownership
def update_file(...): pass

# Database helpers
from app.utils.db_helpers import get_user_files_query
query = get_user_files_query(db, user_id)
```

## ⚙️ Core Configuration (`core/`)

### Components
- **config.py**: Environment-based settings
- **security.py**: JWT and password utilities
- **celery.py**: Background task configuration

### Configuration Pattern
```python
# Settings management
from app.core.config import settings

# Use environment variables
database_url = settings.DATABASE_URL
secret_key = settings.SECRET_KEY
```

## 🔐 Authentication & Authorization

### Authentication Flow
1. **Login**: Username/password → JWT token
2. **Request**: Bearer token in Authorization header
3. **Validation**: JWT signature and expiration
4. **User**: Extract user info from token

### Authorization Patterns
- **Ownership**: Users can only access their own resources
- **Role-based**: Admin vs regular user permissions
- **Resource-specific**: File-level access control

## 🔄 Middleware (`middleware/`)

### Current Middleware
- **Route fixer**: URL normalization and trailing slash handling
- **CORS**: Cross-origin request handling (FastAPI built-in)
- **Authentication**: JWT token validation (dependency injection)

## 📋 Database Initialization (`initial_data.py`)

### Purpose
- **Bootstrap data**: Create initial admin user
- **Development setup**: Ensure required data exists
- **Safe execution**: Idempotent operations (can run multiple times)

## 🚀 Application Entry Point (`main.py`)

### Application Setup
```python
# FastAPI app creation
app = FastAPI(title="OpenTranscribe API")

# Middleware registration
app.add_middleware(...)

# Router inclusion
app.include_router(api_router, prefix="/api")

# Startup events
@app.on_event("startup")
async def startup_event():
    # Initialize services
    pass
```

## 📖 Development Guidelines

### Adding New Features

1. **Models**: Define database structure in `models/`
2. **Schemas**: Create validation models in `schemas/`
3. **Services**: Implement business logic in `services/`
4. **Endpoints**: Add API routes in `api/endpoints/`
5. **Tests**: Add comprehensive tests

### Code Organization Rules

1. **Keep endpoints thin**: Move logic to services
2. **Use dependency injection**: FastAPI's `Depends()`
3. **Handle errors gracefully**: Use utility error handlers
4. **Document everything**: Docstrings and type hints
5. **Follow patterns**: Consistency across codebase

### Import Organization
```python
# Standard library
import os
from typing import List

# Third-party
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

# Local application
from app.core.config import settings
from app.models.user import User
from app.schemas.user import UserCreate
```

---

This architecture provides a solid foundation for scalable, maintainable FastAPI applications with clear separation of concerns and modern Python practices.
