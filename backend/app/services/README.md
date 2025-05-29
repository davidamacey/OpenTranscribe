# Services Layer Documentation

The services layer provides a clean abstraction for business logic, separating it from API endpoints and database operations. This layer orchestrates complex operations, manages transactions, and provides reusable business functionality.

## 🎯 Service Layer Principles

### Design Goals
- **Business Logic Encapsulation**: Keep complex operations out of endpoints
- **Reusability**: Share common operations across multiple endpoints
- **Transaction Management**: Handle database transactions consistently
- **External Service Integration**: Manage third-party API interactions
- **Error Handling**: Provide consistent error handling patterns
- **Testing**: Enable easier unit testing of business logic

### Architecture Pattern
```
API Endpoints → Service Layer → Data Layer (Models/External APIs)
     ↓              ↓                    ↓
  HTTP Logic   Business Logic      Data Operations
```

## 📁 Service Structure

```
services/
├── file_service.py           # File management operations
├── transcription_service.py  # Transcription workflow management
├── minio_service.py          # Object storage operations
└── opensearch_service.py     # Search and indexing operations
```

## 🔧 Service Design Patterns

### Base Service Pattern
```python
class BaseService:
    """Base service class with common patterns."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def _validate_user_access(self, resource, user: User) -> None:
        """Common access validation pattern."""
        if resource.user_id != user.id and not user.is_superuser:
            raise ErrorHandler.unauthorized_error("Access denied")
    
    def _handle_database_error(self, operation: str, error: Exception):
        """Common database error handling."""
        logger.error(f"Database error in {operation}: {error}")
        self.db.rollback()
        raise ErrorHandler.database_error(operation, error)
```

### Service Method Pattern
```python
def service_method(self, data: InputSchema, user: User) -> OutputModel:
    """Standard service method pattern."""
    try:
        # 1. Validation
        self._validate_input(data)
        
        # 2. Authorization
        self._check_permissions(user)
        
        # 3. Business Logic
        result = self._perform_operation(data)
        
        # 4. Database Transaction
        self.db.commit()
        
        # 5. Return Result
        return result
        
    except Exception as e:
        self.db.rollback()
        raise self._handle_error(e)
```

## 📂 File Service (`file_service.py`)

### Purpose
Manages all file-related operations including upload, metadata management, and file lifecycle.

### Key Operations
```python
class FileService:
    async def upload_file(self, file: UploadFile, user: User) -> MediaFile:
        """Complete file upload pipeline."""
        # Validation, storage, database record creation
    
    def get_user_files(self, user: User, filters: dict) -> List[MediaFile]:
        """Retrieve files with advanced filtering."""
        # Query building, permission checking, filtering
    
    def update_file_metadata(self, file_id: int, updates: MediaFileUpdate, user: User) -> MediaFile:
        """Update file metadata with validation."""
        # Authorization, validation, database update
    
    def delete_file(self, file_id: int, user: User) -> None:
        """Complete file deletion (storage + database)."""
        # Authorization, storage cleanup, database deletion
```

### Usage Example
```python
# In API endpoint
@router.post("/files", response_model=MediaFileSchema)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    file_service = FileService(db)
    return await file_service.upload_file(file, current_user)
```

### Features
- **Complete Upload Pipeline**: Validation → Storage → Database → Task Dispatch
- **Advanced Filtering**: Complex query building with multiple filter criteria
- **Permission Management**: User ownership validation
- **Storage Integration**: MinIO operations with error handling
- **Tag Management**: File tagging operations
- **Statistics**: User file statistics and analytics

## 🎙️ Transcription Service (`transcription_service.py`)

### Purpose
Orchestrates transcription workflows, manages AI processing tasks, and handles speaker management.

### Key Operations
```python
class TranscriptionService:
    def start_transcription(self, file_id: int, user: User) -> Dict[str, Any]:
        """Initiate transcription process."""
        # Validation, task creation, Celery dispatch
    
    def get_transcription_status(self, file_id: int, user: User) -> Dict[str, Any]:
        """Get detailed transcription progress."""
        # Task status, progress tracking, error reporting
    
    def update_transcript_segments(self, file_id: int, updates: List[TranscriptSegmentUpdate], user: User) -> List[TranscriptSegment]:
        """Bulk update transcript segments."""
        # Authorization, validation, batch updates
    
    def merge_speakers(self, primary_id: int, secondary_id: int, user: User) -> Speaker:
        """Merge two speakers across all segments."""
        # Complex database operations, referential integrity
```

### Workflow Management
```python
# Transcription Pipeline
def start_transcription(self, file_id: int, user: User):
    # 1. Validate file exists and is processable
    file_obj = self._validate_file_for_transcription(file_id, user)
    
    # 2. Check current status
    if file_obj.status not in [FileStatus.PENDING, FileStatus.ERROR]:
        raise ValidationError("File cannot be transcribed in current state")
    
    # 3. Dispatch background task
    task = transcribe_audio_task.delay(file_id)
    
    # 4. Return task information
    return {"task_id": task.id, "status": "started"}
```

### Features
- **Task Orchestration**: Celery task management and monitoring
- **Progress Tracking**: Real-time transcription progress
- **Speaker Management**: AI-generated speaker identification and merging
- **Segment Editing**: Transcript text and timing modifications
- **Cross-file Analytics**: Speaker consistency across multiple files
- **Error Recovery**: Robust error handling and retry mechanisms

## 🗄️ MinIO Service (`minio_service.py`)

### Purpose
Handles all object storage operations including file upload, download, streaming, and management.

### Key Operations
```python
def upload_file(file_content: IO, file_size: int, object_name: str, content_type: str) -> None:
    """Upload file to MinIO storage."""
    
def download_file(object_name: str) -> Tuple[IO, int, str]:
    """Download file from MinIO storage."""
    
def get_file_stream(object_name: str, range_header: str = None) -> Iterator[bytes]:
    """Stream file with range support for video playback."""
    
def delete_file(object_name: str) -> None:
    """Delete file from MinIO storage."""
    
def get_file_url(object_name: str, expires: int = 3600) -> str:
    """Generate presigned URL for file access."""
```

### Streaming Features
```python
def get_file_stream(object_name: str, range_header: str = None):
    """Advanced streaming with HTTP range support."""
    # Parse range header for video seeking
    # Stream file chunks efficiently
    # Support partial content responses (206)
    # Handle content-length and content-range headers
```

### Features
- **Efficient Upload/Download**: Chunked file operations
- **Video Streaming**: HTTP range request support for video players
- **Presigned URLs**: Secure temporary file access
- **Error Handling**: Comprehensive MinIO error handling
- **Metadata Management**: File metadata and content-type handling

## 🔍 OpenSearch Service (`opensearch_service.py`)

### Purpose
Manages full-text search, indexing, and search analytics for transcripts and files.

### Key Operations
```python
def index_transcript(file_id: int, user_id: int, full_transcript: str, speaker_names: List[str], file_title: str) -> None:
    """Index transcript for full-text search."""
    
def search_transcripts(user_id: int, query: str, filters: dict = None) -> List[Dict]:
    """Search across user's transcripts."""
    
def add_speaker_embedding(speaker_id: int, embedding_vector: List[float]) -> None:
    """Store speaker voice embedding for similarity search."""
    
def search_similar_speakers(embedding_vector: List[float], user_id: int) -> List[Dict]:
    """Find similar speakers using vector search."""
```

### Search Features
```python
def build_search_query(query: str, filters: dict) -> Dict:
    """Build complex OpenSearch query."""
    search_body = {
        "query": {
            "bool": {
                "must": [
                    {"match": {"transcript": query}}
                ],
                "filter": []
            }
        },
        "highlight": {
            "fields": {"transcript": {}}
        }
    }
    
    # Add filters (date range, speakers, file types, etc.)
    if filters.get('from_date'):
        search_body["query"]["bool"]["filter"].append({
            "range": {"created_at": {"gte": filters['from_date']}}
        })
    
    return search_body
```

### Features
- **Full-text Search**: Advanced search across transcripts
- **Faceted Search**: Filter by speakers, dates, file types
- **Highlighting**: Search term highlighting in results
- **Vector Search**: Speaker similarity using voice embeddings
- **Analytics**: Search performance and usage analytics

## 🔄 Service Integration Patterns

### Cross-Service Operations
```python
class FileService:
    def delete_file(self, file_id: int, user: User) -> None:
        """Complete file deletion across all services."""
        try:
            # 1. Get file information
            file_obj = self._get_file_with_permission_check(file_id, user)
            
            # 2. Delete from object storage
            minio_service.delete_file(file_obj.storage_path)
            
            # 3. Remove from search index
            opensearch_service.delete_document(file_id)
            
            # 4. Cancel any running tasks
            transcription_service.cancel_file_tasks(file_id)
            
            # 5. Delete from database (cascades to related records)
            self.db.delete(file_obj)
            self.db.commit()
            
        except Exception as e:
            self.db.rollback()
            raise self._handle_deletion_error(e)
```

### Service Dependencies
```python
# Services can call other services when needed
class TranscriptionService:
    def __init__(self, db: Session):
        self.db = db
        self.file_service = FileService(db)  # Dependency injection
    
    def start_transcription(self, file_id: int, user: User):
        # Use file service for validation
        file_obj = self.file_service.get_file_by_id(file_id, user)
        # Continue with transcription logic...
```

## 🧪 Testing Services

### Service Testing Patterns
```python
class TestFileService:
    def test_upload_file_success(self, db_session, mock_user, mock_upload_file):
        """Test successful file upload."""
        file_service = FileService(db_session)
        
        # Mock external dependencies
        with patch('app.services.minio_service.upload_file'):
            result = await file_service.upload_file(mock_upload_file, mock_user)
            
        assert result.filename == mock_upload_file.filename
        assert result.user_id == mock_user.id
    
    def test_delete_file_unauthorized(self, db_session, mock_user, other_user_file):
        """Test unauthorized file deletion."""
        file_service = FileService(db_session)
        
        with pytest.raises(HTTPException) as exc_info:
            file_service.delete_file(other_user_file.id, mock_user)
            
        assert exc_info.value.status_code == 403
```

### Mocking External Services
```python
# Mock external service calls in tests
@patch('app.services.minio_service.upload_file')
@patch('app.services.opensearch_service.index_transcript')
def test_complete_transcription_workflow(mock_opensearch, mock_minio, db_session):
    """Test full transcription workflow with mocked external services."""
    # Test logic without actual external API calls
```

## 📊 Error Handling in Services

### Standardized Error Responses
```python
from app.utils.error_handlers import ErrorHandler

class FileService:
    def get_file_by_id(self, file_id: int, user: User) -> MediaFile:
        """Get file with proper error handling."""
        file_obj = self.db.query(MediaFile).filter(
            MediaFile.id == file_id,
            MediaFile.user_id == user.id
        ).first()
        
        if not file_obj:
            raise ErrorHandler.not_found_error("File")
        
        return file_obj
    
    def _handle_upload_error(self, error: Exception) -> None:
        """Handle upload-specific errors."""
        if isinstance(error, MinIOError):
            raise ErrorHandler.file_processing_error("storage upload", error)
        elif isinstance(error, ValidationError):
            raise ErrorHandler.validation_error(str(error))
        else:
            raise ErrorHandler.database_error("file creation", error)
```

## 🚀 Performance Considerations

### Database Optimization
```python
class FileService:
    def get_user_files_with_stats(self, user: User) -> List[Dict]:
        """Optimized query with eager loading."""
        return self.db.query(MediaFile)\
            .options(
                joinedload(MediaFile.transcript_segments),
                joinedload(MediaFile.comments),
                selectinload(MediaFile.file_tags).joinedload(FileTag.tag)
            )\
            .filter(MediaFile.user_id == user.id)\
            .all()
```

### Caching Strategies
```python
from functools import lru_cache

class TranscriptionService:
    @lru_cache(maxsize=100)
    def get_user_speakers_cached(self, user_id: int) -> List[Speaker]:
        """Cache frequently accessed speaker data."""
        return self.db.query(Speaker)\
            .filter(Speaker.user_id == user_id)\
            .all()
```

## 🔧 Adding New Services

### Service Creation Checklist
1. **Define Purpose**: Clear single responsibility
2. **Design Interface**: Public methods and their signatures
3. **Error Handling**: Use standardized error patterns
4. **Dependencies**: Inject required services/utilities
5. **Testing**: Comprehensive unit tests with mocks
6. **Documentation**: Clear docstrings and examples

### Service Template
```python
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.user import User
from app.utils.error_handlers import ErrorHandler
from app.utils.auth_decorators import AuthorizationHelper

class NewService:
    """Service for handling [specific domain] operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_resource(self, data: CreateSchema, user: User) -> Resource:
        """Create a new resource with validation."""
        try:
            # Validation
            self._validate_create_data(data)
            
            # Business logic
            resource = self._perform_create_operation(data, user)
            
            # Database transaction
            self.db.add(resource)
            self.db.commit()
            self.db.refresh(resource)
            
            return resource
            
        except Exception as e:
            self.db.rollback()
            raise self._handle_create_error(e)
    
    def _validate_create_data(self, data: CreateSchema) -> None:
        """Private validation method."""
        # Validation logic
        pass
    
    def _handle_create_error(self, error: Exception) -> None:
        """Private error handling method."""
        # Error handling logic
        pass
```

---

The services layer provides a clean, testable, and maintainable way to implement business logic while keeping API endpoints focused on HTTP concerns and database models focused on data representation.