<div align="center">
  <img src="../../../assets/logo-banner.png" alt="OpenTranscribe Logo" width="200">
  
  # Utilities Documentation
</div>

This directory contains common utilities and helper functions that provide reusable functionality across the OpenTranscribe backend application.

## 🛠️ Utilities Overview

### Design Principles
- **Reusability**: Functions and classes designed for use across multiple modules
- **Single Responsibility**: Each utility focused on one specific concern
- **Consistency**: Standardized patterns for common operations
- **Error Handling**: Robust error handling with consistent responses
- **Type Safety**: Full type hints for better development experience

## 📁 Utility Modules

```
utils/
├── auth_decorators.py      # Authentication and authorization decorators
├── db_helpers.py          # Database query utilities and helpers
├── error_handlers.py      # Standardized error handling
└── task_utils.py          # Celery task management utilities
```

## 🔐 Authentication Decorators (`auth_decorators.py`)

### Purpose
Provides reusable decorators and helpers for authentication and authorization across endpoints.

### Key Components

#### Authorization Decorators
```python
@require_file_ownership
def update_file(file_id: int, db: Session, current_user: User):
    """Decorator ensures user owns the file before proceeding."""
    
@require_admin
def admin_operation(db: Session, current_user: User):
    """Decorator ensures user has admin privileges."""
    
@require_verified_user
def verified_operation(db: Session, current_user: User):
    """Decorator ensures user account is verified."""
```

#### Authorization Helper Class
```python
class AuthorizationHelper:
    @staticmethod
    def check_file_access(db: Session, file_id: int, user: User) -> MediaFile:
        """Check if user has access to a file and return it."""
        
    @staticmethod
    def check_admin_or_owner(resource, user: User, owner_field: str = 'user_id') -> bool:
        """Check if user is admin or owns the resource."""
        
    @staticmethod
    def require_resource_access(db: Session, model_class, resource_id: int, 
                               user: User, owner_field: str = 'user_id'):
        """Generic function to check resource access."""
```

### Usage Examples
```python
# Endpoint with file ownership requirement
@router.put("/files/{file_id}")
@require_file_ownership
def update_file(
    file_id: int,
    updates: FileUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # User ownership is automatically verified
    return update_file_service(db, file_id, updates, current_user)

# Service layer with authorization helper
def get_file_with_permission_check(db: Session, file_id: int, user: User) -> MediaFile:
    return AuthorizationHelper.check_file_access(db, file_id, user)
```

### Features
- **Decorator-based Authorization**: Clean, reusable permission checks
- **Flexible Resource Access**: Generic patterns for different resource types
- **Admin/Owner Patterns**: Common authorization logic
- **Error Consistency**: Standardized 403/404 responses

## 🗄️ Database Helpers (`db_helpers.py`)

### Purpose
Provides common database query patterns, utilities, and optimizations.

### Key Components

#### Query Builders
```python
def get_user_files_query(db: Session, user_id: int) -> Query:
    """Standard query for user's files."""
    
def apply_file_filters(query: Query, **filters) -> Query:
    """Apply standard file filters to a query."""
    
def get_files_by_status(db: Session, user_id: int, status: str) -> List[MediaFile]:
    """Get files by status for a user."""
```

#### CRUD Helpers
```python
def get_or_create(db: Session, model: Type[T], defaults: Optional[dict] = None, 
                  **kwargs) -> tuple[T, bool]:
    """Get an object or create it if it doesn't exist."""
    
def safe_get_by_id(db: Session, model: Type[T], obj_id: int, 
                   user_id: Optional[int] = None) -> Optional[T]:
    """Safely get an object by ID with optional user filtering."""
    
def bulk_update(db: Session, model: Type[T], updates: List[dict], 
                id_field: str = 'id') -> bool:
    """Perform bulk updates efficiently."""
```

#### Specialized Queries
```python
def get_file_with_transcript_count(db: Session, file_id: int, user_id: int) -> tuple[MediaFile, int]:
    """Get a file with its transcript segment count."""
    
def get_unique_speakers_for_file(db: Session, file_id: int) -> List[Speaker]:
    """Get unique speakers that appear in a specific file."""
    
def get_user_file_stats(db: Session, user_id: int) -> dict:
    """Get comprehensive file statistics for a user."""
```

#### Tag Management
```python
def get_file_tags(db: Session, file_id: int) -> List[str]:
    """Get tag names for a file."""
    
def add_tags_to_file(db: Session, file_id: int, tag_names: List[str]) -> bool:
    """Add tags to a file, creating tags if they don't exist."""
    
def remove_tags_from_file(db: Session, file_id: int, tag_names: List[str]) -> bool:
    """Remove tags from a file."""
```

### Usage Examples
```python
# Service layer using database helpers
class FileService:
    def get_user_files_with_filters(self, user: User, filters: dict) -> List[MediaFile]:
        query = get_user_files_query(self.db, user.id)
        query = apply_file_filters(query, **filters)
        return query.order_by(MediaFile.upload_time.desc()).all()
    
    def ensure_tag_exists(self, tag_name: str) -> Tag:
        tag, created = get_or_create(self.db, Tag, name=tag_name)
        if created:
            logger.info(f"Created new tag: {tag_name}")
        return tag
```

### Features
- **Performance Optimization**: Efficient queries with proper joins
- **Reusable Patterns**: Common query patterns across the application
- **Type Safety**: Full generic type support
- **Error Handling**: Graceful handling of database errors
- **Batch Operations**: Efficient bulk operations

## 🚨 Error Handlers (`error_handlers.py`)

### Purpose
Provides standardized error handling patterns and HTTP exception generation.

### Key Components

#### Error Handler Class
```python
class ErrorHandler:
    @staticmethod
    def database_error(operation: str, error: Exception) -> HTTPException:
        """Create standardized database error response."""
        
    @staticmethod
    def validation_error(message: str) -> HTTPException:
        """Create standardized validation error response."""
        
    @staticmethod
    def not_found_error(resource: str) -> HTTPException:
        """Create standardized not found error response."""
        
    @staticmethod
    def unauthorized_error(message: str = "Access denied") -> HTTPException:
        """Create standardized unauthorized error response."""
        
    @staticmethod
    def file_processing_error(operation: str, error: Exception) -> HTTPException:
        """Create standardized file processing error response."""
```

#### Error Handling Decorators
```python
def handle_database_errors(func: Callable) -> Callable:
    """Decorator to handle common database errors."""
    
def handle_not_found(resource_name: str = "Resource") -> Callable:
    """Decorator factory to handle resource not found errors."""
```

### Usage Examples
```python
# Service layer error handling
class FileService:
    def get_file_by_id(self, file_id: int, user: User) -> MediaFile:
        file_obj = self.db.query(MediaFile).filter(
            MediaFile.id == file_id,
            MediaFile.user_id == user.id
        ).first()
        
        if not file_obj:
            raise ErrorHandler.not_found_error("File")
        
        return file_obj
    
    def process_file_upload(self, file_data: bytes) -> MediaFile:
        try:
            # File processing logic
            return processed_file
        except ValidationError as e:
            raise ErrorHandler.validation_error(str(e))
        except StorageError as e:
            raise ErrorHandler.file_processing_error("upload", e)

# Endpoint with error decorator
@handle_database_errors
@router.get("/files/{file_id}")
def get_file(file_id: int, db: Session = Depends(get_db)):
    # Database errors automatically handled
    return db.query(MediaFile).filter(MediaFile.id == file_id).first()
```

### Features
- **Consistent Responses**: Standardized error format across API
- **Logging Integration**: Automatic error logging with context
- **HTTP Status Codes**: Proper status codes for different error types
- **Decorator Support**: Clean error handling with decorators
- **Error Classification**: Different handlers for different error types

## ⚙️ Task Utilities (`task_utils.py`)

### Purpose
Provides utilities for Celery task management and monitoring.

### Key Components

#### Task Management
```python
def create_task_record(db: Session, celery_task_id: str, user_id: int, 
                      media_file_id: int, task_type: str) -> Task:
    """Create a new task record in the database."""
    
def update_task_status(db: Session, task_id: str, status: str, progress: float = None, 
                      error_message: str = None, completed: bool = False) -> None:
    """Update task status in the database."""
    
def update_media_file_status(db: Session, file_id: int, status: FileStatus) -> None:
    """Update media file status."""
```

#### Task Monitoring
```python
def get_task_progress(db: Session, task_id: str) -> Optional[Dict[str, Any]]:
    """Get current task progress and status."""
    
def cancel_user_tasks(db: Session, user_id: int, task_type: str = None) -> int:
    """Cancel all pending tasks for a user."""
    
def cleanup_completed_tasks(db: Session, older_than_days: int = 7) -> int:
    """Clean up old completed tasks."""
```

### Usage Examples
```python
# Task creation in service layer
class TranscriptionService:
    def start_transcription(self, file_id: int, user: User) -> Dict[str, Any]:
        # Dispatch Celery task
        task = transcribe_audio_task.delay(file_id)
        
        # Create database record
        create_task_record(self.db, task.id, user.id, file_id, "transcription")
        
        return {"task_id": task.id, "status": "started"}

# Task progress tracking in background task
@celery_app.task(bind=True)
def long_running_task(self, data):
    task_id = self.request.id
    
    # Initialize task
    with session_scope() as db:
        update_task_status(db, task_id, "in_progress", progress=0.0)
    
    # Processing steps with progress updates
    for i, item in enumerate(data):
        process_item(item)
        progress = (i + 1) / len(data)
        
        with session_scope() as db:
            update_task_status(db, task_id, "in_progress", progress=progress)
    
    # Complete task
    with session_scope() as db:
        update_task_status(db, task_id, "completed", progress=1.0, completed=True)
```

### Features
- **Task Lifecycle Management**: Creation, progress tracking, completion
- **Database Integration**: Task state persistence
- **Progress Monitoring**: Real-time progress updates
- **Error Tracking**: Error message storage and retrieval
- **Cleanup Utilities**: Maintenance operations for task history

## 🔧 Common Patterns

### Dependency Injection Pattern
```python
# Service factory for dependency injection
def get_file_service(db: Session = Depends(get_db)) -> FileService:
    """Factory function for FileService dependency injection."""
    return FileService(db)

# Usage in endpoints
@router.get("/files")
def list_files(
    file_service: FileService = Depends(get_file_service),
    current_user: User = Depends(get_current_active_user)
):
    return file_service.get_user_files(current_user)
```

### Session Management Pattern
```python
# Context manager for database sessions
@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

# Usage in background tasks
def background_operation(data):
    with session_scope() as db:
        # Database operations with automatic commit/rollback
        process_data(db, data)
```

### Validation Pattern
```python
# Input validation with error handling
def validate_file_upload(file: UploadFile) -> None:
    """Validate uploaded file with consistent error responses."""
    if not file.filename:
        raise ErrorHandler.validation_error("Filename is required")
    
    if file.size > MAX_FILE_SIZE:
        raise ErrorHandler.validation_error(f"File size exceeds {MAX_FILE_SIZE} bytes")
    
    allowed_types = ["audio/", "video/"]
    if not any(file.content_type.startswith(t) for t in allowed_types):
        raise ErrorHandler.validation_error("File must be audio or video format")
```

## 🧪 Testing Utilities

### Test Helper Functions
```python
# Test utilities for database operations
def create_test_user(db: Session, email: str = "test@example.com") -> User:
    """Create a test user for testing."""
    return get_or_create(db, User, email=email, hashed_password="test_hash")[0]

def create_test_file(db: Session, user: User, filename: str = "test.mp4") -> MediaFile:
    """Create a test media file for testing."""
    return get_or_create(db, MediaFile, 
                        filename=filename, 
                        user_id=user.id, 
                        storage_path=f"/test/{filename}")[0]

# Mock utilities for external services
@contextmanager
def mock_external_services():
    """Mock external service calls for testing."""
    with patch('app.services.minio_service.upload_file'), \
         patch('app.services.opensearch_service.index_transcript'), \
         patch('app.tasks.transcription.transcribe_audio_task.delay'):
        yield
```

### Testing Patterns
```python
def test_with_error_handling():
    """Test error handling utilities."""
    with pytest.raises(HTTPException) as exc_info:
        raise ErrorHandler.not_found_error("TestResource")
    
    assert exc_info.value.status_code == 404
    assert "TestResource not found" in str(exc_info.value.detail)

def test_database_helpers(db_session, test_user):
    """Test database helper functions."""
    # Test get_or_create
    tag, created = get_or_create(db_session, Tag, name="test-tag")
    assert created is True
    
    # Test safe_get_by_id
    retrieved_tag = safe_get_by_id(db_session, Tag, tag.id)
    assert retrieved_tag.name == "test-tag"
```

## 🚀 Performance Considerations

### Caching Strategies
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_user_permissions_cached(user_id: int) -> Dict[str, bool]:
    """Cache user permissions to avoid repeated database queries."""
    with session_scope() as db:
        user = safe_get_by_id(db, User, user_id)
        return {
            "is_admin": user.is_superuser,
            "is_active": user.is_active,
            "can_upload": user.is_active and not user.is_suspended
        }
```

### Query Optimization
```python
def optimized_user_files_query(db: Session, user_id: int) -> Query:
    """Optimized query with eager loading for better performance."""
    return db.query(MediaFile)\
        .options(
            joinedload(MediaFile.transcript_segments),
            selectinload(MediaFile.file_tags).joinedload(FileTag.tag)
        )\
        .filter(MediaFile.user_id == user_id)
```

## 🔧 Adding New Utilities

### Utility Creation Guidelines
1. **Single Purpose**: Each utility should have one clear responsibility
2. **Type Safety**: Include comprehensive type hints
3. **Error Handling**: Use consistent error handling patterns
4. **Documentation**: Clear docstrings with examples
5. **Testing**: Comprehensive unit tests
6. **Reusability**: Design for use across multiple modules

### Utility Template
```python
from typing import Optional, List, TypeVar
from sqlalchemy.orm import Session

from app.utils.error_handlers import ErrorHandler

T = TypeVar('T')

def new_utility_function(db: Session, param1: str, param2: Optional[int] = None) -> T:
    """
    Description of what this utility does.
    
    Args:
        db: Database session
        param1: Description of parameter
        param2: Optional parameter description
        
    Returns:
        Description of return value
        
    Raises:
        HTTPException: When validation fails
        
    Example:
        >>> result = new_utility_function(db, "test", 123)
        >>> assert result is not None
    """
    try:
        # Validation
        if not param1:
            raise ErrorHandler.validation_error("param1 is required")
        
        # Main logic
        result = perform_operation(param1, param2)
        
        # Return result
        return result
        
    except Exception as e:
        logger.error(f"Error in new_utility_function: {e}")
        raise ErrorHandler.database_error("utility operation", e)
```

---

The utilities module provides a solid foundation of reusable components that promote consistency, reduce code duplication, and improve maintainability across the OpenTranscribe backend.