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
- **Audio Waveform Visualization**: Interactive waveform player with precise timing and click-to-seek
- **Browser Recording**: Built-in microphone recording with real-time audio level monitoring
- **Recording Controls**: Pause/resume recording with duration tracking and quality settings

### 👥 **Smart Speaker Management**
- **Automatic Speaker Diarization**: Identify different speakers using PyAnnote.audio
- **Cross-Video Speaker Recognition**: AI-powered voice fingerprinting to identify speakers across different media files
- **Speaker Profile System**: Create and manage global speaker profiles that persist across all transcriptions
- **Intelligent Speaker Suggestions**: Consolidated speaker identification with confidence scoring and automatic profile matching
- **LLM-Enhanced Speaker Recognition**: Content-based speaker identification using conversational context analysis
- **Profile Embedding Service**: Advanced voice similarity matching using vector embeddings for cross-video speaker linking
- **Smart Speaker Status Tracking**: Comprehensive speaker verification status with computed fields for UI optimization
- **Auto-Profile Creation**: Automatic speaker profile creation and assignment when speakers are labeled
- **Retroactive Speaker Matching**: Cross-video speaker matching with automatic label propagation for high-confidence matches
- **Custom Speaker Labels**: Edit and manage speaker names and information with intelligent suggestions
- **Speaker Analytics**: View speaking time distribution, cross-media appearances, and interaction patterns

### 🎬 **Rich Media Support**
- **Universal Format Support**: Audio (MP3, WAV, FLAC, M4A) and Video (MP4, MOV, AVI, MKV)
- **Large File Support**: Upload files up to 4GB for GoPro and high-quality video content
- **Interactive Media Player**: Click transcript to navigate playback
- **Custom File Titles**: Edit display names for media files with real-time search index updates
- **Advanced Upload Manager**: Floating, draggable upload manager with real-time progress tracking
- **Concurrent Upload Processing**: Multiple file uploads with queue management and retry logic
- **Intelligent Upload System**: Duplicate detection, hash verification, and automatic recovery
- **Metadata Extraction**: Comprehensive file information using ExifTool
- **Subtitle Export**: Generate SRT/VTT files for accessibility
- **File Reprocessing**: Re-run AI analysis while preserving user comments and annotations
- **Auto-Recovery System**: Intelligent detection and recovery of stuck or failed file processing

### 🔍 **Powerful Search & Discovery**
- **Hybrid Search**: Combine keyword and semantic search capabilities
- **Full-Text Indexing**: Lightning-fast content search with OpenSearch
- **Advanced Filtering**: Filter by speaker, date, tags, duration, and more
- **Smart Tagging**: Organize content with custom tags and categories
- **Collections System**: Group related media files into organized collections for better project management

### 📊 **Analytics & Insights**
- **Advanced Content Analysis**: Comprehensive speaker analytics including talk time, interruption detection, and turn-taking patterns
- **Speaker Performance Metrics**: Speaking pace (WPM), question frequency, and conversation flow analysis
- **Meeting Efficiency Analytics**: Silence ratio analysis and participation balance tracking
- **Real-Time Analytics Computation**: Server-side analytics computation with automatic refresh capabilities
- **Cross-Video Speaker Analytics**: Track speaker patterns and participation across multiple recordings
- **AI-Powered Summarization**: Generate BLUF (Bottom Line Up Front) format summaries with meeting insights
- **Multi-Provider LLM Support**: Use local vLLM, OpenAI, Ollama, Claude, or OpenRouter for AI features
- **Intelligent Section Processing**: Automatically handles transcripts of any length using section-by-section analysis
- **Custom AI Prompts**: Create and manage custom summarization prompts for different content types
- **LLM Configuration Management**: User-specific LLM settings with encrypted API key storage
- **Provider Testing**: Test LLM connections and validate configurations before use

### 💬 **Collaboration Features**
- **Time-Stamped Comments**: Add annotations at specific moments
- **User Management**: Role-based access control (admin/user) with personalized settings
- **Recording Settings Management**: User-specific audio recording preferences with quality controls
- **Export Options**: Download transcripts in multiple formats
- **Real-Time Updates**: Live progress tracking with detailed WebSocket notifications
- **Enhanced Progress Tracking**: 13 granular processing stages with descriptive messages
- **Smart Notification System**: Persistent notifications with unread count badges and progress updates
- **WebSocket Integration**: Real-time updates for transcription, summarization, and upload progress
- **Collection Management**: Create, organize, and share collections of related media files
- **Smart Error Recovery**: User-friendly error messages with specific guidance and auto-recovery options
- **Full-Screen Transcript View**: Dedicated modal for reading and searching long transcripts
- **Auto-Refresh Systems**: Background updates for file status without manual refreshing

### 🎙️ **Recording & Audio Features**
- **Browser-Based Recording**: Direct microphone recording with no plugins required
- **Real-Time Audio Level Monitoring**: Visual audio level feedback during recording
- **Multi-Device Support**: Choose from available microphone devices
- **Recording Quality Control**: Configurable bitrate and format settings
- **Pause/Resume Recording**: Full recording session control with duration tracking
- **Background Upload Processing**: Seamless integration with upload queue system
- **Recording Session Management**: Persistent recording state with navigation warnings

### 🤖 **AI-Powered Features**
- **Comprehensive LLM Integration**: Support for 6+ providers (OpenAI, Claude, vLLM, Ollama, etc.)
- **Custom Prompt Management**: Create and manage AI prompts for different content types
- **Encrypted Configuration Storage**: Secure API key storage with user-specific settings
- **Provider Connection Testing**: Validate LLM configurations before use
- **Intelligent Content Processing**: Context-aware summarization with section-by-section analysis
- **BLUF Format Summaries**: Bottom Line Up Front structured summaries with action items
- **Multi-Model Support**: Works with models from 3B to 200B+ parameters
- **Local & Cloud Processing**: Support for both local (privacy-first) and cloud AI providers

### 📱 **Enhanced User Experience**
- **Progressive Web App**: Installable app experience with offline capabilities
- **Responsive Design**: Optimized for desktop, tablet, and mobile devices
- **Interactive Waveform Player**: Click-to-seek audio visualization with precise timing
- **Floating Upload Manager**: Draggable upload interface with real-time progress
- **Smart Modal System**: Consistent modal design with improved accessibility
- **Enhanced Data Formatting**: Server-side formatting service for consistent display of dates, durations, and file sizes
- **Error Categorization**: Intelligent error classification with user-friendly suggestions and retry guidance
- **Smart Status Management**: Comprehensive file and task status tracking with formatted display text
- **Auto-Refresh Systems**: Background data updates without manual page refreshing
- **Theme Support**: Seamless dark/light mode switching
- **Keyboard Shortcuts**: Efficient navigation and control via hotkeys

## 🛠️ Technology Stack

### **Frontend**
- **Svelte** - Reactive UI framework with excellent performance
- **TypeScript** - Type-safe development with modern JavaScript and comprehensive ESLint integration
- **Progressive Web App** - Offline capabilities and native-like experience
- **Responsive Design** - Seamless experience across all devices
- **Advanced UI Components** - Draggable upload manager, modal consistency, and real-time status updates
- **Code Quality Tooling** - ESLint, TypeScript strict mode, and automated formatting

### **Backend**
- **FastAPI** - High-performance async Python web framework
- **SQLAlchemy 2.0** - Modern ORM with type safety
- **Celery + Redis** - Distributed task processing for AI workloads
- **WebSocket** - Real-time communication for live updates

### **AI/ML Stack**
- **WhisperX** - Advanced speech recognition with alignment
- **PyAnnote.audio** - Speaker diarization and voice analysis
- **Faster-Whisper** - Optimized inference engine
- **Multi-Provider LLM Integration** - Support for vLLM, OpenAI, Ollama, Anthropic Claude, and OpenRouter
- **Local LLM Support** - Privacy-focused processing with vLLM and Ollama
- **Intelligent Context Processing** - Section-by-section analysis handles unlimited transcript lengths
- **Universal Model Compatibility** - Works with any model size from 3B to 200B+ parameters

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
- 8GB+ RAM (16GB+ recommended)

# Recommended for optimal performance
- NVIDIA GPU with CUDA support
```

### Quick Installation (Using Docker Hub Images)

Run this one-liner to download and set up OpenTranscribe using our pre-built Docker Hub images:

```bash
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

Then follow the on-screen instructions. The setup script will:
- Detect your hardware (NVIDIA GPU, Apple Silicon, or CPU)
- Download the production Docker Compose file
- Configure environment variables with optimal settings for your hardware
- **Prompt for your HuggingFace token** (required for speaker diarization)
- **Automatically download and cache AI models (~2.5GB)** if token is provided
- Set up the management script (`opentranscribe.sh`)

**Note:** The script will prompt you for your HuggingFace token during setup. If you provide it, AI models will be downloaded and cached before Docker starts, ensuring the app is ready to use immediately. If you skip this step, models will download on first use (10-30 minute delay).

Once setup is complete, start OpenTranscribe with:

```bash
cd opentranscribe
./opentranscribe.sh start
```

The Docker images are available on Docker Hub as separate repositories:
- `davidamacey/opentranscribe-backend`: Backend service (also used for celery-worker and flower)
- `davidamacey/opentranscribe-frontend`: Frontend service

Access the web interface at http://localhost:5173

### Manual Installation (From Source)

1. **Clone the Repository**
   ```bash
   git clone https://github.com/davidamacey/OpenTranscribe.git
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
   - 📚 **API Documentation**: http://localhost:5174/docs
   - 🌺 **Task Monitor**: http://localhost:5175/flower
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

2. **Upload or Record Content**
   - **File Upload**: Click \"Upload Files\" or drag-and-drop media files (up to 4GB)
   - **Direct Recording**: Use the microphone button in the navbar for browser-based recording
   - **URL Processing**: Paste YouTube or media URLs for automatic processing
   - Supported formats: MP3, WAV, MP4, MOV, and more
   - Files are automatically queued for concurrent processing

3. **Monitor Processing**
   - Watch detailed real-time progress with 13 processing stages
   - Use the floating upload manager for multi-file progress tracking
   - View task status in Flower monitor or notifications panel
   - Receive live WebSocket notifications for all status changes

4. **Explore Your Content**
   - **Interactive Transcript**: Click on transcript text to navigate media playback
   - **Waveform Player**: Click on audio waveform for precise seeking
   - **Custom Titles**: Edit file display names for better organization and searchability
   - **Speaker Management**: Edit speaker names and add custom labels
   - **AI Summaries**: Generate BLUF format summaries with custom prompts
   - **Comments**: Add time-stamped comments and annotations
   - **Collections**: Organize files into themed collections
   - **Full-Screen View**: Use transcript modal for detailed reading and searching

5. **Configure AI Features** (Optional)
   - Set up LLM providers in User Settings for AI summarization
   - Create custom prompts for different content types
   - Test provider connections before processing

### **Advanced Features**

#### **Recording Workflow**
```
🎙️ Device Selection → 📊 Level Monitoring → ⏸️ Session Control → ⬆️ Background Upload
```
- Choose from available microphone devices
- Monitor real-time audio levels during recording
- Pause/resume recording sessions with duration tracking
- Seamless integration with background upload processing

#### **AI-Powered Processing**
```
🤖 LLM Configuration → 📝 Custom Prompts → 🔍 Content Analysis → 📊 BLUF Summaries
```
- Configure multiple LLM providers (OpenAI, Claude, vLLM, Ollama, etc.)
- Create custom prompts for different content types (meetings, interviews, podcasts)
- Test provider connections and validate configurations
- Generate structured summaries with action items and key decisions

#### **Speaker Management**
```
👥 Automatic Detection → 🤖 AI Recognition → 🏷️ Profile Management → 🔍 Cross-Media Tracking
```
- Speakers are automatically detected and assigned labels using advanced AI diarization
- AI suggests speaker identities based on voice fingerprinting across your media library
- Create global speaker profiles that persist across all your transcriptions
- Accept or reject AI suggestions with confidence scores to improve accuracy over time
- Track speaker appearances across multiple media files with detailed analytics

#### **Advanced Upload Management**
```
⬆️ Concurrent Uploads → 📊 Progress Tracking → 🔄 Retry Logic → 📋 Queue Management
```
- Floating, draggable upload manager with real-time progress
- Multiple file uploads with intelligent queue processing
- Automatic retry logic for failed uploads with exponential backoff
- Duplicate detection with hash verification

#### **Search and Discovery**
```
🔍 Keyword Search → 🧠 Semantic Search → 🏷️ Smart Filtering → 🎯 Waveform Navigation
```
- Search transcript content with advanced filters
- Use semantic search to find related concepts
- Click-to-seek navigation via interactive waveform visualization
- Organize content with custom tags and categories

#### **Collections Management**
```
📁 Create Collections → 📂 Organize Files → 🏷️ Bulk Operations → 🎯 Inline Editing
```
- Group related media files into named collections
- Inline collection editing with tag-style interface
- Filter library view by specific collections
- Bulk add/remove files from collections with drag-and-drop support

#### **Real-Time Notifications**
```
🔔 Progress Updates → 📊 Status Tracking → 🔄 WebSocket Integration → ✅ Completion Alerts
```
- Persistent notification panel with unread count badges
- Real-time updates for transcription, summarization, and upload progress
- WebSocket integration for instant status updates
- Smart notification grouping and auto-refresh systems

#### **Export and Integration**
```
📄 Multiple Formats → 📺 Subtitle Files → 🔗 API Access → 🎬 Media Downloads
```
- Export transcripts as TXT, JSON, or CSV
- Generate SRT/VTT subtitle files with embedded timing
- Access data programmatically via comprehensive REST API
- Download media files with embedded subtitles

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
# Required for speaker diarization - see setup instructions below
HUGGINGFACE_TOKEN=your_huggingface_token_here

# Model configuration
WHISPER_MODEL=large-v2              # large-v2, medium, small, base
COMPUTE_TYPE=float16                # float16, int8
BATCH_SIZE=16                       # Reduce if GPU memory limited

# Speaker detection
MIN_SPEAKERS=1                      # Minimum speakers to detect
MAX_SPEAKERS=10                     # Maximum speakers to detect

# Model caching (recommended)
MODEL_CACHE_DIR=./models            # Directory to store downloaded AI models
```

#### **LLM Configuration (AI Features)**
OpenTranscribe offers flexible AI deployment options. Choose the approach that best fits your infrastructure:

**🔧 Quick Setup Options:**

1. **Cloud-Only (Recommended for Most Users)**
   ```bash
   # Configure for OpenAI in .env
   LLM_PROVIDER=openai
   OPENAI_API_KEY=your_openai_key
   OPENAI_MODEL_NAME=gpt-4o-mini

   # Start without local LLM
   ./opentr.sh start dev
   ```

2. **Local vLLM (High-Performance GPUs)**
   ```bash
   # Configure for vLLM in .env
   LLM_PROVIDER=vllm
   VLLM_MODEL_NAME=gpt-oss-20b

   # Start with vLLM service (requires 16GB+ VRAM)
   docker compose -f docker-compose.yml -f docker-compose.vllm.yml up
   ```

3. **Local Ollama (Consumer GPUs)**
   ```bash
   # Configure for Ollama in .env
   LLM_PROVIDER=ollama
   OLLAMA_MODEL_NAME=llama3.2:3b-instruct-q4_K_M

   # Edit docker-compose.vllm.yml and uncomment ollama service
   # Then start with both compose files
   docker compose -f docker-compose.yml -f docker-compose.vllm.yml up
   ```

**📋 Complete Provider Configuration:**
```bash
# Cloud Providers (configure in .env)
LLM_PROVIDER=openai                  # openai, anthropic, custom (openrouter)
OPENAI_API_KEY=your_openai_key       # OpenAI GPT models
ANTHROPIC_API_KEY=your_claude_key    # Anthropic Claude models
OPENROUTER_API_KEY=your_or_key       # OpenRouter (multi-provider)

# Local Providers (requires additional Docker services)
LLM_PROVIDER=vllm                    # Local vLLM server
LLM_PROVIDER=ollama                  # Local Ollama server
```

**🎯 Deployment Scenarios:**
- **💰 Cost-Effective**: OpenRouter with Claude Haiku (~$0.25/1M tokens)
- **🔒 Privacy-First**: Local vLLM or Ollama (no data leaves your server)
- **⚡ Performance**: OpenAI GPT-4o-mini (fastest cloud option)
- **📱 Small Models**: Even 3B Ollama models can handle hours of content via intelligent sectioning
- **🚫 No LLM**: Leave `LLM_PROVIDER` empty for transcription-only mode

See [LLM_DEPLOYMENT_OPTIONS.md](LLM_DEPLOYMENT_OPTIONS.md) for detailed setup instructions.

#### **🗂️ Model Caching**

OpenTranscribe automatically downloads and caches AI models for optimal performance. Models are saved locally and reused across container restarts.

**Default Setup:**
- All models are cached to `./models/` directory in your project folder
- Models persist between Docker container restarts
- No re-downloading required after initial setup

**Directory Structure:**
```
./models/
├── huggingface/          # PyAnnote + WhisperX models
│   ├── hub/             # WhisperX transcription models (~1.5GB)
│   └── transformers/    # PyAnnote transformer models
└── torch/               # PyTorch cache
    ├── hub/checkpoints/ # Wav2Vec2 alignment model (~360MB)
    └── pyannote/        # PyAnnote diarization models (~500MB)
```

**Custom Cache Location:**
```bash
# Set custom directory in your .env file
MODEL_CACHE_DIR=/path/to/your/models

# Examples:
MODEL_CACHE_DIR=~/ai-models          # Home directory
MODEL_CACHE_DIR=/mnt/storage/models  # Network storage
MODEL_CACHE_DIR=./cache              # Project subdirectory
```

**Storage Requirements:**
- **WhisperX Models**: ~1.5GB (depends on model size)
- **PyAnnote Models**: ~500MB (diarization + embedding)
- **Alignment Model**: ~360MB (Wav2Vec2)
- **Total**: ~2.5GB for complete setup```

### **🔑 HuggingFace Token Setup**

OpenTranscribe requires a HuggingFace token for speaker diarization and voice fingerprinting features. Follow these steps:

#### **1. Generate HuggingFace Token**
1. Visit [HuggingFace Settings > Access Tokens](https://huggingface.co/settings/tokens)
2. Click "New token" and select "Read" access
3. Copy the generated token

#### **2. Accept Model User Agreements**
You must accept the user agreements for these models:
- [Segmentation Model](https://huggingface.co/pyannote/segmentation-3.0) - Click "Agree and access repository"
- [Speaker Diarization Model](https://huggingface.co/pyannote/speaker-diarization-3.1) - Click "Agree and access repository"

#### **3. Configure Token**
Add your token to the environment configuration:

**For Production Installation:**
```bash
# The setup script will prompt you for your token
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

**For Manual Installation:**
```bash
# Add to .env file
echo "HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" >> .env
```

**Note:** Without a valid HuggingFace token, speaker diarization will be disabled and speakers will not be automatically detected or identified across different media files.

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
           proxy_pass http://localhost:5174;
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

- 📚 **Documentation**:
  - [Database Schema & Architecture](docs/database-schema.md) - ERD diagrams and system architecture
  - [Backend Documentation](docs/BACKEND_DOCUMENTATION.md)
  - [Prompt Engineering Guide](docs/PROMPT_ENGINEERING_README.md) - Best practices for LLM prompts
  - [Scripts Documentation](scripts/README.md) - Docker build and deployment guide
- 🛠️ **API Reference**: http://localhost:5174/docs (when running)
- 🌺 **Task Monitor**: http://localhost:5175/flower (when running)
- 🤝 **Contributing**: [Contribution guidelines](CONTRIBUTING.md)
- 🐛 **Issues**: [GitHub Issues](https://github.com/yourusername/OpenTranscribe/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/yourusername/OpenTranscribe/discussions)

---

**Built with ❤️ using AI assistance and modern open-source technologies.**

*OpenTranscribe demonstrates the power of AI-assisted development while maintaining full local control over your data and processing.*
