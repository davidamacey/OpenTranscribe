# Changelog

All notable changes to OpenTranscribe will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2025-12-15

### Overview
Major feature release integrating valuable contributions from the [@vfilon](https://github.com/vfilon) fork, along with critical UUID/ID standardization fixes and production infrastructure improvements.

### Added

#### Universal Media URL Support
- **1800+ Platform Support** - Expand beyond YouTube to support virtually any video platform via yt-dlp
- **Dynamic Source Detection** - Automatically detect source platform from yt-dlp metadata
- **User-Friendly Error Handling** - Clear messages for authentication-required platforms
- **Platform Guidance** - Helpful messages for common platforms (Vimeo, Instagram, TikTok, etc.)
- **Recommended Platforms** - YouTube, Dailymotion, Twitter/X highlighted as best supported

#### NGINX Reverse Proxy with SSL/TLS (Closes [#72](https://github.com/davidamacey/OpenTranscribe/issues/72))
- **Production-Ready SSL** - Full NGINX reverse proxy configuration for HTTPS deployments
- **docker-compose.nginx.yml** - Optional overlay for production environments
- **SSL Certificate Generation** - Script for self-signed certificates (`scripts/generate-ssl-cert.sh`)
- **WebSocket Proxy** - Full WebSocket support through NGINX
- **Large File Uploads** - 2GB upload support for large media files
- **Service Proxying** - Flower dashboard and MinIO console accessible through NGINX
- **Browser Microphone Recording** - Enabled on remote/network access via HTTPS

#### Infrastructure Improvements
- **GPU Overlay Separation** - `docker-compose.gpu.yml` for optional GPU support on cross-platform systems
- **Task Status Reconciliation** - Better handling of stuck tasks with multiple timestamp fallbacks
- **Auto-Refresh Analytics** - Analytics refresh when segment speaker changes
- **Ollama Context Window** - Configurable `num_ctx` parameter for Ollama LLM provider
- **Model-Aware Temperature** - Temperature handling based on model capabilities
- **Explicit Docker Image Names** - Cache efficiency with named images

#### Documentation
- **NGINX Setup Guide** - Comprehensive `docs/NGINX_SETUP.md` documentation
- **Fork Comparison** - `docs/FORK_COMPARISON_vfilon.md` with detailed analysis
- **Implementation Plan** - `docs/FORK_IMPLEMENTATION_PLAN.md` checklist
- **Test Videos** - `docs/testing/media_url_test_videos.md` with platform test URLs

### Changed

#### Backend
- **Service Rename** - `youtube_service.py` → `media_download_service.py` for platform-agnostic naming
- **URL Validation** - Generic HTTP/HTTPS URL pattern instead of YouTube-specific
- **Minio Version** - Updated minimum version to 7.2.18

#### Frontend
- **Media URL UI** - Renamed `youtubeUrl` → `mediaUrl` throughout FileUploader
- **Notification Text** - Changed "YouTube Processing" → "Video Processing" (all 7 languages)
- **Platform Info** - Added collapsible "Supported Platforms" section with limitations warning
- **WebSocket Token Encoding** - Added `encodeURIComponent()` for auth tokens

### Fixed

#### UUID/ID Standardization (60+ files)
- **Speaker Recommendations** - Fixed recommendations not showing for new videos
- **Profile Embedding Service** - Fixed returning UUID as `profile_id` when integer expected
- **Consistent ID Handling** - Backend uses integer IDs for DB, UUIDs for API responses
- **Frontend UUIDs** - All entity references now use UUID strings consistently
- **Comment System** - Fixed UUID handling in comments
- **Password Reset** - Fixed password reset flow
- **Transcript Segments** - Fixed segment update UUID handling

### Contributors

Special thanks to:
- **[@vfilon](https://github.com/vfilon)** - Original fork contributions (Universal Media URL concept, NGINX configuration, task reconciliation)

### Upgrade Notes

Users running self-hosted deployments should pull the latest images:
```bash
docker pull davidamacey/opentranscribe-frontend:v0.3.0
docker pull davidamacey/opentranscribe-backend:v0.3.0
```

For NGINX/SSL setup, see `docs/NGINX_SETUP.md`.

---

## [0.2.1] - 2025-12-13

### Overview
Security patch release addressing critical container vulnerabilities identified in security scans.

### Security

#### Container Base Image Updates
- **Frontend**: Upgraded `nginx:1.29.3-alpine3.22` → `nginx:1.29.4-alpine3.23`
- **Backend**: Upgraded `python:3.12-slim-bookworm` → `python:3.13-slim-trixie` (Debian 12 → Debian 13)

#### Resolved Critical CVEs (4 → 0)
- **CVE-2025-47917** (libmbedcrypto) - CRITICAL - Fixed in 3.6.4-2
- **CVE-2023-6879** (libaom3) - CRITICAL - Fixed in 3.12.1-1
- **CVE-2025-7458** (libsqlite3) - CRITICAL - Fixed in 3.46.1-7
- **CVE-2023-45853** (zlib) - CRITICAL - Fixed in 1.3.1

#### Frontend Security Fixes
- Fixed 3 HIGH severity libpng vulnerabilities
- Fixed 2 MEDIUM severity libpng vulnerabilities
- Fixed 1 MEDIUM severity busybox vulnerability
- Remaining: 3 tiff CVEs (no Alpine fix available)

#### Additional Improvements
- Added `HEALTHCHECK` instructions to both frontend and backend Dockerfiles
- Updated Python from 3.12 to 3.13
- Updated pip to latest version (25.3)

### Changed
- Backend now runs on Debian 13 "trixie" (released August 2025)
- Python site-packages path updated from 3.12 to 3.13

### Upgrade Notes
Users running self-hosted deployments should pull the latest images:
```bash
docker pull davidamacey/opentranscribe-frontend:v0.2.1
docker pull davidamacey/opentranscribe-backend:v0.2.1
```

---

## [0.2.0] - 2025-12-12

### Overview
Community-driven multilingual release! This version features significant contributions from the open source community, including 7 pull requests from [@SQLServerIO](https://github.com/SQLServerIO) (Wes Brown) and a critical multilingual feature request from [@LaboratorioInternacionalWeb](https://github.com/LaboratorioInternacionalWeb).

### Added

#### Multilingual Transcription Support
- **100+ Language Support** - Expanded from 50+ to 100+ languages via WhisperX
- **Configurable Source Language** - Auto-detect or manually specify source language for improved accuracy
- **Translation Toggle** - Choose to keep original language or translate to English (default: keep original)
- **Word-Level Alignment Indicators** - UI shows which languages (~42) support word-level timestamps
- **LLM Output Language** - Generate AI summaries in 12 languages (EN, ES, FR, DE, PT, ZH, JA, KO, IT, RU, AR, HI)

#### UI Internationalization (i18n)
- **7 UI Languages** - English, Spanish, French, German, Portuguese, Chinese, Japanese
- **Language Settings** - User-configurable UI language preference
- **Locale Store** - Persistent language preference with localStorage
- **Translation System** - Comprehensive i18n system across all frontend components

#### Speaker Management Enhancements
- **Speaker Merge UI** - Visual interface to combine duplicate speakers with segment preview
- **Segment Reassignment** - Automatic segment speaker reassignment during merge
- **Per-File Speaker Settings** - Configure min/max speakers at upload or reprocess time
- **User-Level Speaker Preferences** - Save default speaker detection settings (always prompt, use defaults, use custom)

#### LLM Integration Improvements
- **Anthropic Model Discovery** - Native /v1/models API for dynamic model listing
- **Model Auto-Discovery** - Extended to support vLLM, Ollama, and Anthropic providers
- **Edit Mode API Key Support** - Stored API keys work in edit mode (no need to re-enter)
- **Updated Default Models** - Anthropic: claude-opus-4-5-20251101, Ollama: llama3.2:latest
- **Improved Configuration UX** - Toast notifications replace inline errors, better API key toggle positioning

#### User Settings
- **Transcription Settings** - User-level transcription preferences stored in database
- **Garbage Cleanup Settings** - User-configurable automatic cleanup of erroneous segments
- **Automatic Database Migrations** - Migrations run automatically on startup

#### Admin & System
- **System Statistics** - CPU, memory, disk, and GPU usage visible to all authenticated users
- **Admin Password Reset** - Secure password reset with validation
- **Compact Action Buttons** - Icon-only action buttons with tooltips in admin UI

### Changed

- **Provider Consolidation** - `claude` provider deprecated in favor of `anthropic`
- **LLM Provider Enum** - Reordered with legacy CLAUDE at end
- **Error Display** - Converted inline errors to toast notifications in LLM config modal

### Fixed

- **Large Transcript Pagination** - Fixed page hanging with thousands of segments ([PR #110](https://github.com/davidamacey/OpenTranscribe/pull/110))
- **Garbage Segment Cleanup** - Automatic detection and removal of erroneous transcription segments ([PR #107](https://github.com/davidamacey/OpenTranscribe/pull/107))
- **UUID Admin Endpoints** - Fixed admin endpoints to use UUID instead of integer ID ([PR #106](https://github.com/davidamacey/OpenTranscribe/pull/106))
- **PyTorch 2.6+ Compatibility** - Updated for newer PyTorch versions ([PR #102](https://github.com/davidamacey/OpenTranscribe/pull/102))
- **vLLM Endpoint Configuration** - Fixed summaries not working with vLLM in OpenAI mode ([Issue #100](https://github.com/davidamacey/OpenTranscribe/issues/100))
- **API Key Whitespace** - Added .trim() to all API key validations
- **Race Conditions** - Fixed race conditions when editing existing LLM configurations
- **Speaker Dropdown Visibility** - Fixed flickering and visibility issues

### Code Quality

- **Reduced Cyclomatic Complexity** - Refactored 47 functions across 27 files
- **ESLint Integration** - Improved frontend linting and type safety
- **Removed Unused Code** - Cleaned up unused error variables and CSS classes

### Contributors

Special thanks to our community contributors:
- [@SQLServerIO](https://github.com/SQLServerIO) (Wes Brown) - 7 pull requests
- [@LaboratorioInternacionalWeb](https://github.com/LaboratorioInternacionalWeb) - Multilingual feature request

## [0.1.0] - 2025-11-05

### Overview
First official release of OpenTranscribe! This release marks the transition from internal development to public availability. What started as a weekend experiment in May 2025 has evolved into a full-featured, production-ready AI transcription platform over 6 months of dedicated development.

### Added

#### Core Transcription Features
- **WhisperX Integration** - High-accuracy speech recognition with faster-whisper backend
- **Word-Level Timestamps** - Precise timing for every word using WAV2VEC2 alignment
- **Multi-Language Support** - Transcribe in 50+ languages with automatic English translation
- **GPU Acceleration** - 70x realtime speed with large-v2 model on NVIDIA GPUs
- **CPU Fallback** - Complete CPU-only mode for systems without GPUs
- **Apple Silicon Support** - MPS acceleration for M1/M2/M3 Macs
- **Batch Processing** - Process multiple files concurrently with intelligent queue management

#### Speaker Diarization & Management
- **Automatic Speaker Detection** - PyAnnote.audio integration for speaker identification
- **Cross-Video Speaker Recognition** - AI-powered voice fingerprinting to match speakers across different media files
- **Speaker Profile System** - Global speaker profiles that persist across all transcriptions
- **Voice Similarity Analysis** - Advanced embedding-based speaker matching with confidence scores
- **LLM-Enhanced Speaker Identification** - Content-based speaker name suggestions using conversational context
- **Manual Verification Workflow** - Accept/reject AI suggestions to improve accuracy over time
- **Speaker Analytics** - Talk time distribution, cross-media appearances, and interaction patterns
- **Configurable Speaker Limits** - Support for 1-20 speakers by default, scalable to 50+ for large conferences
- **Auto-Profile Creation** - Automatic speaker profile creation when speakers are labeled
- **Retroactive Speaker Matching** - Cross-video matching with automatic label propagation

#### Media Support & Processing
- **Universal Format Support** - Audio (MP3, WAV, FLAC, M4A, OGG, AAC) and Video (MP4, MOV, AVI, MKV, WEBM)
- **YouTube Integration** - Direct URL processing with automatic video download
- **YouTube Playlist Support** - Extract and queue all videos from playlists for batch transcription
- **Large File Support** - Upload files up to 4GB (supports GoPro and high-quality video content)
- **Interactive Media Player** - Plyr-based player with click-to-seek transcript navigation
- **Audio Waveform Visualization** - Interactive waveform with precise timing and click-to-seek
- **Browser Microphone Recording** - Built-in microphone recording with real-time audio level monitoring (works over localhost or HTTPS)
- **Background Recording** - Record audio in the background while using other application features
- **Recording Controls** - Pause/resume recording with duration tracking and quality settings
- **Custom File Titles** - Edit display names for media files with real-time search index updates
- **Metadata Extraction** - Comprehensive file information using ExifTool
- **Subtitle Export** - Generate SRT/VTT files for accessibility
- **File Reprocessing** - Re-run AI analysis while preserving user comments and annotations
- **Auto-Recovery System** - Intelligent detection and recovery of stuck or failed file processing

#### Upload & File Management
- **Advanced Upload Manager** - Floating, draggable upload interface with real-time progress tracking
- **Concurrent Upload Processing** - Multiple file uploads with intelligent queue management
- **Drag-and-Drop Support** - Intuitive file upload interface with direct media file upload
- **Video File Size Detection** - Automatic detection of large video files with client-side audio extraction option to reduce upload size and processing time
- **Client-Side Audio Extraction** - Extract audio from video files in the browser before upload for faster processing and reduced bandwidth
- **Duplicate Detection** - Hash-based verification to prevent duplicate uploads
- **Automatic Recovery** - Retry logic for failed uploads with exponential backoff
- **Background Upload Processing** - Seamless integration with background task queue
- **YouTube URL Upload** - Direct video processing from YouTube URLs without manual download
- **YouTube Playlist Batch Upload** - Process entire YouTube playlists via URL with automatic queuing

#### AI-Powered Features
- **LLM Integration** - Support for 6+ providers (OpenAI, Anthropic Claude, vLLM, Ollama, OpenRouter, Custom)
- **AI-Powered Summaries** - Generate comprehensive summaries with customizable formats and structures
- **BLUF Format Summaries** - Bottom Line Up Front structured summaries with action items, key decisions, and follow-ups
- **Custom AI Prompts** - Create and manage unlimited AI prompts with ANY JSON structure
- **Flexible Schema Storage** - JSONB storage supporting multiple prompt types simultaneously
- **Intelligent Section Processing** - Automatic context-aware processing (single or multi-section) based on transcript length
- **Section-by-Section Analysis** - Handles transcripts of any length with intelligent chunking at speaker/topic boundaries
- **LLM Configuration Management** - User-specific LLM settings with encrypted API key storage
- **Provider Testing** - Test LLM connections and validate configurations before use
- **AI-Powered Topic Generation** - Automatic topic extraction from transcript content for intelligent tag suggestions
- **AI-Generated Collections** - Intelligent collection suggestions based on content analysis and topic clustering
- **Smart Tag Recommendations** - AI-powered tag suggestions based on transcript content, speakers, and themes
- **Real-Time Topic Extraction** - AI-powered topic extraction with granular progress notifications
- **Speaker Name Suggestions** - LLM-powered speaker identification based on conversation context
- **Local & Cloud Processing** - Support for both privacy-first local models and cloud AI providers

#### Search & Discovery
- **Hybrid Search** - Combine keyword and semantic search capabilities using OpenSearch 3.3.1
- **Full-Text Indexing** - Lightning-fast content search with Apache Lucene 10
- **9.5x Faster Vector Search** - Significantly improved semantic search performance
- **25% Faster Queries** - Enhanced full-text search with lower latency
- **75% Lower p90 Latency** - Improved aggregation performance
- **Advanced Filtering** - Filter by speaker, date, tags, duration, and more with searchable dropdowns
- **Smart Tagging** - Organize content with custom tags and categories
- **Collections System** - Group related media files into organized collections for better project management
- **Speaker Usage Counts** - Track which speakers appear most frequently across your media library
- **Inline Collection Editing** - Tag-style interface for managing file collections
- **Searchable Dropdowns** - Enhanced filter UI for better usability

#### Analytics & Insights
- **Advanced Content Analysis** - Comprehensive speaker analytics including talk time, interruptions, and turn-taking patterns
- **Speaker Performance Metrics** - Speaking pace (WPM), question frequency, and conversation flow analysis
- **Meeting Efficiency Analytics** - Silence ratio analysis and participation balance tracking
- **Real-Time Analytics Computation** - Server-side analytics with automatic refresh capabilities
- **Cross-Video Speaker Analytics** - Track speaker patterns and participation across multiple recordings

#### User Interface & Experience
- **Progressive Web App** - Installable app experience with offline capabilities
- **Responsive Design** - Optimized for desktop, tablet, and mobile devices
- **Interactive Waveform Player** - Click-to-seek audio visualization with precise timing
- **Floating Upload Manager** - Draggable upload interface with real-time progress
- **Smart Modal System** - Consistent modal design with improved accessibility
- **Timestamp-Based Comments** - Add user comments anchored to specific timestamps in videos and transcripts
- **Comment Navigation** - Click comments to jump to the corresponding moment in the media playback
- **Annotation System** - Rich annotation capabilities with timestamp markers throughout the transcript
- **Enhanced Data Formatting** - Server-side formatting service for consistent display of dates, durations, and file sizes
- **Error Categorization** - Intelligent error classification with user-friendly suggestions and retry guidance
- **Smart Status Management** - Comprehensive file and task status tracking with formatted display text
- **Auto-Refresh Systems** - Background data updates without manual page refreshing
- **Theme Support** - Seamless dark/light mode switching
- **Keyboard Shortcuts** - Efficient navigation and control via hotkeys
- **Full-Screen Transcript View** - Dedicated modal for reading and searching long transcripts
- **Smart Notification System** - Persistent notifications with unread count badges and progress updates
- **WebSocket Integration** - Real-time updates for transcription, summarization, and upload progress

#### Infrastructure & Performance
- **Docker Compose Architecture** - Base + override pattern for different environments
  - `docker-compose.yml` - Base configuration (all environments)
  - `docker-compose.override.yml` - Development overrides (auto-loaded)
  - `docker-compose.prod.yml` - Production overrides
  - `docker-compose.offline.yml` - Offline/airgapped overrides
  - `docker-compose.gpu-scale.yml` - Multi-GPU scaling configuration
- **Multi-GPU Worker Scaling** - Optional parallel processing on dedicated GPUs (4+ workers per GPU)
- **Specialized Worker Queues** - GPU (transcription), Download (YouTube), CPU (waveform), NLP (AI features), Utility (maintenance)
- **Parallel Waveform Processing** - CPU-based waveform generation runs simultaneously with GPU transcription
- **Non-Blocking Architecture** - LLM tasks don't delay next transcription (45-75s faster per 3-hour file)
- **Configurable Concurrency** - GPU(1-4), CPU(8), Download(3), NLP(4), Utility(2) workers for optimal resource utilization
- **Model Caching System** - Simple volume-based caching (~2.6GB total) with natural cache locations
- **PostgreSQL Database** - Reliable relational database with JSONB support for flexible schemas
- **MinIO Object Storage** - S3-compatible storage for media files
- **OpenSearch 3.3.1** - Full-text and vector search with Apache Lucene 10
- **Redis Message Broker** - High-performance task queue and caching
- **Celery Distributed Tasks** - Background AI processing with multiple specialized queues
- **Flower Monitoring** - Real-time task monitoring and management dashboard
- **NGINX Production Server** - Optimized reverse proxy for production deployments
- **Complete Offline Support** - Full airgapped/offline deployment capability

#### Security & Privacy
- **Non-Root Container User** - Backend containers run as non-root user (appuser, UID 1000)
- **Automatic Permission Management** - Startup scripts automatically fix model cache permissions
- **Principle of Least Privilege** - Reduced security risk from container escape vulnerabilities
- **Security Scanning Integration** - Trivy and Grype integration for vulnerability detection
- **Role-Based Access Control** - Admin/user permissions with file ownership validation
- **Encrypted API Key Storage** - User-specific LLM settings with secure key storage
- **Session Management** - Secure JWT-based authentication
- **Local Processing** - All data stays on your infrastructure (except optional cloud LLM calls)

#### Developer Experience
- **Comprehensive Utility Scripts** - `opentr.sh` and `opentranscribe.sh` for all operations
- **Hot Reload Support** - Development mode with automatic code reloading
- **Database Backup/Restore** - Easy data migration and disaster recovery
- **Service Health Checks** - Container orchestration with health monitoring
- **Docker Build Scripts** - Automated multi-platform builds with security scanning
- **Version Management** - Centralized VERSION file for consistent versioning
- **Code Quality Tooling** - ESLint, TypeScript strict mode, Black, Ruff
- **Comprehensive Documentation** - Docusaurus documentation site with screenshots and guides
- **TypeScript Integration** - Type-safe frontend development
- **API Documentation** - OpenAPI/Swagger automatic API docs

#### Documentation & Resources
- **Complete Documentation Site** - docs.opentranscribe.app with comprehensive guides
- **Visual Screenshots** - Step-by-step visual guides for all features
- **Installation Guides** - Multiple deployment options (Docker Hub, source, offline)
- **Configuration Reference** - Detailed environment variable documentation
- **Troubleshooting Guide** - Common issues and solutions
- **Developer Resources** - Contributing guidelines and architecture documentation
- **Blog** - Release announcements and development updates
- **One-Line Installer** - Quick setup script with hardware detection

### Changed
- **License** - Migrated from MIT to GNU Affero General Public License v3.0 (AGPL-3.0) to protect open source and ensure network copyleft
- **Version Numbering** - Starting at 0.1.0 with path to v1.0.0
- **Documentation Structure** - Migrated to dedicated Docusaurus site for better organization

### Technical Stack

#### Frontend
- Svelte 5.39.9 - Reactive UI framework
- TypeScript 5.9.3 - Type-safe development
- Vite 6.1.7 - Build tool and dev server
- Plyr 3.8.3 - Media player
- Axios 1.12.2 - HTTP client
- FFmpeg.wasm 0.12.15 - Browser-based media processing
- date-fns 4.1.0 - Date formatting
- imohash 1.0.3 - Fast file hashing

#### Backend
- Python 3.11+ - Programming language
- FastAPI - Modern async web framework
- SQLAlchemy 2.0 - ORM with type safety
- Alembic - Database migrations
- Celery - Distributed task queue
- Redis - Message broker and caching
- PostgreSQL - Relational database
- WhisperX - Speech recognition with alignment
- PyAnnote.audio - Speaker diarization
- OpenSearch 3.3.1 - Search engine (Apache Lucene 10)
- MinIO - S3-compatible object storage
- Sentence Transformers - Semantic embeddings
- NLTK - Natural language processing
- ExifTool - Metadata extraction
- yt-dlp - YouTube download

#### AI/ML Stack
- faster-whisper - Optimized Whisper inference
- PyAnnote segmentation-3.0 - Speaker segmentation
- PyAnnote speaker-diarization-3.1 - Speaker identification
- WAV2VEC2 - Word-level alignment
- Sentence Transformers all-MiniLM-L6-v2 - Semantic search (~80MB)
- Multiple LLM provider support (OpenAI, Claude, vLLM, Ollama, OpenRouter)

#### Infrastructure
- Docker & Docker Compose - Containerization
- NGINX - Reverse proxy
- Flower - Celery monitoring
- GitHub Actions - CI/CD

### Performance Benchmarks
- **Transcription Speed** - 70x realtime with large-v2 model on GPU
- **Vector Search** - 9.5x faster than previous generation
- **Query Performance** - 25% faster with 75% lower p90 latency
- **Multi-GPU Scaling** - 4 parallel workers can process 4 videos simultaneously
- **Model Cache Size** - ~2.6GB total for all AI models

### Deployment Options
- **Quick Install** - One-line installer with hardware detection
- **Docker Hub** - Pre-built images for instant deployment
- **Source Build** - Full source code with development environment
- **Offline/Airgapped** - Complete offline deployment support
- **Multi-Platform** - AMD64 and ARM64 support

### Breaking Changes
- None (first release)

### Migration Notes
- This is the first public release - no migration required
- For future releases, we will strive for backwards compatibility
- Breaking changes will be clearly announced in release notes

### Known Issues
- None critical at release time
- See GitHub Issues for community-reported items

### Contributors
- David Macey (@davidamacey) - Project Lead
- OpenTranscribe Community - Testing and feedback

### Links
- **Documentation**: https://docs.opentranscribe.app
- **GitHub Repository**: https://github.com/davidamacey/OpenTranscribe
- **Docker Hub Backend**: https://hub.docker.com/r/davidamacey/opentranscribe-backend
- **Docker Hub Frontend**: https://hub.docker.com/r/davidamacey/opentranscribe-frontend
- **Issues**: https://github.com/davidamacey/OpenTranscribe/issues
- **License**: https://github.com/davidamacey/OpenTranscribe/blob/master/LICENSE

---

## Future Roadmap

Looking ahead to v1.0.0, we plan to add:
- Real-time transcription for live streaming
- Enhanced speaker analytics and visualization
- Better speaker diarization models
- Google-style text search
- LLM powered RAG Chat with transcript text
- Other refinements along the way!

We welcome community feedback and contributions as we work towards the v1.0.0 release!

[0.1.0]: https://github.com/davidamacey/OpenTranscribe/releases/tag/v0.1.0
