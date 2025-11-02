---
sidebar_position: 1
---

# Architecture

OpenTranscribe is built with a modern, scalable architecture.

## System Components

### Frontend (Svelte)
- Progressive Web App
- TypeScript
- Responsive design
- Real-time WebSocket updates

### Backend (FastAPI)
- Async Python
- RESTful API
- OpenAPI documentation
- WebSocket support

### Workers (Celery)
- **GPU Queue**: Transcription, diarization
- **Download Queue**: YouTube downloads
- **CPU Queue**: Waveform generation
- **NLP Queue**: LLM features
- **Utility Queue**: Maintenance

### Data Layer
- **PostgreSQL**: Relational data
- **MinIO**: Object storage (S3-compatible)
- **OpenSearch**: Full-text and vector search
- **Redis**: Task queue and caching

## Data Flow

1. User uploads file
2. File stored in MinIO
3. Celery task queued
4. GPU worker processes:
   - Transcription (WhisperX)
   - Diarization (PyAnnote)
5. Results stored in PostgreSQL
6. Indexed in OpenSearch
7. WebSocket notification to UI

## Deployment Models

- Development: docker-compose with hot reload
- Production: docker-compose with optimizations
- Offline: Airgapped deployment
- Cloud: AWS/GCP/Azure with GPU instances

## Next Steps

- [Contributing](./contributing.md)
- [Docker Compose Installation](../installation/docker-compose.md)
