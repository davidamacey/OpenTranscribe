---
sidebar_position: 1
title: Introduction
---

# Welcome to OpenTranscribe

OpenTranscribe is a powerful, self-hosted AI-powered transcription and media analysis platform that turns your audio and video files into searchable, analyzable text with advanced features like speaker identification, AI summarization, and cross-media intelligence.

## What is OpenTranscribe?

OpenTranscribe combines state-of-the-art AI models with a modern web interface to provide:

- **High-accuracy transcription** using WhisperX with word-level timestamps
- **Automatic speaker identification** with voice fingerprinting across videos
- **AI-powered summarization** with customizable prompts and LLM integration
- **Full-text and semantic search** powered by OpenSearch
- **Privacy-first processing** - everything runs locally on your infrastructure

## Key Features

### 🎧 Advanced Transcription
- WhisperX integration with faster-whisper backend
- Word-level timestamps with WAV2VEC2 alignment
- Multi-language support with automatic English translation
- 70x realtime speed on GPU (large-v2 model)
- Support for audio (MP3, WAV, FLAC, M4A) and video (MP4, MOV, AVI, MKV)

### 👥 Smart Speaker Management
- Automatic speaker diarization using PyAnnote.audio
- Cross-video speaker recognition with voice fingerprinting
- LLM-enhanced speaker identification
- Global speaker profiles that persist across transcriptions
- Confidence scoring and manual verification workflow

### 🤖 AI-Powered Features
- LLM summarization with BLUF (Bottom Line Up Front) format
- Support for multiple LLM providers (OpenAI, Claude, vLLM, Ollama, OpenRouter)
- Custom AI prompts for different content types
- Intelligent section-by-section processing for unlimited transcript lengths
- Speaker analytics and interaction patterns

### 🔍 Search & Discovery
- Hybrid search combining keyword and semantic search
- 9.5x faster vector search with OpenSearch 3.3.1
- Advanced filtering by speaker, date, tags, duration
- Collections for organizing related media
- Interactive waveform visualization with click-to-seek

### 📊 Analytics & Insights
- Speaker analytics (talk time, interruptions, pace)
- Meeting efficiency metrics
- Action item extraction
- Cross-video speaker tracking

## Why OpenTranscribe?

### Open Source & Self-Hosted
- **Full control** over your data - nothing leaves your infrastructure
- **MIT License** - use it however you want
- **No subscription fees** - one-time setup, unlimited use
- **Privacy-first** - ideal for sensitive content (legal, medical, business)

### Production-Ready
- **Docker-based deployment** - runs anywhere
- **GPU acceleration** - NVIDIA GPUs supported
- **Multi-worker architecture** - process multiple files in parallel
- **Offline capable** - works in airgapped environments

### Modern Stack
- **React + TypeScript frontend** - responsive, PWA-enabled
- **FastAPI backend** - high-performance Python
- **PostgreSQL + OpenSearch** - reliable, scalable storage
- **Celery workers** - distributed background processing

## Use Cases

OpenTranscribe is perfect for:

- 📞 **Meeting transcriptions** - Record and analyze team meetings with speaker identification
- 🎙️ **Podcast production** - Generate transcripts and show notes automatically
- 🎓 **Academic research** - Transcribe interviews and lectures for analysis
- ⚖️ **Legal & compliance** - Accurate transcripts with speaker identification for depositions
- 📞 **Customer service** - Analyze support calls for quality and training
- 🎬 **Content creation** - Generate subtitles and content from videos

## Quick Look

```bash
# Install with one command
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash

# Start the application
cd opentranscribe
./opentranscribe.sh start

# Access at http://localhost:5173
```

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Frontend   │────▶│   Backend    │────▶│   Workers   │
│   (Svelte)  │     │  (FastAPI)   │     │  (Celery)   │
└─────────────┘     └──────────────┘     └─────────────┘
                            │                    │
                            ▼                    ▼
                    ┌──────────────┐     ┌─────────────┐
                    │  PostgreSQL  │     │  WhisperX   │
                    │    MinIO     │     │  PyAnnote   │
                    │ OpenSearch   │     │     LLM     │
                    └──────────────┘     └─────────────┘
```

## System Requirements

**Minimum:**
- 8GB RAM
- 4 CPU cores
- 50GB disk space
- Docker & Docker Compose

**Recommended:**
- 16GB+ RAM
- 8+ CPU cores
- 100GB+ SSD
- NVIDIA GPU with 8GB+ VRAM (RTX 3070 or better)

## Next Steps

Ready to get started? Follow our [Quick Start Guide](./quick-start.md) to install OpenTranscribe in minutes.

Or explore:
- [Installation Guide](../installation/docker-compose.md) - Detailed installation instructions
- [Hardware Requirements](../installation/hardware-requirements.md) - Hardware recommendations
- [Configuration](../configuration/environment-variables.md) - Customize your setup
