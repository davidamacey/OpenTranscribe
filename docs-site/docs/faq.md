---
sidebar_position: 100
title: Frequently Asked Questions
---

# Frequently Asked Questions

Common questions and answers about OpenTranscribe.

## General

### What is OpenTranscribe?

OpenTranscribe is an open-source, self-hosted AI-powered transcription and media analysis platform. It uses state-of-the-art AI models (WhisperX, PyAnnote, LLMs) to transcribe audio/video files, identify speakers, generate summaries, and enable powerful search across your media library.

### Is OpenTranscribe free?

Yes! OpenTranscribe is completely free and open-source under the GNU Affero General Public License v3.0 (AGPL-3.0). There are no subscription fees, usage limits, or hidden costs. You can use it for personal, commercial, or any other purpose, as long as you comply with the AGPL-3.0 license terms.

### What makes OpenTranscribe different from other transcription services?

- **Self-hosted** - Your data never leaves your infrastructure
- **Open source** - Full transparency and customizability
- **Privacy-first** - No cloud services required (except optional LLM providers)
- **Advanced features** - Speaker diarization, cross-video speaker matching, AI summarization
- **No usage limits** - Transcribe unlimited content
- **GPU acceleration** - Fast processing with your own hardware
- **Offline capable** - Works in airgapped environments

### Can I use OpenTranscribe commercially?

Yes! The AGPL-3.0 license permits commercial use. However, if you modify OpenTranscribe and offer it as a network service (SaaS), you must make your modified source code available to your users under the same AGPL-3.0 license.

## Installation & Setup

### What are the system requirements?

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

See [Hardware Requirements](./installation/hardware-requirements.md) for detailed recommendations.

### Do I need a GPU?

No, but **highly recommended** for practical use. CPU-only processing is very slow:
- **GPU (RTX 3080)**: 1-hour video → ~5 minutes
- **CPU (8-core)**: 1-hour video → ~60 minutes

### Can I use Apple Silicon (M1/M2/M3)?

Yes! OpenTranscribe supports Apple Silicon Macs with MPS (Metal Performance Shaders) acceleration. Performance is between CPU and NVIDIA GPU:
- **M2 Max**: 1-hour video → ~15-20 minutes

### What GPUs are supported?

Any NVIDIA GPU with CUDA support:
- **Minimum**: GTX 1060 (6GB VRAM)
- **Recommended**: RTX 3070 or better (8GB+ VRAM)
- **Best**: RTX 4090, A6000, A100

AMD GPUs are not currently supported (ROCm support planned for future).

### How do I get a HuggingFace token?

1. Create free account at [huggingface.co](https://huggingface.co)
2. Go to [Settings → Access Tokens](https://huggingface.co/settings/tokens)
3. Click "New token", select "Read" access
4. Accept agreements for:
   - [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
   - [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
5. Copy token to your `.env` file

See [HuggingFace Setup](./installation/huggingface-setup.md) for detailed instructions.

### Why do I need a HuggingFace token?

The PyAnnote speaker diarization models are "gated" - they require accepting a user agreement before downloading. The token authenticates that you've accepted the terms.

**Without a token:** Transcription works, but speakers won't be detected (everything will be labeled as SPEAKER_00).

### Can I run OpenTranscribe offline?

Yes! After initial setup and model downloads (~2.5GB), OpenTranscribe works completely offline. Use the offline Docker Compose configuration:

```bash
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d
```

See [Offline Installation](./installation/offline-installation.md) for details.

## Features & Usage

### What file formats are supported?

**Audio:** MP3, WAV, FLAC, M4A, OGG, AAC
**Video:** MP4, MOV, AVI, MKV, WEBM, FLV

Maximum file size: **4GB**

### What languages are supported for transcription?

**100+ languages** are supported for transcription via WhisperX/Whisper. See the [Whisper documentation](https://github.com/openai/whisper#available-models-and-languages) for the full list.

**v0.2.0 Language Features:**
- **Source Language Selection**: Auto-detect or manually specify the audio language
- **Translation Toggle**: Choose to keep original language or translate to English
- **Word-Level Timestamps**: ~42 languages support word-level alignment (others fall back to segment-level)

Configure language settings in: **Settings → Transcription → Language Settings**

**Note:** English transcription quality is best. Other languages work but accuracy varies.

### What languages is the UI available in?

**7 languages** as of v0.2.0:
- English (default)
- Spanish (Espa\u00f1ol)
- French (Fran\u00e7ais)
- German (Deutsch)
- Portuguese (Portugu\u00eas)
- Chinese (\u4e2d\u6587)
- Japanese (\u65e5\u672c\u8a9e)
- Russian (\u0420\u0443\u0441\u0441\u043a\u0438\u0439)

Change the UI language in: **Settings → Language**

Want to contribute a translation? Submit a PR with a new locale file!

### How accurate is the transcription?

Accuracy depends on:
- **Audio quality** - Clear audio with minimal background noise
- **Model size** - `large-v2` is most accurate
- **Language** - English has best accuracy
- **Speaker accent** - Native accents perform better

**Typical accuracy:** 85-95% word accuracy with good audio quality.

### How does speaker diarization work?

OpenTranscribe uses PyAnnote.audio to:
1. **Detect voice activity** - Find when people are speaking
2. **Extract voice features** - Create voice fingerprints
3. **Cluster speakers** - Group similar voices
4. **Assign labels** - Tag each segment with SPEAKER_00, SPEAKER_01, etc.

You can then manually edit speaker names, and OpenTranscribe will remember those voices across future transcriptions.

### Can OpenTranscribe identify speakers by name automatically?

Not automatically, but it can:
1. **Suggest speaker identities** using LLM analysis of conversation content
2. **Match voices across videos** using voice fingerprints
3. **Remember speakers** once you've identified them in one video

See [Speaker Management](./user-guide/speaker-management.md) for details.

### How many speakers can it detect?

Default: **1-20 speakers**

You can increase this in `.env`:
```bash
MIN_SPEAKERS=1
MAX_SPEAKERS=50  # or higher for large conferences
```

There's no hard upper limit, but accuracy decreases with very large groups (30+ speakers).

### What LLM providers are supported?

OpenTranscribe supports multiple LLM providers for AI summarization:

**Cloud Providers:**
- **OpenAI** (GPT-4o, GPT-4o-mini, GPT-4-turbo)
- **Anthropic Claude** (Claude 3.5 Sonnet, Claude 3 Opus)
- **OpenRouter** (access to 100+ models)

**Self-Hosted:**
- **vLLM** (fast self-hosted inference)
- **Ollama** (local models)
- **Custom OpenAI-compatible APIs**

See [LLM Integration](./features/llm-integration.md) for setup instructions.

### Do I need an LLM for transcription?

No! LLMs are **optional** and only used for:
- AI-powered summarization
- Topic extraction
- Enhanced speaker name suggestions

Transcription and speaker diarization work without any LLM.

### Can I generate AI summaries in languages other than English?

Yes! As of v0.2.0, AI summaries can be generated in **12 languages**:
- English, Spanish, French, German
- Portuguese, Chinese, Japanese, Korean
- Italian, Russian, Arabic, Hindi

Configure in: **Settings → Transcription → LLM Output Language**

The LLM will generate the summary in your chosen language regardless of the original audio language.

### Can I use OpenTranscribe without any cloud services?

Yes! You can run completely offline and local:
- Transcription: Local WhisperX models
- Speakers: Local PyAnnote models
- LLM (optional): Local vLLM or Ollama

No data leaves your infrastructure.

### How long does processing take?

Depends on hardware and content length:

| Content Length | GPU (RTX 3080) | CPU (8-core) |
|----------------|----------------|--------------|
| 5 minutes      | ~30 seconds    | ~5 minutes   |
| 30 minutes     | ~3 minutes     | ~30 minutes  |
| 1 hour         | ~5 minutes     | ~60 minutes  |
| 3 hours        | ~15 minutes    | ~3 hours     |

**Processing speed:** ~70x realtime with GPU and `large-v2` model.

### Can I process multiple files at once?

Yes! OpenTranscribe uses Celery workers to process multiple files in parallel:
- **Default:** 1-2 files at once (depending on GPU memory)
- **Multi-GPU:** 4+ files at once with [Multi-GPU Scaling](./configuration/multi-gpu-scaling.md)

### How much disk space do I need?

**For OpenTranscribe:**
- Docker images: ~5GB
- AI models: ~2.5GB
- Database: ~100MB (grows with transcriptions)

**For media files:**
- Plan **~10% of original file size** for processed data
- Example: 100 hours of audio (10GB) → ~11GB total storage needed

### Can I download videos from YouTube and other platforms?

Yes! OpenTranscribe supports **1800+ platforms** via yt-dlp integration:
- **Best supported**: YouTube (including playlists), Dailymotion, Twitter/X
- **Limited support**: Vimeo, Instagram, Facebook, TikTok (may require authentication)
- Automatically downloads and transcribes
- User-friendly error messages for authentication-required videos

### How do I view system statistics?

System statistics (CPU, memory, disk, GPU usage) are visible to all authenticated users in the **navbar** - look for the system stats icon. This shows real-time resource usage of your OpenTranscribe server.

### How does pagination work for large transcripts?

For transcripts with thousands of segments (3+ hour recordings), OpenTranscribe automatically paginates the display to prevent browser slowdown. Segments load progressively as you scroll through the transcript.

## Performance & Optimization

### How can I speed up processing?

1. **Use a GPU** - Fastest option (required for practical use)
2. **Use larger batch size** - If you have GPU memory (edit `BATCH_SIZE` in `.env`)
3. **Use smaller model** - `medium` or `base` (faster but less accurate)
4. **Multi-GPU scaling** - Process 4+ files in parallel
5. **SSD storage** - Faster disk I/O

### My GPU is running out of memory. What can I do?

1. **Reduce batch size**: `BATCH_SIZE=8` (or lower)
2. **Use smaller model**: `WHISPER_MODEL=medium` or `base`
3. **Use quantization**: `COMPUTE_TYPE=int8`
4. **Close other GPU applications**
5. **Upgrade GPU** (if feasible)

### Can I use multiple GPUs?

Yes! OpenTranscribe supports multi-GPU scaling for high-throughput processing:

```bash
# Configure in .env
GPU_SCALE_ENABLED=true
GPU_SCALE_DEVICE_ID=2  # Which GPU to use
GPU_SCALE_WORKERS=4    # Number of parallel workers

# Start with GPU scaling
./opentr.sh start dev --gpu-scale
```

See [Multi-GPU Scaling](./configuration/multi-gpu-scaling.md) for details.

## Troubleshooting

### OpenTranscribe won't start

```bash
# Check Docker is running
docker ps

# Check logs
docker compose logs

# Common issues:
# - Port conflicts (5173, 8080, etc. already in use)
# - Insufficient memory
# - Docker Compose not installed
```

See [Troubleshooting Guide](./installation/troubleshooting.md).

### "Permission denied" error for model cache

```bash
# Fix permissions
./scripts/fix-model-permissions.sh

# Or manually
sudo chown -R 1000:1000 ./models
```

This happens because Docker creates directories as root, but containers run as non-root user (UID 1000) for security.

### Transcription fails with "CUDA out of memory"

Reduce GPU memory usage:
```bash
# Edit .env
BATCH_SIZE=8        # Reduce from 16
COMPUTE_TYPE=int8   # Use 8-bit quantization

# Or use smaller model
WHISPER_MODEL=medium
```

### Speaker diarization not working

1. **Check HuggingFace token** is set in `.env`
2. **Accept model agreements** (both pyannote models)
3. **Check logs** for download errors: `docker compose logs celery-worker`
4. **Re-download models** if corrupted

### Poor transcription quality

- **Use better audio** - Clear, well-recorded audio
- **Use larger model** - `large-v2` is most accurate
- **Reduce background noise** - Use noise cancellation
- **Check language setting** - Ensure correct language selected

### YouTube downloads failing

- **Check yt-dlp version** - May need updating
- **Check video availability** - Some videos are region-locked
- **Check age restrictions** - Age-restricted videos may not work
- **Try direct file upload** - Download manually first

## Security & Privacy

### Is my data secure?

Yes! All processing happens locally:
- Media files stored in MinIO (local S3-compatible storage)
- Transcripts stored in PostgreSQL (local database)
- AI models run locally (no cloud services)
- Optional LLM calls can use self-hosted providers

### Are transcripts encrypted?

Database data is not encrypted by default, but you can:
- Use encrypted Docker volumes
- Enable PostgreSQL encryption at rest
- Use full disk encryption on your server

### Who can access my transcriptions?

Only users you create. OpenTranscribe has role-based access control:
- **Admin users** - Full access to all data
- **Regular users** - Access only to their own data

### Can I use OpenTranscribe for sensitive content?

Yes! OpenTranscribe is designed for privacy-sensitive use cases:
- Legal depositions
- Medical consultations
- Business strategy meetings
- Personal recordings

All processing is local, nothing is sent to cloud services (except optional LLM calls, which you control).

## Development & Contribution

### How can I contribute?

We welcome contributions! See [Contributing Guide](./developer-guide/contributing.md) for:
- Code contributions
- Documentation improvements
- Bug reports
- Feature requests
- Translations

### Can I customize OpenTranscribe?

Yes! OpenTranscribe is open source (AGPL-3.0 License):
- Modify the code
- Add custom features
- Integrate with other services
- White-label for your organization

See [Developer Guide](./developer-guide/architecture.md) to get started.

**Important:** If you modify OpenTranscribe and offer it as a network service (SaaS), you must make your modified source code available to your users under the AGPL-3.0 license.

### How is OpenTranscribe built?

**Frontend:** Svelte + TypeScript + Vite
**Backend:** Python + FastAPI + SQLAlchemy
**AI:** WhisperX + PyAnnote + LangChain
**Infrastructure:** Docker + PostgreSQL + Redis + MinIO + OpenSearch

See [Architecture](./developer-guide/architecture.md) for details.

### What AI models does it use?

- **WhisperX** - Speech recognition (based on OpenAI Whisper)
- **PyAnnote.audio** - Speaker diarization
- **Wav2Vec2** - Word-level alignment
- **Sentence Transformers** - Semantic search embeddings
- **LLMs** (optional) - Summarization and analysis

## Licensing & Legal

### What is the license?

OpenTranscribe is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)** - a strong copyleft open-source license. You can:
- Use commercially
- Modify the code
- Distribute
- Private use

**Key requirement:** If you modify OpenTranscribe and offer it as a network service (SaaS), you must provide your users access to the modified source code under the same AGPL-3.0 license. This ensures the open source community benefits from improvements.

### Can I sell OpenTranscribe?

Yes! The AGPL-3.0 license permits commercial use, including:
- Offering it as a paid service
- Selling access to your installation
- Using it for commercial transcription work

**Important:** If you modify the code and run it as a network service, you must make your modifications available under AGPL-3.0.

### Do I need to credit OpenTranscribe?

Credit is appreciated but not required. The AGPL-3.0 license requires that you:
1. Include the original license notice in copies of the software
2. Make source code available if you offer it as a network service
3. Preserve copyright notices

### What if I don't want to share my modifications?

If you modify OpenTranscribe for internal use only (not as a network service), you don't need to share your changes. The AGPL-3.0 only requires source disclosure when you offer the software as a service to others over a network.

### What about the AI models' licenses?

- **WhisperX**: Apache 2.0 License
- **PyAnnote**: MIT License
- **Wav2Vec2**: Apache 2.0 License

All are permissive licenses compatible with commercial use.

## Still Have Questions?

- **GitHub Discussions**: [github.com/davidamacey/OpenTranscribe/discussions](https://github.com/davidamacey/OpenTranscribe/discussions)
- **GitHub Issues**: [github.com/davidamacey/OpenTranscribe/issues](https://github.com/davidamacey/OpenTranscribe/issues)
- **Documentation**: Browse the rest of the docs!
