<div align="center">
  <img src="assets/logo-banner.png" alt="OpenTranscribe Logo" width="400">
  
  **AI-Powered Transcription and Media Analysis Platform**
</div>

OpenTranscribe is a powerful, containerized web application for transcribing and analyzing audio/video files using state-of-the-art AI models. Built with modern technologies and designed for scalability, it provides an end-to-end solution for speech-to-text conversion, speaker identification, and content analysis.

> **Note**: This application is 99.9% created by AI using Windsurf and various commercial LLMs, demonstrating the power of AI-assisted development.

## ✨ Key Features

### 🎧 **Advanced Transcription**
- **High-Accuracy Speech Recognition**: Powered by WhisperX with faster-whisper backend
- **Word-Level Timestamps**: Precise timing for every word using WAV2VEC2 alignment
- **Multi-Language Support**: Transcribe in multiple languages with automatic English translation
- **Batch Processing**: 70x realtime speed with large-v2 model on GPU

### 👥 **Smart Speaker Management**
- **Automatic Speaker Diarization**: Identify different speakers using PyAnnote.audio
- **Cross-Recording Recognition**: Voice fingerprinting to recognize speakers across files
- **Custom Speaker Labels**: Edit and manage speaker names and information
- **Speaker Analytics**: View speaking time distribution and interaction patterns

### 🎬 **Rich Media Support**
- **Universal Format Support**: Audio (MP3, WAV, FLAC, M4A) and Video (MP4, MOV, AVI, MKV)
- **Large File Support**: Upload files up to 4GB for GoPro and high-quality video content
- **Interactive Media Player**: Click transcript to navigate playback
- **Metadata Extraction**: Comprehensive file information using ExifTool
- **Subtitle Export**: Generate SRT/VTT files for accessibility
- **File Reprocessing**: Re-run AI analysis while preserving user comments and annotations

### 🔍 **Powerful Search & Discovery**
- **Hybrid Search**: Combine keyword and semantic search capabilities
- **Full-Text Indexing**: Lightning-fast content search with OpenSearch
- **Advanced Filtering**: Filter by speaker, date, tags, duration, and more
- **Smart Tagging**: Organize content with custom tags and categories
- **Collections System**: Group related media files into organized collections for better project management

### 📊 **Analytics & Insights**
- **Content Analysis**: Word count, speaking time, and conversation flow
- **Speaker Statistics**: Individual speaker metrics and participation
- **Sentiment Analysis**: Understand tone and emotional content
- **Automated Summaries**: Generate concise summaries using local LLMs

### 💬 **Collaboration Features**
- **Time-Stamped Comments**: Add annotations at specific moments
- **User Management**: Role-based access control (admin/user)
- **Export Options**: Download transcripts in multiple formats
- **Real-Time Updates**: Live progress tracking with detailed WebSocket notifications
- **Enhanced Progress Tracking**: 13 granular processing stages with descriptive messages
- **Collection Management**: Create, organize, and share collections of related media files

## 🛠️ Technology Stack

### **Frontend**
- **Svelte** - Reactive UI framework with excellent performance
- **TypeScript** - Type-safe development with modern JavaScript
- **Progressive Web App** - Offline capabilities and native-like experience
- **Responsive Design** - Seamless experience across all devices

### **Backend**
- **FastAPI** - High-performance async Python web framework
- **SQLAlchemy 2.0** - Modern ORM with type safety
- **Celery + Redis** - Distributed task processing for AI workloads
- **WebSocket** - Real-time communication for live updates

### **AI/ML Stack**
- **WhisperX** - Advanced speech recognition with alignment
- **PyAnnote.audio** - Speaker diarization and voice analysis
- **Faster-Whisper** - Optimized inference engine
- **Local LLMs** - Privacy-focused text processing

### **Infrastructure**
- **PostgreSQL** - Reliable relational database
- **MinIO** - S3-compatible object storage
- **OpenSearch** - Full-text and vector search engine
- **Docker** - Containerized deployment
- **NGINX** - Production web server

## 🚀 Quick Start

### Prerequisites

```bash
# Required
- Docker and Docker Compose
- Git
- 8GB+ RAM (16GB+ recommended)

# Recommended for optimal performance
- NVIDIA GPU with CUDA support
- 50GB+ free disk space (for AI models)
```

### Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yourusername/OpenTranscribe.git
   cd OpenTranscribe
   
   # Make utility script executable
   chmod +x opentr.sh
   ```

2. **Environment Configuration**
   ```bash
   # Copy environment template
   cp .env.example .env
   
   # Edit .env file with your settings (optional for development)
   # Key variables:
   # - HUGGINGFACE_TOKEN (required for speaker diarization)
   # - GPU settings for optimal performance
   ```

3. **Start OpenTranscribe**
   ```bash
   # Start in development mode (with hot reload)
   ./opentr.sh start dev
   
   # Or start in production mode
   ./opentr.sh start prod
   ```

4. **Access the Application**
   - 🌐 **Web Interface**: http://localhost:5173
   - 📚 **API Documentation**: http://localhost:8080/docs
   - 🌺 **Task Monitor**: http://localhost:5555/flower
   - 🔍 **Search Engine**: http://localhost:9200
   - 📁 **File Storage**: http://localhost:9091

## 📋 OpenTranscribe Utility Commands

The `opentr.sh` script provides comprehensive management for all application operations:

### **Basic Operations**
```bash
# Start the application
./opentr.sh start [dev|prod]     # Start in development or production mode
./opentr.sh stop                 # Stop all services
./opentr.sh status               # Show container status
./opentr.sh logs [service]       # View logs (all or specific service)
```

### **Development Workflow**
```bash
# Service management
./opentr.sh restart-backend      # Restart API and workers without database reset
./opentr.sh restart-frontend     # Restart frontend only
./opentr.sh restart-all          # Restart all services without data loss

# Container rebuilding (after code changes)
./opentr.sh rebuild-backend      # Rebuild backend with new code
./opentr.sh rebuild-frontend     # Rebuild frontend with new code
./opentr.sh build                # Rebuild all containers
```

### **Database Management**
```bash
# Data operations (⚠️ DESTRUCTIVE)
./opentr.sh reset [dev|prod]     # Complete reset - deletes ALL data!
./opentr.sh init-db              # Initialize database without container reset

# Backup and restore
./opentr.sh backup               # Create timestamped database backup
./opentr.sh restore [file]       # Restore from backup file
```

### **System Administration**
```bash
# Maintenance
./opentr.sh clean                # Remove unused containers and images
./opentr.sh health               # Check service health status
./opentr.sh shell [service]      # Open shell in container

# Available services: backend, frontend, postgres, redis, minio, opensearch, celery-worker
```

### **Monitoring and Debugging**
```bash
# View specific service logs
./opentr.sh logs backend         # API server logs
./opentr.sh logs celery-worker   # AI processing logs
./opentr.sh logs frontend        # Frontend development logs
./opentr.sh logs postgres        # Database logs

# Follow logs in real-time
./opentr.sh logs backend -f
```

## 🎯 Usage Guide

### **Getting Started**

1. **User Registration**
   - Navigate to http://localhost:5173
   - Create an account or use default admin credentials
   - Set up your profile and preferences

2. **Upload Your First File**
   - Click \"Upload Files\" or drag-and-drop media files (up to 4GB)
   - Supported formats: MP3, WAV, MP4, MOV, and more
   - Files are automatically queued for processing

3. **Monitor Processing**
   - Watch detailed real-time progress with 13 processing stages
   - View task status in Flower monitor
   - Receive live WebSocket notifications for all status changes

4. **Explore Your Transcript**
   - Click on transcript text to navigate media playback
   - Edit speaker names and add custom labels
   - Add time-stamped comments and annotations
   - Reprocess files to improve accuracy while preserving your edits

### **Advanced Features**

#### **Speaker Management**
```
👥 Automatic Detection → 🏷️ Custom Labels → 🔍 Cross-File Recognition
```
- Speakers are automatically detected and assigned labels
- Edit speaker names for better organization
- System learns to recognize speakers across different files

#### **Search and Discovery**
```
🔍 Keyword Search → 🧠 Semantic Search → 🏷️ Smart Filtering
```
- Search transcript content with advanced filters
- Use semantic search to find related concepts
- Organize content with custom tags and categories

#### **Collections Management**
```
📁 Create Collections → 📂 Organize Files → 🏷️ Bulk Operations
```
- Group related media files into named collections
- Filter library view by specific collections
- Bulk add/remove files from collections
- Manage collection metadata and descriptions

#### **Export and Integration**
```
📄 Multiple Formats → 📺 Subtitle Files → 🔗 API Access
```
- Export transcripts as TXT, JSON, or CSV
- Generate SRT/VTT subtitle files
- Access data programmatically via REST API

## 📁 Project Structure

```
OpenTranscribe/
├── 📁 backend/                 # Python FastAPI backend
│   ├── 📁 app/                # Application modules
│   │   ├── 📁 api/            # REST API endpoints
│   │   ├── 📁 models/         # Database models
│   │   ├── 📁 services/       # Business logic
│   │   ├── 📁 tasks/          # Background AI processing
│   │   ├── 📁 utils/          # Common utilities
│   │   └── 📁 db/             # Database configuration
│   ├── 📁 scripts/            # Admin and maintenance scripts
│   ├── 📁 tests/              # Comprehensive test suite
│   └── 📄 README.md           # Backend documentation
├── 📁 frontend/               # Svelte frontend application
│   ├── 📁 src/                # Source code
│   │   ├── 📁 components/     # Reusable UI components
│   │   ├── 📁 routes/         # Page components
│   │   ├── 📁 stores/         # State management
│   │   └── 📁 styles/         # CSS and themes
│   └── 📄 README.md           # Frontend documentation
├── 📁 database/               # Database initialization
├── 📁 models_ai/              # AI model storage (runtime)
├── 📁 scripts/                # Utility scripts
├── 📄 docker-compose.yml      # Container orchestration
├── 📄 opentr.sh               # Main utility script
└── 📄 README.md               # This file
```

## 🔧 Configuration

### **Environment Variables**

#### **Core Application**
```bash
# Database
DATABASE_URL=postgresql://postgres:password@postgres:5432/opentranscribe

# Security
SECRET_KEY=your-super-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key

# Object Storage
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_BUCKET_NAME=transcribe-app
```

#### **AI Processing**
```bash
# Required for speaker diarization
HUGGINGFACE_TOKEN=your_huggingface_token_here

# Model configuration
WHISPER_MODEL=large-v2              # large-v2, medium, small, base
COMPUTE_TYPE=float16                # float16, int8
BATCH_SIZE=16                       # Reduce if GPU memory limited

# Speaker detection
MIN_SPEAKERS=1                      # Minimum speakers to detect
MAX_SPEAKERS=10                     # Maximum speakers to detect
```

#### **Performance Tuning**
```bash
# GPU settings
USE_GPU=true                        # Enable GPU acceleration
CUDA_VISIBLE_DEVICES=0              # GPU device selection

# Resource limits
MAX_UPLOAD_SIZE=4GB                 # Maximum file size (supports GoPro videos)
CELERY_WORKER_CONCURRENCY=2         # Concurrent tasks
```

### **Production Deployment**

For production use, ensure you:

1. **Security Configuration**
   ```bash
   # Generate strong secrets
   openssl rand -hex 32  # For SECRET_KEY
   openssl rand -hex 32  # For JWT_SECRET_KEY
   
   # Set strong database passwords
   # Configure proper firewall rules
   # Set up SSL/TLS certificates
   ```

2. **Performance Optimization**
   ```bash
   # Use production environment
   NODE_ENV=production
   
   # Configure resource limits
   # Set up monitoring and logging
   # Configure backup strategies
   ```

3. **Reverse Proxy Setup**
   ```nginx
   # Example NGINX configuration
   server {
       listen 80;
       server_name your-domain.com;
       
       location / {
           proxy_pass http://localhost:5173;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
       
       location /api {
           proxy_pass http://localhost:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

## 🧪 Development

### **Development Environment**
```bash
# Start development with hot reload
./opentr.sh start dev

# Backend development
cd backend/
pip install -r requirements.txt
pytest tests/                    # Run tests
black app/                       # Format code
flake8 app/                      # Lint code

# Frontend development  
cd frontend/
npm install
npm run dev                      # Development server
npm run test                     # Run tests
npm run lint                     # Lint code
```

### **Testing**
```bash
# Backend tests
./opentr.sh shell backend
pytest tests/                    # All tests
pytest tests/api/                # API tests only
pytest --cov=app tests/          # With coverage

# Frontend tests
cd frontend/
npm run test                     # Unit tests
npm run test:e2e                 # End-to-end tests
npm run test:components          # Component tests
```

### **Contributing**
We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## 🔍 Troubleshooting

### **Common Issues**

#### **GPU Not Detected**
```bash
# Check GPU availability
nvidia-smi

# Verify Docker GPU support
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi

# Set CPU-only mode if needed
echo "USE_GPU=false" >> .env
```

#### **Memory Issues**
```bash
# Reduce model size
echo "WHISPER_MODEL=medium" >> .env
echo "BATCH_SIZE=8" >> .env
echo "COMPUTE_TYPE=int8" >> .env

# Monitor memory usage
docker stats
```

#### **Slow Transcription**
- Use GPU acceleration (`USE_GPU=true`)
- Reduce model size (`WHISPER_MODEL=medium`)
- Increase batch size if you have GPU memory
- Split large files into smaller segments

#### **Database Connection Issues**
```bash
# Reset database
./opentr.sh reset dev

# Check database logs
./opentr.sh logs postgres

# Verify database is running
./opentr.sh shell postgres psql -U postgres -l
```

#### **Container Issues**
```bash
# Check service status
./opentr.sh status

# Clean up resources
./opentr.sh clean

# Full reset (⚠️ deletes all data)
./opentr.sh reset dev
```

### **Getting Help**

- 📚 **Documentation**: Check README files in each component directory
- 🐛 **Issues**: Report bugs on GitHub Issues
- 💬 **Discussions**: Ask questions in GitHub Discussions
- 📊 **Monitoring**: Use Flower dashboard for task debugging

## 📈 Performance & Scalability

### **Hardware Recommendations**

#### **Minimum Requirements**
- 8GB RAM
- 4 CPU cores
- 50GB disk space
- Any modern GPU (optional but recommended)

#### **Recommended Configuration**
- 16GB+ RAM
- 8+ CPU cores
- 100GB+ SSD storage
- NVIDIA GPU with 8GB+ VRAM (RTX 3070 or better)
- High-speed internet for model downloads

#### **Production Scale**
- 32GB+ RAM
- 16+ CPU cores
- Multiple GPUs for parallel processing
- Fast NVMe storage
- Load balancer for multiple instances

### **Performance Tuning**

```bash
# GPU optimization
COMPUTE_TYPE=float16              # Use half precision
BATCH_SIZE=32                     # Increase for more GPU memory
WHISPER_MODEL=large-v2            # Best accuracy

# CPU optimization (if no GPU)
COMPUTE_TYPE=int8                 # Use quantization
BATCH_SIZE=1                      # Reduce memory usage
WHISPER_MODEL=base                # Faster processing
```

## 🔐 Security Considerations

### **Data Privacy**
- All processing happens locally - no data sent to external services
- Optional: Disable external model downloads for air-gapped environments
- User data is encrypted at rest and in transit
- Configurable data retention policies

### **Access Control**
- Role-based permissions (admin/user)
- File ownership validation
- API rate limiting
- Secure session management

### **Network Security**
- All services run in isolated Docker network
- Configurable firewall rules
- Optional SSL/TLS termination
- Secure default configurations

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **OpenAI Whisper** - Foundation speech recognition model
- **WhisperX** - Enhanced alignment and diarization
- **PyAnnote.audio** - Speaker diarization capabilities
- **FastAPI** - Modern Python web framework
- **Svelte** - Reactive frontend framework
- **Docker** - Containerization platform

## 🔗 Useful Links

- 📚 **Documentation**: [Complete documentation index](BACKEND_DOCUMENTATION.md)
- 🛠️ **API Reference**: http://localhost:8080/docs (when running)
- 🌺 **Task Monitor**: http://localhost:5555/flower (when running)
- 🤝 **Contributing**: [Contribution guidelines](CONTRIBUTING.md)
- 🐛 **Issues**: [GitHub Issues](https://github.com/yourusername/OpenTranscribe/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/yourusername/OpenTranscribe/discussions)

---

**Built with ❤️ using AI assistance and modern open-source technologies.**

*OpenTranscribe demonstrates the power of AI-assisted development while maintaining full local control over your data and processing.*