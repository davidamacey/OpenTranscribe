<div align="center">
  <img src="../assets/logo-banner.png" alt="OpenTranscribe Logo" width="400">
  
  # Backend
</div>

A modern FastAPI-based backend for AI-powered transcription and media processing.

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Git

### Development Setup
```bash
# Clone the repository
git clone <repository-url>
cd transcribe-app

# Start development environment
./opentr.sh start dev

# Check health
curl http://localhost:8080/health
```

### API Access
- **API Base URL**: http://localhost:8080/api
- **Interactive Docs**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc
- **Flower Dashboard**: http://localhost:5555/flower

## 📋 Table of Contents

- [Architecture Overview](#architecture-overview)
- [Directory Structure](#directory-structure)
- [Development Guide](#development-guide)
- [API Documentation](#api-documentation)
- [Database Management](#database-management)
- [Background Tasks](#background-tasks)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)

## 🏗️ Architecture Overview

OpenTranscribe backend is built with modern Python technologies:

### Core Technologies
- **FastAPI** - High-performance async web framework
- **SQLAlchemy 2.0** - Modern Python SQL toolkit and ORM
- **Alembic** - Database migration management
- **Celery** - Distributed task queue for background processing
- **Redis** - Task broker and caching
- **PostgreSQL** - Primary database
- **MinIO** - S3-compatible object storage
- **OpenSearch** - Full-text and vector search

### AI/ML Stack
- **WhisperX** - Advanced speech recognition with word-level alignment
- **PyAnnote** - Speaker diarization, voice fingerprinting, and cross-video speaker matching
- **FFmpeg** - Media processing and conversion
- **OpenSearch Vector Search** - Embedding-based speaker similarity matching

#### Enhanced AI Processing Features
- **Fast Batch Processing**: WhisperX leverages faster-whisper for batched inference (70x realtime with large-v2)
- **Accurate Word-level Timestamps**: Uses wav2vec2 alignment for precise word timing
- **Advanced Speaker Diarization**: Identifies different speakers using PyAnnote.audio with voice fingerprinting
- **Cross-Video Speaker Recognition**: AI-powered matching of speakers across different media files using embedding similarity
- **Speaker Profile Management**: Global speaker profiles that persist across all transcriptions
- **AI-Powered Speaker Suggestions**: Automatic speaker identification with confidence scoring and verification workflow
- **Automatic Translation**: Always converts audio to English transcripts
- **Video Metadata Extraction**: Extracts detailed metadata from video files using ExifTool (resolution, frame rate, codec, etc.)

#### AI/ML Configuration
Required environment variables for AI processing:

| Variable | Description | Default |
|----------|-------------|---------|
| `WHISPER_MODEL` | Whisper model size to use | `large-v2` |
| `DIARIZATION_MODEL` | Pyannote diarization model | `pyannote/speaker-diarization-3.1` |
| `BATCH_SIZE` | Batch size for processing (reduce if low on GPU memory) | `16` |
| `COMPUTE_TYPE` | Computation precision (`float16` or `int8`) | `float16` |
| `MIN_SPEAKERS` | Minimum number of speakers to detect (optional) | `1` |
| `MAX_SPEAKERS` | Maximum number of speakers to detect (optional) | `10` |
| `HUGGINGFACE_TOKEN` | HuggingFace API token for diarization models | Required |
| `MODEL_CACHE_DIR` | Host directory to cache downloaded models | `./models` |

#### Model Caching
OpenTranscribe automatically caches AI models for persistence across container restarts:

- **WhisperX Models**: Cached via HuggingFace Hub (~1.5GB)
- **PyAnnote Models**: Cached via PyTorch/HuggingFace (~500MB)  
- **Alignment Models**: Cached via PyTorch Hub (~360MB)
- **Total Storage**: ~2.5GB for complete model cache

Models are downloaded once on first use and automatically reused. Set `MODEL_CACHE_DIR` in your `.env` to specify the host directory for model storage.

#### HuggingFace Authentication
You must obtain a HuggingFace API token to use the speaker diarization functionality. Create an account at [HuggingFace](https://huggingface.co/) and generate a token at https://huggingface.co/settings/tokens.

You also need to accept the user agreement for the following models:
- [Segmentation](https://huggingface.co/pyannote/segmentation)
- [Speaker-Diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)

#### Troubleshooting AI Processing
- **High GPU Memory Usage**: Try reducing `BATCH_SIZE` or changing `COMPUTE_TYPE` to `int8`
- **Slow Processing**: Consider using a smaller model like `medium` or `small` 
- **Speaker Identification Issues**: Adjust `MIN_SPEAKERS` and `MAX_SPEAKERS` if you know the approximate speaker count

#### AI/ML References
- [WhisperX GitHub Repository](https://github.com/m-bain/whisperX)
- [Pyannote Audio](https://github.com/pyannote/pyannote-audio)

### Architecture Principles
- **Modular Design** - Clear separation of concerns
- **Service Layer** - Business logic abstraction
- **Async/Await** - Non-blocking request handling
- **Background Processing** - CPU-intensive tasks offloaded to workers
- **RESTful API** - Standard HTTP methods and status codes
- **Real-time Updates** - WebSocket notifications for long-running tasks

## 📁 Directory Structure

```
backend/
├── app/                        # Main application package
│   ├── api/                   # API layer
│   │   ├── endpoints/         # API route handlers
│   │   │   ├── files/        # File management modules
│   │   │   └── *.py          # Individual endpoint modules
│   │   ├── router.py         # Main API router
│   │   └── websockets.py     # WebSocket handlers
│   ├── auth/                 # Authentication modules
│   ├── core/                 # Core configuration and setup
│   ├── db/                   # Database utilities
│   ├── models/               # SQLAlchemy ORM models
│   ├── schemas/              # Pydantic validation schemas
│   ├── services/             # Business logic layer
│   ├── tasks/                # Background task processing
│   │   └── transcription/    # Modular transcription pipeline
│   ├── utils/                # Common utilities
│   ├── main.py              # FastAPI application entry point
│   └── initial_data.py      # Database initialization
├── alembic/                  # Database migrations
├── scripts/                  # Utility scripts
├── tests/                    # Test suite
├── requirements.txt          # Python dependencies
├── Dockerfile.dev           # Development container
└── README.md               # This file
```

## 🛠️ Development Guide

### Environment Setup

1. **Use the OpenTranscribe utility script**:
   ```bash
   ./opentr.sh start dev    # Start development environment
   ./opentr.sh logs backend # View backend logs
   ./opentr.sh shell backend # Access backend container
   ```

2. **Manual setup** (if needed):
   ```bash
   cd backend/
   pip install -r requirements.txt
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
   ```

### Development Workflow

1. **Code Changes**:
   - Backend code is mounted as a volume in development
   - Changes are automatically reloaded via `--reload` flag
   - No container restart needed for code changes

2. **Database Changes**:
   ```bash
   # Update database/init_db.sql
   # Update app/models/ SQLAlchemy models
   # Update app/schemas/ Pydantic schemas
   ./opentr.sh reset dev  # Reset database with new schema
   ```

3. **Dependency Changes**:
   ```bash
   # Add to requirements.txt
   ./opentr.sh restart-backend  # Rebuild container with new deps
   ```

### Code Style and Standards

- **Python Style**: Follow PEP 8
- **Type Hints**: Use throughout codebase
- **Docstrings**: Google-style docstrings for functions/classes
- **Imports**: Organize imports (standard, third-party, local)
- **Error Handling**: Use structured error responses
- **Async/Await**: Prefer async functions for I/O operations

### Adding New Features

1. **API Endpoints**: Add to `app/api/endpoints/`
2. **Database Models**: Add to `app/models/`
3. **Validation Schemas**: Add to `app/schemas/`
4. **Business Logic**: Add to `app/services/`
5. **Background Tasks**: Add to `app/tasks/`
6. **Tests**: Add to `tests/`

## 📚 API Documentation

### Interactive Documentation
- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc

### API Structure
```
/api/
├── /auth          # Authentication endpoints
├── /files         # File management
├── /users         # User management
├── /comments      # Comment system
├── /tags          # Tag management
├── /speakers      # Speaker management and cross-video matching
├── /speaker-profiles # Global speaker profile management
├── /tasks         # Task monitoring
├── /search        # Search functionality
└── /admin         # Admin operations
```

### Authentication
- **JWT Tokens** for API authentication
- **Role-based access** (user, admin)
- **File ownership** validation

### Response Format
```json
{
  "data": {...},
  "message": "Success message",
  "status": "success"
}
```

### Error Format
```json
{
  "detail": "Error description",
  "status_code": 400,
  "error_type": "validation_error"
}
```

## 🗄️ Database Management

### Development Approach
- **Direct SQL**: Schema defined in `database/init_db.sql`
- **Quick Reset**: Use `./opentr.sh reset dev` for schema changes
- **Models**: SQLAlchemy models in `app/models/`
- **Validation**: Pydantic schemas in `app/schemas/`

### Production Approach
- **Migrations**: Alembic migrations for version control
- **Deployment**: `alembic upgrade head` for production
- **Rollback**: `alembic downgrade -1` if needed

### Database Scripts
```bash
# Development
./opentr.sh reset dev              # Reset with new schema
python scripts/db_inspect.py       # Inspect database state
python scripts/create_admin.py     # Create admin user

# Production (future)
alembic upgrade head               # Apply migrations
alembic revision --autogenerate    # Generate migration
```

## ⚙️ Background Tasks

### Task System
- **Celery** with Redis broker
- **Flower** monitoring at http://localhost:5555/flower
- **Async processing** for CPU-intensive operations

### Available Tasks
- **Transcription**: WhisperX + speaker diarization with voice fingerprinting
- **Speaker Matching**: Cross-video speaker identification and profile matching
- **Analysis**: Transcript analysis and metrics
- **Summarization**: Automated transcript summaries

### Task Monitoring
```bash
# View task status
./opentr.sh logs celery-worker

# Monitor with Flower
# http://localhost:5555/flower
```

## 🧪 Testing

### Test Suite
```bash
# Run all tests
./opentr.sh shell backend
pytest tests/

# Run specific test
pytest tests/api/endpoints/test_files.py

# Run with coverage
pytest --cov=app tests/
```

### Test Structure
- **Unit Tests**: Individual component testing
- **Integration Tests**: API endpoint testing
- **Database Tests**: Model and schema validation
- **Mock Services**: External service mocking

### Test Configuration
- **Isolated Database**: SQLite in-memory for tests
- **Disabled Services**: S3, Celery, Redis disabled in tests
- **Fixtures**: Common test data and setup

## 🚀 Deployment

### Production Setup
1. **Environment Variables**: Configure production settings
2. **Database**: Run Alembic migrations
3. **Storage**: Configure MinIO/S3 for file storage
4. **Search**: Set up OpenSearch cluster
5. **Workers**: Deploy Celery workers with GPU support
6. **Monitoring**: Set up logging and metrics

### Environment Variables
```bash
# Core
DATABASE_URL=postgresql://user:pass@host:5432/db
SECRET_KEY=your-secret-key

# Storage
MINIO_ENDPOINT=your-minio-endpoint
MINIO_ACCESS_KEY=your-access-key
MINIO_SECRET_KEY=your-secret-key

# AI/ML
HUGGINGFACE_TOKEN=your-hf-token

# Search
OPENSEARCH_URL=your-opensearch-url
```

### Health Checks
- **Application**: `/health` endpoint
- **Database**: Connection validation
- **Storage**: MinIO connectivity
- **Search**: OpenSearch status
- **Workers**: Celery worker health

## 🤝 Contributing

### Development Process
1. **Fork** the repository
2. **Create** feature branch: `git checkout -b feature/amazing-feature`
3. **Follow** code style and add tests
4. **Commit** changes: `git commit -m 'Add amazing feature'`
5. **Push** branch: `git push origin feature/amazing-feature`
6. **Create** Pull Request

### Code Review Checklist
- [ ] Code follows style guidelines
- [ ] Tests added for new functionality
- [ ] Documentation updated
- [ ] No breaking changes (or properly documented)
- [ ] Performance impact considered
- [ ] Security implications reviewed

### Reporting Issues
- Use GitHub Issues for bug reports
- Include environment details
- Provide reproduction steps
- Include relevant logs

## 📞 Support

### Documentation
- **API Docs**: http://localhost:8080/docs
- **Architecture**: [app/README.md](app/README.md)
- **Database**: [app/db/README.md](app/db/README.md)
- **Scripts**: [scripts/README.md](scripts/README.md)

### Getting Help
- **GitHub Issues**: Bug reports and feature requests
- **Discussions**: General questions and discussions
- **Documentation**: Check existing docs first

### Useful Commands
```bash
# Development
./opentr.sh start dev           # Start development
./opentr.sh logs backend        # View logs
./opentr.sh shell backend       # Access container
./opentr.sh restart-backend     # Restart backend only

# Database
./opentr.sh reset dev           # Reset database
python scripts/db_inspect.py    # Inspect database

# Testing
pytest tests/                   # Run tests
pytest --cov=app tests/         # With coverage
```

---

**Built with ❤️ using FastAPI, SQLAlchemy, and modern Python technologies.**