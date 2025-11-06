# OpenTranscribe v0.1.0 - First Official Release

**Release Date:** November 5, 2025
**License:** GNU Affero General Public License v3.0 (AGPL-3.0)

## Overview

We're thrilled to announce the first official release of OpenTranscribe! After 6 months of intensive development starting in May 2025, what began as a weekend experiment has evolved into a production-ready, fully-featured AI transcription platform.

OpenTranscribe is a powerful, self-hosted AI-powered transcription and media analysis platform that combines state-of-the-art AI models with a modern web interface to provide high-accuracy transcription, speaker identification, AI summarization, and advanced search capabilities.

## Why AGPL-3.0?

We've chosen the GNU Affero General Public License v3.0 to:
- **Protect open source** - Ensure the code remains open and accessible to everyone
- **Prevent proprietary forks** - Require that modifications, especially network services, remain open
- **Ensure transparency** - Network users have the right to access the source code
- **Build community** - Foster collaboration and shared improvements

## Key Highlights

### 🎧 Professional-Grade Transcription
- **70x realtime speed** on GPU with large-v2 model
- **Word-level timestamps** using WAV2VEC2 alignment
- **50+ languages** supported with automatic translation
- **Universal format support** - Audio and video files up to 4GB

### 👥 Advanced Speaker Intelligence
- **Automatic speaker diarization** using PyAnnote.audio
- **Cross-video speaker recognition** with voice fingerprinting
- **AI-powered speaker suggestions** using LLM context analysis
- **Global speaker profiles** that persist across all recordings
- **Speaker analytics** with talk time, pace, and interaction patterns

### 🤖 AI-Powered Insights
- **LLM integration** - Support for OpenAI, Claude, vLLM, Ollama, OpenRouter, and custom providers
- **BLUF format summaries** - Bottom Line Up Front structured analysis
- **Custom AI prompts** - Unlimited prompts with flexible JSON schemas
- **Intelligent sectioning** - Handles transcripts of any length automatically
- **Local or cloud processing** - Privacy-first local models or powerful cloud AI

### 🔍 Powerful Search & Discovery
- **Hybrid search** - Keyword + semantic search with OpenSearch 3.3.1
- **9.5x faster vector search** - Significantly improved performance
- **25% faster queries** with 75% lower p90 latency
- **Advanced filtering** - Search by speaker, tags, collections, date, duration
- **Interactive navigation** - Click-to-seek on transcripts and waveforms

### ⚡ Enterprise Performance
- **Multi-GPU scaling** - Optional parallel processing (4+ workers per GPU)
- **Specialized work queues** - GPU, CPU, Download, NLP, and Utility queues
- **Non-blocking architecture** - Parallel processing saves 45-75s per 3-hour file
- **Model caching** - Efficient ~2.6GB cache with automatic persistence
- **Complete offline support** - Full airgapped deployment capability

## Installation

### Quick Install (Recommended)
```bash
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
cd opentranscribe
./opentranscribe.sh start
```

Access at: **http://localhost:5173**

### Docker Hub Images
Pre-built multi-platform images (AMD64, ARM64):
- `davidamacey/opentranscribe-backend:v0.1.0`
- `davidamacey/opentranscribe-frontend:v0.1.0`

### From Source
```bash
git clone https://github.com/davidamacey/OpenTranscribe.git
cd OpenTranscribe
git checkout v0.1.0
cp .env.example .env
# Edit .env with your settings
./opentr.sh start dev
```

## What's Included

### Core Features
✅ **Transcription** - WhisperX with faster-whisper backend
✅ **Speaker Diarization** - PyAnnote.audio integration with auto-labeling and profile generation
✅ **Media File Upload** - Direct upload of audio/video files up to 4GB with drag-and-drop
✅ **Video File Size Detection** - Client-side audio extraction option for large video files
✅ **YouTube Support** - Direct URL and playlist processing for batch transcription
✅ **Browser Microphone Recording** - Built-in recording (localhost or HTTPS) with background operation
✅ **AI-Powered Summaries** - Multi-provider LLM integration with customizable formats
✅ **AI Topic Generation** - Automatic tag and collection suggestions from transcript content
✅ **Timestamp Comments** - User annotations anchored to specific video moments
✅ **Search Engine** - OpenSearch 3.3.1 with hybrid keyword and vector search
✅ **Collections** - Organize media into themed groups with AI suggestions
✅ **Analytics** - Speaker metrics and interaction analysis
✅ **Waveform Visualization** - Interactive audio timeline
✅ **PWA Support** - Installable progressive web app
✅ **Dark/Light Mode** - Full theme support

### Infrastructure
✅ **Docker Compose** - Multi-environment orchestration
✅ **PostgreSQL** - Relational database with JSONB
✅ **MinIO** - S3-compatible object storage
✅ **Redis** - Message broker and caching
✅ **Celery** - Distributed task processing
✅ **NGINX** - Production web server
✅ **Flower** - Task monitoring dashboard

### Security
✅ **Non-root containers** - Principle of least privilege
✅ **RBAC** - Role-based access control
✅ **Encrypted secrets** - Secure API key storage
✅ **Security scanning** - Trivy and Grype integration
✅ **Session management** - JWT-based authentication

## System Requirements

### Minimum
- **CPU:** 4 cores
- **RAM:** 8GB
- **Storage:** 50GB (including ~3GB for AI models)
- **GPU:** Optional (CPU-only mode available)

### Recommended
- **CPU:** 8+ cores
- **RAM:** 16GB+
- **Storage:** 100GB+ SSD
- **GPU:** NVIDIA GPU with 8GB+ VRAM (RTX 3070 or better)

### Supported Platforms
- **OS:** Linux, macOS (including Apple Silicon), Windows (via WSL2)
- **Architectures:** AMD64, ARM64
- **GPUs:** NVIDIA CUDA, Apple MPS (Metal)

## Performance Benchmarks

| Metric | Performance |
|--------|-------------|
| Transcription Speed (GPU) | 70x realtime |
| Vector Search Improvement | 9.5x faster |
| Query Performance | 25% faster, 75% lower p90 latency |
| Multi-GPU Throughput | 4 videos simultaneously (4 workers) |
| Model Cache Size | ~2.6GB total |

## Documentation

📚 **Complete Documentation:** https://docs.opentranscribe.app

Key resources:
- [Quick Start Guide](https://docs.opentranscribe.app/docs/getting-started/quick-start)
- [Installation Guide](https://docs.opentranscribe.app/docs/getting-started/installation)
- [User Guide](https://docs.opentranscribe.app/docs/user-guide)
- [Configuration Reference](https://docs.opentranscribe.app/docs/configuration)
- [Screenshots & Visual Guide](https://docs.opentranscribe.app/docs/screenshots)
- [FAQ](https://docs.opentranscribe.app/docs/faq)
- [Troubleshooting](https://docs.opentranscribe.app/docs/troubleshooting)

## Roadmap to v1.0.0

We're committed to delivering a stable, production-ready v1.0.0 release. While we'll strive for backwards compatibility, we cannot guarantee it until v1.0.0. Breaking changes will be clearly announced.

**Planned features for future releases:**
- Real-time transcription for live streaming
- Enhanced speaker analytics and visualization
- Better speaker diarization models
- Google-style text search
- LLM powered RAG Chat with transcript text
- Other refinements along the way!

## Known Issues

No critical issues at release time. See [GitHub Issues](https://github.com/davidamacey/OpenTranscribe/issues) for community-reported items.

## Contributing

We welcome contributions from the community! See our [Contributing Guide](https://github.com/davidamacey/OpenTranscribe/blob/master/docs/CONTRIBUTING.md) for details.

Ways to contribute:
- 🐛 Report bugs and issues
- 💡 Suggest new features
- 🔧 Submit pull requests
- 📚 Improve documentation
- 🌍 Translate the interface
- ⭐ Star the repository

## Support & Community

- **Issues:** [GitHub Issues](https://github.com/davidamacey/OpenTranscribe/issues)
- **Discussions:** [GitHub Discussions](https://github.com/davidamacey/OpenTranscribe/discussions)
- **Email:** [Contact via GitHub](https://github.com/davidamacey)

## Acknowledgments

OpenTranscribe builds upon amazing open-source projects:
- **OpenAI Whisper** - Foundation speech recognition model
- **WhisperX** - Enhanced alignment and diarization
- **PyAnnote.audio** - Speaker diarization toolkit
- **FastAPI** - Modern Python web framework
- **Svelte** - Reactive frontend framework
- **PostgreSQL** - Reliable database system
- **OpenSearch** - Search and analytics engine
- **Docker** - Containerization platform

Special thanks to the AI community and all contributors who helped make this release possible!

## License

OpenTranscribe is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

See [LICENSE](https://github.com/davidamacey/OpenTranscribe/blob/master/LICENSE) for full details.

---

**Built with ❤️ by the OpenTranscribe community**

*OpenTranscribe demonstrates the power of AI-assisted development while maintaining full local control over your data and processing.*

**Download:** [v0.1.0 Release](https://github.com/davidamacey/OpenTranscribe/releases/tag/v0.1.0)
**Docker:** [Backend](https://hub.docker.com/r/davidamacey/opentranscribe-backend) | [Frontend](https://hub.docker.com/r/davidamacey/opentranscribe-frontend)
**Docs:** [docs.opentranscribe.app](https://docs.opentranscribe.app)
