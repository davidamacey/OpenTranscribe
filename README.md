# 🎙️ OpenTranscribe

**This application is 99.9% created by AI using Windsurf and a variety of commercial LLMs**

## 📋 Overview

OpenTranscribe is a powerful web application for transcribing and analyzing audio/video files. This application leverages state-of-the-art AI models for speech recognition, speaker diarization, and text analysis to provide an end-to-end solution for transcription needs.

⚠️ **IMPORTANT**: This project is a work in progress and may have issues. Some features are still under development, and the application may not function perfectly in all scenarios. We are continuously working to improve stability and feature completeness.

## ✨ Key Features

- 🔊 **Audio/Video Transcription**: Upload media files and get accurate transcripts with word-level timestamps using state-of-the-art speech recognition technology
- 👥 **Speaker Diarization**: Automatically identify and label different speakers in your recordings, making multi-person conversations easy to follow
- 🧠 **Speaker Recognition**: Recognize the same speakers across multiple recordings through voice fingerprinting technology
- 🖱️ **Interactive Transcript**: Navigate media playback by clicking on transcript text, making it easy to find and reference specific moments
- 💬 **Comments & Annotations**: Add time-stamped comments to mark important moments, perfect for collaboration and review
- 🔍 **Powerful Search**: Find specific content using both keyword and semantic search capabilities through OpenSearch integration
- 📊 **Analytics & Insights**: View speaker statistics, sentiment analysis, and key topics to gain deeper understanding of your content
- 📝 **Summarization**: Generate concise summaries of your transcripts using local LLMs to quickly grasp main points
- 🌐 **Multi-language Support**: Transcribe in multiple languages with translation capabilities for global content
- 📺 **Subtitle Export**: Generate SRT/VTT files or embed subtitles directly into videos for sharing and accessibility

## 🛠️ Technology Stack

OpenTranscribe is built using modern technologies carefully selected for performance, reliability, and maintainability:

- 🖥️ **Frontend**: 
  - Svelte framework for reactive and efficient UI components
  - Responsive design that works across desktop and mobile devices
  - Modern JavaScript with component-based architecture

- 🔧 **Backend**: 
  - Python FastAPI with async support for high performance
  - Modular coding practices for maintainability and extensibility
  - RESTful API design with comprehensive Swagger documentation

- 🗄️ **Databases**: 
  - PostgreSQL for reliable relational data storage
  - SQLAlchemy ORM for type-safe database interactions
  - Pydantic for robust data validation and schemas

- 🔍 **Vector Storage**: 
  - OpenSearch for powerful full-text and vector search capabilities
  - Custom embedding integration for semantic similarity searching
  - Hybrid search combining traditional and vector-based approaches

- 🔄 **Task Processing**: 
  - Celery with Redis for reliable asynchronous job processing
  - Task monitoring through Flower dashboard
  - Robust error handling and task retry mechanisms

- 🧠 **AI Models**:
  - Faster-Whisper for efficient and accurate speech-to-text conversion
  - PyAnnotate for precise speaker diarization and voice fingerprinting
  - Local LLMs for natural language processing tasks like summarization
  - FFmpeg for comprehensive media processing capabilities

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Git
- NVIDIA GPU recommended (for faster processing) with CUDA support

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/opentranscribe.git
   cd opentranscribe
   ```

2. Create an environment file:
   ```bash
   cp .env.example .env
   # Edit .env with your configurations if needed
   ```

### 🧪 Development Mode

The development environment uses Docker Compose to run all components with live-reloading for a productive development experience:

1. Start the development environment:
   ```bash
   ./start.sh dev
   # or use the opentr.sh utility:
   # ./opentr.sh start dev
   ```
   
   This performs the following actions:
   - Starts all Docker containers with proper dependency ordering
   - Creates necessary directories for models and temporary files
   - Sets up the database with initial schema if needed
   - Starts the backend API server with auto-reload for instant code changes
   - Launches Celery workers for background processing with GPU support if available
   - Starts the frontend development server with hot module replacement
   - Shows container logs for monitoring

2. Access the application and related services:
   - 🌐 **Frontend**: http://localhost:5173 (Svelte application with hot reloading)
   - 🔌 **API**: http://localhost:8080/api (FastAPI with auto-reload)
   - 📚 **API Documentation**: http://localhost:8080/docs (Swagger UI)
   - 🔍 **OpenSearch**: http://localhost:9200 (Vector & full-text search)
   - 📁 **MinIO Console**: http://localhost:9091 (Object storage, credentials in .env file)
   - 🌺 **Flower Dashboard**: http://localhost:5555/flower (Celery task monitoring)

3. Manage the development environment:
   ```bash
   # Reset the environment (clear all data):
   ./reset_and_init.sh dev
   # or
   ./opentr.sh reset dev
   
   # Stop all services:
   ./opentr.sh stop
   
   # View logs:
   ./opentr.sh logs [service]  # e.g., backend, frontend, postgres
   
   # Open a shell in a container:
   ./opentr.sh shell backend  # or frontend, postgres, etc.
   ```
   
   The reset command performs these actions:
   - Stops and removes all containers
   - Removes volumes (clearing all data)
   - Rebuilds and restarts the services
   - Reinitializes the database with base schema
   - Creates an admin user if one doesn't exist

### 🚀 Production Mode

For production deployment, OpenTranscribe uses a specialized build process to optimize performance and security:

1. Configure the `.env` file with production settings:
   ```bash
   # Create a copy of .env.example specifically for production
   cp .env.example .env.prod
   
   # Edit the .env.prod file to ensure:
   # - NODE_ENV=production
   # - Set strong, unique passwords for all services
   # - Optimize resource settings based on your hardware
   # - Configure appropriate JWT secrets
   ```

2. Build and start the production environment:
   ```bash
   # Using the utility script (recommended):
   ./opentr.sh start prod
   
   # Or manually:
   ./reset_and_init.sh prod
   ```
   
   This will:
   - Stop any existing containers and clear volumes
   - Build optimized production images (including minified frontend)
   - Start only the necessary services for production
   - Initialize the database with base schema and admin user
   - Configure NGINX to serve the production frontend

3. Access the application:
   - 🌐 **Frontend**: http://localhost:5173 (production build served via NGINX in container)
   - 🔌 **API**: http://localhost:8080/api (optimized FastAPI without debug/reload)
   - 🌺 **Flower**: http://localhost:5555/flower (for monitoring tasks) 

4. Important production considerations:
   - 🔒 **Security**: Set strong passwords in the .env file and limit access to admin interfaces
   - 🛡️ **Reverse Proxy**: Configure a proper reverse proxy (NGINX) with SSL/TLS certificates
   - 🔥 **Firewall**: Set up appropriate firewall rules to protect services
   - 💾 **Backups**: Implement automated backups for the database and object storage
   - 📈 **Monitoring**: Set up health checks and system monitoring
   - 🔄 **Updates**: Establish a process for safe updates and migrations

> **Note**: The frontend-prod service in docker-compose.yml builds the Svelte application with production optimizations and serves it using NGINX, which is more efficient than the development server. This is the key difference between development and production modes.

## Monitoring & Administration

### Celery Flower Dashboard

The application includes Flower for monitoring Celery tasks:

- Access the dashboard at: http://localhost:5555/flower
- Monitor task progress, worker status, and resource usage
- View real-time task execution and retries

### Database Management

For database operations:

### Database Management

For database operations, use the utility script:

```bash
# Connect to PostgreSQL shell
./opentr.sh shell postgres psql -U postgres -d opentranscribe

# Create a database backup
./opentr.sh backup

# Restore from backup
./opentr.sh restore ./backups/your_backup_file.sql

# Reset the database (warning: deletes all data)
./opentr.sh reset
```

### 🛠️ Utility Script Reference

OpenTranscribe includes a powerful utility script `opentr.sh` for common tasks:

```bash
# Start services (dev mode by default)
./opentr.sh start [dev|prod]

# Stop all services
./opentr.sh stop

# Reset and reinitialize (deletes data!)
./opentr.sh reset [dev|prod]

# View logs
./opentr.sh logs [service]  # e.g., backend, frontend, postgres

# Check container status
./opentr.sh status

# Open a shell in a container
./opentr.sh shell [service]

# Create a database backup
./opentr.sh backup

# Restore database from backup
./opentr.sh restore [backup_file]

# Rebuild containers
./opentr.sh build
```

## 📁 Working with Media Files

### 🎵 Supported Formats

OpenTranscribe supports most common audio and video formats through FFmpeg integration:

- 🎧 **Audio Formats**: 
  - MP3 (most common compressed audio)
  - WAV (uncompressed audio, highest quality)
  - FLAC (lossless compressed audio)
  - M4A (Apple's AAC container)
  - AAC (Advanced Audio Coding)
  - OGG (open source audio format)

- 🎬 **Video Formats**: 
  - MP4 (most widely supported)
  - MOV (QuickTime format)
  - AVI (older but widely supported)
  - MKV (high quality container with multiple tracks)
  - WEBM (optimized for web)

### 🔄 Transcription Process

When you upload a file to OpenTranscribe, a sophisticated process begins:

1. 📤 **Upload & Storage**: The file is streamed to MinIO (S3-compatible object storage)
2. 📋 **Job Creation**: A transcription job is created and queued in Celery with appropriate priority
3. 🧠 **Audio Processing**: 
   - Audio is extracted from video files if necessary
   - Audio is normalized and prepared for transcription
   - Faster-Whisper processes the audio to generate text with timestamps
4. 👥 **Speaker Analysis**: PyAnnotate analyzes the audio for different speakers and creates voice embeddings
5. 🔗 **Alignment**: The transcript and speaker information are aligned and merged
6. 💽 **Storage & Indexing**: 
   - Results are saved to the PostgreSQL database
   - Text and metadata are indexed in OpenSearch for fast retrieval
   - Speaker embeddings are stored for future recognition
7. 🔔 **Notification**: The UI shows progress and notifies when complete via WebSockets

> **Note**: ⚠️ The transcription process is resource-intensive and currently under optimization. Processing long files may take significant time depending on your hardware. GPU acceleration significantly improves performance when available.

## 🛠️ Development Notes

### 📂 Project Structure

```
opentranscribe/
├── backend/                # Python FastAPI backend
│   ├── app/                # Application modules
│   │   ├── api/            # API endpoints and routers
│   │   ├── core/           # Core functionality and config
│   │   │   ├── celery.py   # Celery task queue configuration
│   │   │   ├── config.py   # Application configuration
│   │   │   └── security.py # Authentication and authorization
│   │   ├── models/         # SQLAlchemy database models
│   │   ├── schemas/        # Pydantic validation schemas
│   │   └── services/       # Business logic and external integrations
│   │       ├── search.py   # OpenSearch integration
│   │       ├── storage.py  # MinIO/S3 integration
│   │       └── transcription.py # Transcription pipeline
│   ├── models/             # AI model files (downloaded at runtime)
│   └── Dockerfile.dev      # Development Docker configuration
├── frontend/               # Svelte frontend application
│   ├── public/             # Static assets and resources
│   ├── src/                # Source code
│   │   ├── components/     # Reusable UI components
│   │   ├── routes/         # Page components and routing
│   │   ├── stores/         # Svelte stores for state management
│   │   ├── utils/          # Helper functions and utilities
│   │   └── App.svelte      # Main application component
│   ├── Dockerfile.dev      # Development Docker configuration
│   └── Dockerfile.prod     # Production optimization build
├── database/               # Database initialization and migrations
│   └── init_db.sql         # Initial schema setup
└── .env.example            # Example environment configuration
```

### 🌱 Current Development Status

**⚠️ Work in Progress**: OpenTranscribe is currently in active development with the following status:

- ✅ **Working Features**:
  - User authentication and file management
  - Web UI Interface with file upload

- 🚧 **In Progress**:
  - Basic audio/video upload and storage
  - Transcription with Faster-Whisper
  - Simple speaker diarization
  - Basic transcript viewing and playback
  - Advanced speaker recognition across files
  - Improved UI/UX for transcript editing
  - Search functionality optimization
  - Full summarization capabilities
  - Error handling and system stability

- 📅 **Future Work**:
  - Advanced analytics and insights
  - Public API for integrations
  - Mobile optimization
  - Enterprise features (teams, sharing, etc.)
  - Offline processing mode

### 👥 Contributing

We welcome contributions to help improve OpenTranscribe! Here's how you can help:

- 🐛 Report bugs and issues you encounter
- 💡 Suggest new features or improvements
- 🔧 Submit pull requests for fixes or enhancements
- 📚 Improve documentation and examples
- 🧪 Add tests to improve reliability

Please check the issues list for specific areas where help is needed.

## 🔍 Troubleshooting

### ⚠️ Common Issues

- 🖥️ **GPU not detected**: 
  - Verify your NVIDIA drivers are properly installed: `nvidia-smi` should display your GPU
  - Ensure CUDA is installed and compatible with the container runtime
  - Check that the appropriate devices are passed to the container in docker-compose.yml
  - Try setting USE_GPU=false in .env for CPU-only operation (will be slower)

- 🎞️ **Media processing errors**: 
  - Ensure FFmpeg is properly configured in the container
  - Check if your media file is corrupted or in an unsupported format
  - Look at the celery-worker logs for specific error messages
  - Try converting your media using an external tool first

- 🐢 **Slow transcription**: 
  - Consider using a smaller Whisper model variant (medium or small instead of large)
  - Add more GPU memory to the worker container
  - For very long files, consider splitting them into smaller segments
  - CPU transcription is significantly slower than GPU - consider GPU hardware

- 🗄️ **Database issues**:
  - If PostgreSQL fails to start, check if the port is already in use
  - Use the reset_and_init.sh script to reinitialize the database
  - Check if the database name matches in all configurations (should be 'opentranscribe')

- 🌐 **Network issues**:
  - Ensure all ports specified in docker-compose.yml are available
  - Check if firewalls or proxies are blocking connections between services

### 📊 Logs and Monitoring

To view logs for specific services, use the following commands:

```bash
# Backend API logs
docker compose logs -f backend

# Celery worker logs (AI processing)
docker compose logs -f celery-worker

# Frontend development server logs
docker compose logs -f frontend

# Production frontend logs
docker compose logs -f frontend-prod

# Database logs
docker compose logs -f postgres

# All logs combined
docker compose logs -f
```

For convenience during development:
- The start-dev.sh script automatically opens separate log windows for each service
- The reset_and_init.sh script also opens logs after initialization
- Flower dashboard (http://localhost:5555/flower) provides detailed task monitoring

### 🔄 Reset and Recovery

If you encounter persistent issues, a full reset often helps:

```bash
# Full development reset
./reset_and_init.sh dev

# Full production reset
./reset_and_init.sh prod
```

This will stop all containers, remove volumes (clearing all data), and restart with a fresh environment.

## License

[MIT](LICENSE)
