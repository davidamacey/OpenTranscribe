<div align="center">
  <img src="../../../assets/logo-banner.png" alt="OpenTranscribe Logo" width="250">
  
  # Background Tasks Documentation
</div>

This directory contains Celery-based background tasks for CPU-intensive AI processing operations. Tasks are designed to run asynchronously to avoid blocking API requests.

## ⚡ Task System Overview

### Architecture
```
API Request → Task Dispatch → Celery Worker → AI Processing → Database Update → WebSocket Notification
     ↓              ↓              ↓               ↓                ↓                    ↓
  HTTP Layer    Queue System   Background     AI/ML Models    Data Storage      Real-time UI
```

### Core Technologies
- **Celery**: Distributed task queue system
- **Redis**: Message broker for task queuing
- **Flower**: Task monitoring and management UI
- **WhisperX**: Advanced speech recognition with alignment
- **PyAnnote**: Speaker diarization and voice analysis
- **Multi-Provider LLMs**: Intelligent summarization with context processing
- **FFmpeg**: Media processing and conversion

## 📁 Task Structure

```
tasks/
├── transcription/              # Modular transcription pipeline
│   ├── __init__.py            # Main task exports
│   ├── core.py                # Task orchestrator
│   ├── metadata_extractor.py  # Media metadata processing
│   ├── audio_processor.py     # Audio conversion/extraction
│   ├── whisperx_service.py    # AI transcription service
│   ├── speaker_processor.py   # Speaker diarization
│   ├── storage.py             # Database storage utilities
│   └── notifications.py       # WebSocket notifications
├── analytics.py               # Analytics and insights processing
├── cleanup.py                 # File recovery and cleanup tasks
├── summarization.py           # Multi-provider AI summarization with intelligent section processing
├── speaker_tasks.py           # LLM-powered speaker identification and management
├── transcription.py           # Main transcription task router
└── youtube_processing.py      # NEW: Enhanced YouTube URL processing with metadata extraction
```

## 🎙️ Transcription Pipeline (`transcription/`)

### Pipeline Overview
The transcription system is modularized into focused components for maintainability and reusability:

```
1. File Download → 2. Metadata Extraction → 3. Audio Processing → 4. AI Transcription → 5. Speaker Diarization → 6. Database Storage → 7. Search Indexing → 8. Notifications
```

### Core Task (`core.py`)
Main orchestrator that coordinates the entire transcription pipeline:

```python
@celery_app.task(bind=True, name="transcribe_audio")
def transcribe_audio_task(self, file_id: int):
    """
    Process an audio/video file with WhisperX for transcription and PyAnnote for diarization.
    
    Pipeline:
    1. Download file from MinIO storage
    2. Extract comprehensive metadata with ExifTool
    3. Convert/extract audio for processing
    4. Run WhisperX transcription with word-level alignment
    5. Perform speaker diarization with PyAnnote
    6. Process and store transcript segments
    7. Index content for search
    8. Send real-time notifications
    """
```

**Key Features:**
- **Progress Tracking**: Real-time progress updates (0.1 → 1.0)
- **Error Handling**: Comprehensive error recovery and logging
- **Status Management**: File status transitions (pending → processing → completed)
- **Session Management**: Proper database session handling
- **Resource Cleanup**: Temporary file cleanup and memory management

### Metadata Extraction (`metadata_extractor.py`)
Extracts comprehensive media metadata using ExifTool:

```python
def extract_media_metadata(file_path: str) -> Optional[Dict[str, Any]]:
    """Extract metadata from media file using ExifTool."""
    
def get_important_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Filter and normalize important metadata fields."""
    
def update_media_file_metadata(media_file, extracted_metadata: Dict[str, Any], 
                              content_type: str, file_path: str) -> None:
    """Update MediaFile object with extracted metadata."""
```

**Extracted Information:**
- **File Properties**: Size, format, type, duration
- **Video Specs**: Resolution, frame rate, codec, aspect ratio
- **Audio Specs**: Channels, sample rate, bit depth
- **Creation Data**: Timestamps, device information
- **Content Info**: Title, author, description, GPS data

### Audio Processing (`audio_processor.py`)
Handles audio extraction and format conversion:

```python
def prepare_audio_for_transcription(temp_file_path: str, content_type: str, 
                                  temp_dir: str) -> str:
    """Prepare audio file for transcription by extracting from video or converting format."""
    
def extract_audio_from_video(video_path: str, output_path: str) -> None:
    """Extract audio from video using FFmpeg."""
    
def convert_audio_format(input_path: str, output_path: str) -> None:
    """Convert audio to WAV format for optimal WhisperX processing."""
```

**Processing Features:**
- **Format Detection**: Automatic format detection from MIME types
- **Video Audio Extraction**: Extract audio track from video files
- **Audio Conversion**: Convert to optimal format (16kHz, mono, PCM)
- **Quality Optimization**: Prepare audio for best AI recognition results

### WhisperX Service (`whisperx_service.py`)
Manages the AI transcription pipeline using WhisperX:

```python
class WhisperXService:
    def process_full_pipeline(self, audio_file_path: str, hf_token: str = None) -> Dict[str, Any]:
        """Run complete WhisperX pipeline: transcription, alignment, and diarization."""
    
    def transcribe_audio(self, audio_file_path: str) -> Dict[str, Any]:
        """Transcribe audio using WhisperX."""
    
    def align_transcription(self, transcription_result: Dict[str, Any], audio) -> Dict[str, Any]:
        """Align transcription with precise word-level timestamps."""
    
    def perform_speaker_diarization(self, audio, hf_token: str = None) -> Dict[str, Any]:
        """Perform speaker diarization on audio."""
```

**AI Features:**
- **Advanced Recognition**: WhisperX with faster-whisper backend
- **Word-level Alignment**: Precise timing for each word using WAV2VEC2
- **Speaker Diarization**: PyAnnote-based speaker identification
- **Multi-language Support**: Automatic translation to English
- **GPU Acceleration**: Optimized for CUDA when available

### Speaker Processing (`speaker_processor.py`)
Manages speaker identification and database operations:

```python
def extract_unique_speakers(segments: List[Dict[str, Any]]) -> Set[str]:
    """Extract unique speaker IDs from transcription segments."""
    
def create_speaker_mapping(db: Session, user_id: int, unique_speakers: Set[str]) -> Dict[str, int]:
    """Create mapping of speaker labels to database IDs."""
    
def process_segments_with_speakers(segments: List[Dict[str, Any]], 
                                 speaker_mapping: Dict[str, int]) -> List[Dict[str, Any]]:
    """Process transcription segments and add speaker database IDs."""
```

**Speaker Features:**
- **Consistent Labeling**: Standardized speaker ID format (SPEAKER_XX)
- **Cross-file Tracking**: UUID-based speaker identification
- **Database Integration**: Automatic speaker record creation
- **User Management**: Speaker verification and display names

### Database Storage (`storage.py`)
Handles all database operations for transcription results:

```python
def save_transcript_segments(db: Session, file_id: int, segments: List[Dict[str, Any]]) -> None:
    """Save transcript segments to database."""
    
def update_media_file_transcription_status(db: Session, file_id: int, 
                                         segments: List[Dict[str, Any]], language: str = "en") -> None:
    """Update media file with transcription completion metadata."""
```

**Storage Features:**
- **Bulk Operations**: Efficient segment insertion
- **Transaction Management**: Atomic operations with rollback
- **Status Updates**: File status progression tracking
- **Relationship Management**: Speaker-segment associations

### Notifications (`notifications.py`)
Real-time WebSocket notifications for UI updates:

```python
def send_notification_with_retry(user_id: int, file_id: int, status: FileStatus, 
                                message: str, progress: int = 0, max_retries: int = 3) -> bool:
    """Send notification with retry logic."""
    
def send_processing_notification(user_id: int, file_id: int) -> None:
    """Send processing started notification."""
    
def send_completion_notification(user_id: int, file_id: int) -> None:
    """Send transcription completed notification."""
```

**Notification Features:**
- **Real-time Updates**: Instant UI notifications via WebSocket
- **Progress Tracking**: Step-by-step progress updates
- **Error Notifications**: User-friendly error messages
- **Retry Logic**: Robust delivery with automatic retries

## 📊 Analytics Tasks (`analytics.py`)

### Purpose
Generate insights and analytics from transcribed content:

```python
@celery_app.task(name="analyze_transcript")
def analyze_transcript_task(file_id: int):
    """
    Analyze a transcript for additional metadata and insights.
    
    Generates:
    - Word count statistics
    - Speaker distribution
    - Segment analysis
    - Duration metrics
    """
```

**Analytics Features:**
- **Content Metrics**: Word counts, segment counts, speaker distribution
- **Time Analysis**: Speaking time per speaker, segment duration patterns
- **Language Insights**: Vocabulary analysis, complexity metrics
- **Engagement Metrics**: Turn-taking patterns, interruption analysis

## 📝 AI Summarization Tasks (`summarization.py`)

### Purpose
Generate comprehensive BLUF-format summaries using multi-provider LLMs with intelligent context processing:

```python
@celery_app.task(name="summarize_transcript")
def summarize_transcript_task(file_id: int):
    """
    Generate AI-powered summary with intelligent section processing.
    
    Workflow:
    1. Retrieve transcript and speaker data from database
    2. Query LLM model for context length capabilities  
    3. Automatically chunk long transcripts at natural boundaries
    4. Process each section individually for comprehensive analysis
    5. Stitch section summaries into final BLUF format
    6. Store results in both PostgreSQL and OpenSearch for search
    """
```

### Intelligent Context Processing

```python
# Example: Long transcript processing
context_length = await llm_service.get_model_context_length()  # 4096 for small Ollama model
transcript_chunks = chunk_transcript_intelligently(transcript, context_length)

if len(chunks) == 1:
    # Single-pass processing
    summary = await llm_service.generate_summary(transcript_chunks[0])
else:
    # Multi-section processing  
    section_summaries = []
    for i, chunk in enumerate(transcript_chunks):
        section_summary = await llm_service.summarize_transcript_section(chunk, i+1, len(chunks))
        section_summaries.append(section_summary)
    
    # Stitch into comprehensive BLUF summary
    summary = await llm_service.stitch_section_summaries(section_summaries)
```

**AI Summarization Features:**
- **BLUF Format**: Bottom Line Up Front executive summaries
- **Multi-Provider Support**: vLLM, OpenAI, Ollama, Claude, OpenRouter
- **Intelligent Chunking**: Natural boundaries (speaker changes, topics, sentences)
- **Context-Aware Processing**: Automatic model capability detection
- **Universal Compatibility**: Works with 4K to 200K+ token models
- **No Content Loss**: Complete transcript analysis regardless of length
- **Structured Output**: Action items, decisions, speaker analysis, key points

## 🧹 File Cleanup Tasks (`cleanup.py`)

### Purpose
Automated background tasks for system maintenance, file recovery, and health monitoring:

```python
@shared_task(bind=True, name="cleanup.run_periodic_cleanup")
def run_periodic_cleanup(self):
    """
    Periodic task to clean up stuck files and maintain system health.
    
    This task should be run regularly (e.g., every 30 minutes) to:
    - Detect and recover stuck files
    - Mark orphaned files for cleanup
    - Generate system health reports
    """

@shared_task(bind=True, name="cleanup.deep_cleanup")
def run_deep_cleanup(self, dry_run: bool = False):
    """
    Deep cleanup task for removing orphaned files (admin-triggered).
    
    Args:
        dry_run: If True, only preview what would be cleaned up
    """

@shared_task(bind=True, name="cleanup.health_check")
def system_health_check(self):
    """
    Generate a system health report with file processing metrics.
    """

@shared_task(bind=True, name="cleanup.emergency_recovery")
def emergency_file_recovery(self, file_ids: list):
    """
    Emergency recovery task for specific files (admin-triggered).
    
    Args:
        file_ids: List of file IDs to attempt recovery on
    """
```

### Auto-Recovery Features
The cleanup tasks provide comprehensive file recovery capabilities:

**Stuck File Detection:**
- Files processing longer than threshold (default: 2 hours)
- Files pending longer than threshold without starting
- Files with failed tasks that can be retried
- Files marked as orphaned needing recovery

**Recovery Actions:**
- Cancel stuck/failed Celery tasks
- Reset file status and retry counters
- Clear partial processing artifacts
- Restart transcription with fresh task
- Update recovery attempt tracking

**System Health Monitoring:**
- Calculate error rates and processing statistics
- Generate actionable health recommendations
- Monitor worker capacity and queue health
- Track cleanup success/failure rates

### Periodic Cleanup Configuration
```python
# Celery Beat configuration for automatic scheduling
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'run-periodic-cleanup': {
        'task': 'cleanup.run_periodic_cleanup',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
    'system-health-check': {
        'task': 'cleanup.health_check',
        'schedule': crontab(minute=0, hour='*/6'),  # Every 6 hours
    },
}
```

### Integration with Enhanced File Safety
The cleanup tasks work with the enhanced file management system:

**Enhanced Status States:**
- `PENDING` → `PROCESSING` → `COMPLETED`/`ERROR`
- New states: `CANCELLING`, `CANCELLED`, `ORPHANED`
- Task tracking with `active_task_id` and timing metadata

**Safe Operations:**
- Pre-deletion safety checks for active processing
- Force deletion options for admin users
- Retry limits and intelligent recovery logic
- Transaction safety with proper rollback handling

**Real-time Monitoring:**
- WebSocket notifications for recovery operations
- Progress tracking for bulk operations
- User-friendly error messages and recommendations

## 🔧 Task Configuration

### Celery Configuration (`app/core/celery.py`)
```python
# Task routing and configuration
celery_app = Celery("transcribe_app")
celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
)
```

### Task Registration
```python
# Tasks are automatically discovered
celery_app.autodiscover_tasks(['app.tasks'])

# Manual task registration for complex imports
from app.tasks.transcription import transcribe_audio_task
from app.tasks.analytics import analyze_transcript_task
from app.tasks.summarization import summarize_transcript_task
```

## 📊 Task Monitoring

### Flower Dashboard
- **URL**: http://localhost:5555/flower
- **Features**: Task monitoring, worker status, performance metrics
- **Real-time**: Live task progress and completion rates

### Task Status Tracking
```python
# Task status in database
class Task(Base):
    id: str  # Celery task ID
    status: str  # pending, in_progress, completed, failed
    progress: float  # 0.0 to 1.0
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
```

### Progress Updates
```python
# Update task progress during processing
with session_scope() as db:
    update_task_status(db, task_id, "in_progress", progress=0.5)
```

## 🛡️ Error Handling

### Error Recovery Patterns
```python
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def robust_task(self, file_id: int):
    """Task with automatic retry on failure."""
    try:
        # Task logic
        return process_file(file_id)
    except RecoverableError as e:
        # Retry for recoverable errors
        raise self.retry(countdown=60, exc=e)
    except FatalError as e:
        # Don't retry for fatal errors
        logger.error(f"Fatal error in task: {e}")
        raise
```

### Error Notification
```python
def handle_task_failure(task_id: str, file_id: int, user_id: int, error: Exception):
    """Handle task failure with proper cleanup and notification."""
    try:
        # Update database status
        with session_scope() as db:
            update_task_status(db, task_id, "failed", error_message=str(error))
            update_media_file_status(db, file_id, FileStatus.ERROR)
        
        # Notify user
        send_error_notification(user_id, file_id, str(error))
        
    except Exception as cleanup_error:
        logger.error(f"Error during failure cleanup: {cleanup_error}")
```

## 🚀 Performance Optimization

### GPU Utilization
```python
# Optimize for GPU processing
device = "cuda" if torch.cuda.is_available() else "cpu"
compute_type = "float16" if device == "cuda" else "float32"

# Memory management
if device == "cuda":
    gc.collect()
    torch.cuda.empty_cache()
```

### Batch Processing
```python
# Process multiple files efficiently
@celery_app.task
def batch_transcribe_task(file_ids: List[int]):
    """Process multiple files in a single task for efficiency."""
    for file_id in file_ids:
        try:
            process_single_file(file_id)
        except Exception as e:
            logger.error(f"Error processing file {file_id}: {e}")
            continue  # Continue with other files
```

### Resource Management
```python
# Temporary file cleanup
with tempfile.TemporaryDirectory() as temp_dir:
    # Processing within temporary directory
    # Automatic cleanup on exit
    pass

# Database session management
with session_scope() as db:
    # Database operations
    # Automatic commit/rollback
    pass
```

## 🧪 Testing Tasks

### Task Testing Patterns
```python
def test_transcription_task_success(celery_app, db_session, sample_file):
    """Test successful transcription task."""
    # Mock external dependencies
    with patch('app.services.minio_service.download_file') as mock_download:
        mock_download.return_value = (sample_audio_data, 1024, "audio/wav")
        
        # Execute task
        result = transcribe_audio_task.apply(args=[sample_file.id])
        
        # Verify results
        assert result.successful()
        assert result.result["status"] == "success"

def test_transcription_task_failure(celery_app, db_session, invalid_file):
    """Test transcription task failure handling."""
    result = transcribe_audio_task.apply(args=[invalid_file.id])
    
    assert result.failed()
    # Verify error handling and cleanup
```

### Integration Testing
```python
def test_full_transcription_pipeline(client, auth_headers, sample_video):
    """Test complete pipeline from upload to completion."""
    # 1. Upload file
    response = client.post("/api/files", files={"file": sample_video}, headers=auth_headers)
    file_id = response.json()["id"]
    
    # 2. Wait for processing (with timeout)
    # 3. Verify transcription results
    # 4. Check database state
    # 5. Verify search indexing
```

## 🔧 Adding New Tasks

### Task Creation Checklist
1. **Define Purpose**: Clear single responsibility
2. **Design Interface**: Input parameters and return values
3. **Error Handling**: Comprehensive error recovery
4. **Progress Tracking**: Regular progress updates
5. **Resource Management**: Proper cleanup
6. **Testing**: Unit and integration tests
7. **Documentation**: Clear docstrings and examples

### Task Template
```python
@celery_app.task(bind=True, name="new_task")
def new_task(self, input_data: Dict[str, Any]):
    """
    New task description.
    
    Args:
        input_data: Task input parameters
        
    Returns:
        Dict with task results
    """
    task_id = self.request.id
    
    try:
        # 1. Initialize and validate
        validate_input(input_data)
        
        # 2. Update progress
        with session_scope() as db:
            update_task_status(db, task_id, "in_progress", progress=0.1)
        
        # 3. Perform main processing
        result = perform_main_operation(input_data)
        
        # 4. Update progress
        with session_scope() as db:
            update_task_status(db, task_id, "in_progress", progress=0.8)
        
        # 5. Finalize and return
        with session_scope() as db:
            update_task_status(db, task_id, "completed", progress=1.0, completed=True)
        
        return {"status": "success", "result": result}
        
    except Exception as e:
        # Error handling
        with session_scope() as db:
            update_task_status(db, task_id, "failed", error_message=str(e), completed=True)
        
        logger.error(f"Task {task_id} failed: {e}")
        return {"status": "error", "message": str(e)}
```

---

The background task system provides a robust, scalable foundation for AI-powered media processing with comprehensive error handling, progress tracking, and real-time user feedback.