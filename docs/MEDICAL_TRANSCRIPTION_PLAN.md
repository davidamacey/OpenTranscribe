# OpenTranscribe Fork — Medical Education Transcription Platform

## Context

A developer at an academic medical center is forking OpenTranscribe to build a speaker diarization + transcription platform for medical education. They have a working Flask/SQLite prototype (~2,000 line monolith) using PyAnnote cloud + OpenAI Whisper-1. The goal is to migrate to OpenTranscribe's structured architecture while adding medical-specific features, Deepgram Nova-3 Medical as primary ASR, and compliance capabilities.

**User decisions from Q&A:**
- ASR: **Multi-provider with easy switching** (Deepgram primary, future engines pluggable)
- Diarization: **Deepgram built-in only** (simplify, no separate PyAnnote)
- Infrastructure: **Minimal viable** (drop OpenSearch, simplify Celery — no local GPU available)
- Review workflow: **Hybrid** (auto-flag low-confidence segments + full-transcript review status)
- Compliance: **FERPA only** (no HIPAA concerns — environment is separate from healthcare)
- Search: **Not a priority** — defer to a later version

**Clarifications from user:**
- No local GPU available — Deepgram cloud API is the primary/only practical engine for now
- WhisperX support is aspirational/future — not needed for MVP since it requires GPU
- Correction pattern learning does NOT exist in the prototype — must be built from scratch
- Audit logging needed for FERPA compliance, but no HIPAA requirements
- The recordings are in a medical education context separate from the healthcare side

---

## Phase 1: Codebase Audit Summary

### Architecture Overview

| Component | Technology | Key Files |
|-----------|-----------|-----------|
| Frontend | Svelte/TypeScript SPA, Vite, Plyr, i18n (7 langs) | `frontend/src/` |
| Backend | FastAPI, async, OpenAPI docs | `backend/app/` |
| Database | PostgreSQL + SQLAlchemy 2.0 ORM | `database/init_db.sql`, `backend/app/models/` |
| Storage | MinIO S3-compatible | `backend/app/services/minio_service.py` |
| Search | OpenSearch 3.3.1 (full-text + vector) | `backend/app/services/opensearch_service.py` |
| Queue | Celery + Redis | `backend/app/tasks/` |
| Auth | Hybrid multi-method (local, LDAP, OIDC, PKI, MFA) | `backend/app/auth/` |
| AI/ASR | WhisperX (local GPU) + PyAnnote | `backend/app/tasks/transcription/` |
| LLM | Multi-provider (OpenAI, Anthropic, vLLM, Ollama, etc.) | `backend/app/services/llm_service.py` |

### Feature Inventory

| Feature | Status | Completeness | Files |
|---------|--------|-------------|-------|
| File upload (direct + URL) | Complete | Polished | `endpoints/files/upload.py`, `url_processing.py` |
| WhisperX transcription | Complete | Production | `tasks/transcription/core.py`, `whisperx_service.py` |
| PyAnnote diarization | Complete | Production | `tasks/transcription/whisperx_service.py:268-328` |
| Speaker management | Complete | Polished | `models/media.py:Speaker`, `SpeakerProfile`, `SpeakerMatch` |
| Speaker verification UI | Complete | Polished | `SpeakerVerification.svelte`, `SpeakerMerge.svelte` |
| Voice embedding matching | Complete | Advanced | `services/speaker_embedding_service.py`, `speaker_matching_service.py` |
| LLM speaker identification | Complete | Good | `tasks/speaker_tasks.py`, `services/smart_speaker_suggestion_service.py` |
| LLM summarization (BLUF) | Complete | Advanced | `services/llm_service.py` (1200+ lines) |
| Transcript text editing | Complete | Basic | `EditTranscriptButton.svelte`, `TranscriptDisplay.svelte` |
| Segment speaker reassignment | Complete | Good | `endpoints/transcript_segments.py` |
| Waveform visualization | Complete | Good | `WaveformPlayer.svelte` (canvas-based, click-to-seek) |
| Export (TXT/JSON/CSV/SRT/VTT) | Complete | Good | `ExportControls.svelte`, `services/subtitle_service.py` |
| Full-text search | Complete | Good | `services/opensearch_service.py`, `TranscriptSearch.svelte` |
| Analytics/stats | Complete | Good | `services/analytics_service.py`, `AnalyticsSection.svelte` |
| Collections/tagging | Complete | Good | `endpoints/media_collections.py`, `endpoints/tags.py` |
| Topic extraction | Complete | Good | `services/topic_extraction_service.py` |
| Comments (timestamped) | Complete | Basic | `endpoints/comments.py`, `CommentSection.svelte` |
| Multi-language transcription | Complete | Good | 100+ languages, 42 with word-level timestamps |
| Dark/light theme | Complete | Polished | CSS variables throughout |
| i18n (7 UI languages) | Complete | Good | `frontend/src/lib/i18n/` |
| Auth (multi-method) | Complete | Enterprise | `backend/app/auth/` (12+ files) |
| Task recovery/monitoring | Complete | Good | `services/task_recovery_service.py` |

### Database Schema (17 tables)

```
user                    - Auth, roles, compliance fields
user_mfa                - TOTP multi-factor auth
refresh_token           - JWT refresh tokens
password_history        - Password reuse prevention
media_file              - Files with metadata, waveform_data, summary_data (JSONB)
transcript_segment      - Segments: media_file_id, speaker_id, start_time, end_time, text
speaker                 - Per-file: name, display_name, suggested_name, verified, confidence
speaker_profile         - Global identity across files
speaker_match           - Cross-file speaker similarity scores
speaker_collection      - Speaker grouping
speaker_collection_member
tag / file_tag          - Tagging system
task                    - Celery task tracking
analytics               - Per-file analytics (JSONB)
collection / collection_member - File collections
topic_suggestion        - AI-generated tag/collection suggestions
summary_prompt          - Custom LLM prompts
user_setting            - User preferences (key-value)
user_llm_settings       - Per-user LLM provider config
system_settings         - Global system config
```

### Current Transcription Pipeline Flow
```
Upload → MinIO storage → Celery task dispatched →
  1. Download from MinIO (0-10%)
  2. Audio extraction/conversion to WAV 16kHz (10-38%)
  3. WhisperX transcription (40-50%)
  4. WhisperX alignment for word-level timestamps (50-55%)
  5. PyAnnote diarization (55-65%)
  6. Speaker assignment to words (65-70%)
  7. Speaker record creation + embedding extraction (68-82%)
  8. Segment save to PostgreSQL (75-78%)
  9. OpenSearch indexing (82-85%)
  10. Post-processing: analytics, LLM speaker ID, summarization, topics (85-95%)
  → WebSocket notification to frontend
```

### Gap Analysis vs Requirements

| Requirement | OpenTranscribe Status | Gap Level | Approach |
|------------|----------------------|-----------|----------|
| Deepgram Nova-3 Medical | Not supported | **BUILD** | New ASR provider |
| Multi-engine ASR abstraction | WhisperX only, tightly coupled | **BUILD** | Provider interface pattern |
| Medical vocabulary/hot-words | None | **BUILD** | Keyterm prompting config |
| Confidence scoring per segment | Word-level from WhisperX but not stored in DB | **BUILD** | New column + UI |
| Human-in-the-loop review | Can edit text + reassign speakers, no formal workflow | **BUILD** | Review status system |
| Correction pattern learning | Does not exist | **BUILD** from scratch | New service + tables |
| Speaker name auto-detection | LLM-based exists, no intro pattern detection | **ENHANCE** existing | Extend LLM prompt |
| Benchmarking harness | Does not exist | **BUILD LATER** | Phase C |
| Export formats | TXT, JSON, CSV, SRT, VTT - good coverage | **MINOR ENHANCE** | Add structured JSON for LLM |
| FERPA compliance | Auth exists, no audit log or retention policies | **BUILD** | Phase D |
| Multi-tenant/RBAC | User + admin roles only | **SKIP for now** | Sufficient for single-team |
| Waveform + click-to-seek | EXISTS (WaveformPlayer.svelte) | **DONE** | No work needed |
| Batch processing | Upload multiple files, no session grouping | **SKIP for now** | Collections suffice |

---

## Phase 2: Integration Plan

### Upfront Architecture Decisions

#### 1. ASR Provider Abstraction Pattern

Create `backend/app/services/asr/` as a provider abstraction layer:

```
backend/app/services/asr/
├── __init__.py
├── base.py              # Abstract base class: ASRProvider
├── deepgram_provider.py # Deepgram Nova-3 Medical implementation
├── whisperx_provider.py # WhisperX wrapper (wraps existing whisperx_service.py)
├── types.py             # Shared data types: TranscriptionResult, Segment, Word
└── factory.py           # Provider factory: get_provider(name) → ASRProvider
```

The `ASRProvider` abstract base defines:
```python
class ASRProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: str, config: TranscriptionConfig) -> TranscriptionResult:
        """Returns unified TranscriptionResult with segments, speakers, words, confidence."""

    @abstractmethod
    def supports_diarization(self) -> bool:
        """Whether this provider handles diarization internally."""

    @abstractmethod
    def supports_keyterms(self) -> bool:
        """Whether this provider supports custom vocabulary/keyterms."""
```

`TranscriptionResult` is a unified dataclass:
```python
@dataclass
class TranscriptionResult:
    segments: list[Segment]       # Each with text, start, end, speaker_label, confidence
    words: list[Word]             # Word-level: text, start, end, confidence, speaker_label
    detected_language: str | None
    provider_metadata: dict       # Provider-specific extras
```

**Key insight**: Deepgram returns diarized+transcribed output in ONE call. WhisperX requires separate transcription → alignment → diarization → assignment. The provider abstraction hides this — each provider returns the same `TranscriptionResult`.

#### 2. Infrastructure Simplification

**Drop OpenSearch** — replace with PostgreSQL full-text search:
- For ~500 hours/year, PostgreSQL `tsvector` + `GIN` indexes are more than sufficient
- Eliminates an entire service, Java heap memory, and configuration complexity
- Speaker embeddings can use `pgvector` extension if needed later (or skip vector search for now — at your scale, a simple cosine similarity function in Python is fine)

**Simplify Celery** — keep Redis + Celery but with a single non-GPU worker:
- Deepgram is a cloud API, no GPU needed
- Single Celery worker with concurrency=2-4 handles your volume easily
- Remove GPU-specific Docker Compose overlays

**Keep MinIO** — needed for file storage, lightweight, already works

**Result**: PostgreSQL + Redis + MinIO + Celery worker (4 services vs current 6+)

#### 3. Deepgram Integration Design

Deepgram Nova-3 Medical returns everything in one API call:
```python
# In deepgram_provider.py
options = PrerecordedOptions(
    model="nova-3-medical",
    smart_format=True,
    diarize=True,
    keyterms=self.get_medical_keyterms(config),  # Up to 100 terms
    punctuate=True,
    paragraphs=True,
    utterances=True,  # Speaker-segmented utterances
)
```

Medical keyterms are stored in `system_settings` and/or `user_setting` tables:
- System-level default medical vocabulary list
- User-configurable additional terms per specialty
- Frontend settings UI for managing keyterm lists

#### 4. Database Schema Changes

**Add to `transcript_segment`:**
```sql
ALTER TABLE transcript_segment ADD COLUMN confidence FLOAT NULL;
ALTER TABLE transcript_segment ADD COLUMN review_status VARCHAR(20) DEFAULT 'auto';
-- review_status: 'auto' (untouched), 'flagged' (needs review), 'corrected', 'approved'
ALTER TABLE transcript_segment ADD COLUMN original_text TEXT NULL;
-- Stores pre-correction text for learning
ALTER TABLE transcript_segment ADD COLUMN flagged_reason VARCHAR(100) NULL;
-- e.g., 'low_confidence', 'medical_term', 'speaker_uncertain'
```

**Add to `media_file`:**
```sql
ALTER TABLE media_file ADD COLUMN review_status VARCHAR(20) DEFAULT 'draft';
-- review_status: 'draft', 'in_review', 'approved'
ALTER TABLE media_file ADD COLUMN asr_provider VARCHAR(50) NULL;
-- Track which provider was used
ALTER TABLE media_file ADD COLUMN asr_model VARCHAR(100) NULL;
```

**New table: `correction_pattern`:**
```sql
CREATE TABLE correction_pattern (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    original_text VARCHAR(500) NOT NULL,
    corrected_text VARCHAR(500) NOT NULL,
    context_hint VARCHAR(255) NULL,  -- e.g., medical specialty
    frequency INTEGER DEFAULT 1,
    last_applied TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, original_text)
);
```

**New table: `medical_keyterm`:**
```sql
CREATE TABLE medical_keyterm (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES "user"(id),  -- NULL = system-wide
    term VARCHAR(255) NOT NULL,
    category VARCHAR(100) NULL,  -- 'medication', 'anatomy', 'procedure', 'diagnosis'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, term)
);
```

---

## Phase A: MVP — Deepgram + Provider Abstraction

**Goal**: Upload → Deepgram transcription+diarization → view → edit → export. Multi-provider framework in place.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/services/asr/__init__.py` | Package init |
| `backend/app/services/asr/base.py` | `ASRProvider` ABC + `TranscriptionResult`, `Segment`, `Word` dataclasses |
| `backend/app/services/asr/types.py` | `TranscriptionConfig` dataclass (language, keyterms, translate, min/max speakers) |
| `backend/app/services/asr/deepgram_provider.py` | Deepgram Nova-3 Medical implementation |
| `backend/app/services/asr/whisperx_provider.py` | *(Deferred — requires GPU)* Wrap existing `WhisperXService` to conform to `ASRProvider` interface |
| `backend/app/services/asr/factory.py` | `get_asr_provider(name, config)` factory |

### Files to Modify

| File | Changes |
|------|---------|
| `backend/app/tasks/transcription/core.py` | Refactor `transcribe_audio_task()` to use ASR provider abstraction instead of calling WhisperXService directly. The provider returns `TranscriptionResult`, then existing speaker processing continues. |
| `backend/app/tasks/transcription/speaker_processor.py` | Accept `TranscriptionResult.segments` instead of WhisperX-specific format |
| `database/init_db.sql` | Add `confidence` column to `transcript_segment`, add `asr_provider`/`asr_model` to `media_file`, add `medical_keyterm` table |
| `backend/app/models/media.py` | Add `confidence` field to `TranscriptSegment`, `asr_provider`/`asr_model` to `MediaFile` |
| `backend/app/schemas/media.py` | Add `confidence` to segment schema, `asr_provider` to file schema |
| `backend/requirements.txt` | Add `deepgram-sdk>=3.0.0` |
| `.env.example` | Add `ASR_PROVIDER=deepgram`, `DEEPGRAM_API_KEY=`, `DEEPGRAM_MODEL=nova-3-medical` |
| `backend/app/core/config.py` | Add ASR provider settings |
| `frontend/src/components/TranscriptDisplay.svelte` | Show confidence indicator per segment (e.g., subtle background color) |
| `frontend/src/components/settings/TranscriptionSettings.svelte` | Add ASR provider selection dropdown |

### Infrastructure Changes

| File | Changes |
|------|---------|
| `docker-compose.yml` | Remove `opensearch` service, remove GPU requirements from celery-worker |
| `docker-compose.override.yml` | Simplify dev config (no GPU, no OpenSearch) |
| `backend/app/services/opensearch_service.py` | Stub out / make optional (search deferred to later version) |

**Note on search**: Full-text search is deferred. The OpenSearch service will be removed from Docker Compose and its service calls stubbed out so the app doesn't break. PostgreSQL full-text search can be added in a future version if needed.

### New Dependency
```
deepgram-sdk>=3.0.0
```

### Database Changes
```sql
-- transcript_segment: add confidence
ALTER TABLE transcript_segment ADD COLUMN confidence FLOAT NULL;

-- media_file: track ASR provider used
ALTER TABLE media_file ADD COLUMN asr_provider VARCHAR(50) NULL;
ALTER TABLE media_file ADD COLUMN asr_model VARCHAR(100) NULL;

-- medical keyterms
CREATE TABLE medical_keyterm (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES "user"(id),
    term VARCHAR(255) NOT NULL,
    category VARCHAR(100) NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(COALESCE(user_id, 0), term)
);
```

### Testing
- Unit test: DeepgramProvider returns correct TranscriptionResult format
- Unit test: WhisperXProvider returns correct TranscriptionResult format
- Integration test: Upload file → Deepgram processes → segments in DB → speakers created
- Manual: Upload a medical recording, verify medical terms are transcribed correctly with keyterms
- Manual: Verify waveform, playback, click-to-seek all work with Deepgram output
- Manual: Export TXT/JSON/CSV/SRT/VTT from Deepgram-processed file

### Definition of Done
- [ ] Can upload a file and have it transcribed by Deepgram Nova-3 Medical
- [ ] Speaker diarization from Deepgram creates Speaker records correctly
- [ ] Confidence scores stored and visible in transcript view
- [ ] ASR provider abstraction in place (Deepgram active, WhisperX deferred)
- [ ] Medical keyterms configurable in settings and sent to Deepgram
- [ ] Export formats work with Deepgram-processed transcripts
- [ ] OpenSearch removed, search stubbed out (no breakage)
- [ ] Docker setup runs without GPU requirement

---

## Phase B: Enhanced — Review Workflow + Improved Speaker ID

**Goal**: Hybrid human-in-the-loop review. Low-confidence segments auto-flagged. Transcript-level review status.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/services/review_service.py` | Review workflow logic: flag segments, update status, bulk approve |
| `backend/app/api/endpoints/review.py` | REST endpoints for review operations |
| `backend/app/schemas/review.py` | Pydantic schemas for review requests/responses |
| `frontend/src/components/ReviewPanel.svelte` | Review UI: filter flagged segments, approve/correct, bulk actions |
| `frontend/src/components/ConfidenceIndicator.svelte` | Visual confidence indicator (color-coded bar/dot) |
| `backend/app/services/asr/keyterm_service.py` | Manage medical keyterm lists, apply to requests |
| `backend/app/api/endpoints/keyterms.py` | CRUD for medical keyterms |
| `frontend/src/components/settings/KeytermSettings.svelte` | UI for managing medical vocabulary |

### Files to Modify

| File | Changes |
|------|---------|
| `database/init_db.sql` | Add `review_status`, `original_text`, `flagged_reason` to `transcript_segment`. Add `review_status` to `media_file`. |
| `backend/app/models/media.py` | Add review fields to TranscriptSegment and MediaFile |
| `backend/app/schemas/media.py` | Add review fields to schemas |
| `backend/app/tasks/transcription/core.py` | After transcription, auto-flag low-confidence segments (e.g., confidence < 0.7) |
| `frontend/src/components/TranscriptDisplay.svelte` | Highlight flagged segments, show review controls |
| `frontend/src/routes/files/[id]/+page.svelte` | Add ReviewPanel to file detail view |
| `backend/app/api/router.py` | Add review and keyterm routes |

### Database Changes
```sql
ALTER TABLE transcript_segment ADD COLUMN review_status VARCHAR(20) DEFAULT 'auto';
ALTER TABLE transcript_segment ADD COLUMN original_text TEXT NULL;
ALTER TABLE transcript_segment ADD COLUMN flagged_reason VARCHAR(100) NULL;
ALTER TABLE media_file ADD COLUMN review_status VARCHAR(20) DEFAULT 'draft';
```

### Testing
- Upload file → verify low-confidence segments auto-flagged
- Mark segment as corrected → verify original_text preserved
- Approve all segments → verify file status changes to 'approved'
- Filter view to show only flagged segments
- Medical keyterm CRUD works end-to-end

### Definition of Done
- [ ] Low-confidence segments auto-flagged after transcription
- [ ] Review UI shows flagged segments with ability to correct/approve
- [ ] File-level review status (draft → in_review → approved)
- [ ] Original text preserved when corrections made
- [ ] Medical keyterms configurable via UI
- [ ] Keyterms sent to Deepgram on subsequent transcriptions

---

## Phase C: Learning — Correction Patterns + Benchmarking

**Goal**: System learns from human corrections. Medical vocabulary improves. Can compare ASR engines.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/services/correction_service.py` | Track corrections, detect patterns, suggest corrections |
| `backend/app/models/correction.py` | `CorrectionPattern` SQLAlchemy model |
| `backend/app/api/endpoints/corrections.py` | CRUD + apply-suggestions endpoint |
| `backend/app/schemas/correction.py` | Pydantic schemas |
| `backend/app/services/benchmark_service.py` | Run same audio through multiple providers, compare WER |
| `backend/app/api/endpoints/benchmark.py` | Trigger benchmark, view results |
| `frontend/src/components/CorrectionSuggestions.svelte` | Show learned corrections during editing |
| `frontend/src/components/BenchmarkResults.svelte` | Display ASR comparison results |

### Files to Modify

| File | Changes |
|------|---------|
| `database/init_db.sql` | Add `correction_pattern` table, `benchmark_result` table |
| `backend/app/services/review_service.py` | When segment corrected, feed to correction_service |
| `backend/app/tasks/transcription/core.py` | After transcription, apply known correction patterns |
| `backend/app/api/router.py` | Add correction and benchmark routes |

### Correction Learning Algorithm (build from scratch)
```
1. When user corrects segment text:
   a. Store original_text → corrected_text in correction_pattern
   b. If pattern already exists, increment frequency
   c. Track context (speaker, medical specialty, recording type)
2. On new transcription:
   a. Query high-frequency patterns (frequency >= threshold)
   b. Apply exact + fuzzy matching to new segments
   c. Flag auto-corrected segments for review (never silently change)
3. Management:
   a. Admin UI to view/edit/delete patterns
   b. Toggle auto_apply per pattern
   c. Export/import patterns for sharing across instances
```

### Database Changes
```sql
CREATE TABLE correction_pattern (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    original_text VARCHAR(500) NOT NULL,
    corrected_text VARCHAR(500) NOT NULL,
    context_hint VARCHAR(255) NULL,
    frequency INTEGER DEFAULT 1,
    auto_apply BOOLEAN DEFAULT FALSE,  -- High-confidence patterns auto-applied
    last_applied TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, original_text)
);

CREATE TABLE benchmark_result (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    media_file_id INTEGER REFERENCES media_file(id),
    user_id INTEGER REFERENCES "user"(id),
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    word_error_rate FLOAT NULL,
    processing_time_seconds FLOAT NULL,
    cost_estimate FLOAT NULL,
    segment_count INTEGER NULL,
    result_data JSONB NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### Testing
- Correct a segment → verify pattern created
- Transcribe new file with same error → verify correction suggested
- Run benchmark on test file → verify results from multiple providers
- Verify correction frequency tracking

### Definition of Done
- [ ] Corrections tracked with original/corrected text
- [ ] High-frequency patterns suggested during editing
- [ ] Auto-apply option for well-established patterns
- [ ] Benchmark harness compares 2+ providers on same audio
- [ ] WER/cost/speed metrics displayed

---

## Phase D: Production — FERPA Compliance + Hardening

**Goal**: FERPA compliance (audit logging, data access tracking), deployment hardening. No HIPAA requirements — environment is separate from the healthcare side.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/app/services/audit_service.py` | Structured audit logging for all data access |
| `backend/app/models/audit.py` | AuditLog model |
| `backend/app/middleware/audit_middleware.py` | FastAPI middleware for request logging |
| `backend/app/services/retention_service.py` | Data retention policy enforcement |
| `backend/app/api/endpoints/audit.py` | Admin audit log viewer |

### Files to Modify

| File | Changes |
|------|---------|
| `database/init_db.sql` | Add `audit_log` table, `data_retention_policy` table |
| `backend/app/api/endpoints/files/crud.py` | Add audit logging to file access |
| `backend/app/api/endpoints/transcript_segments.py` | Audit log edits |
| `backend/app/core/config.py` | Add retention and audit settings |

### Database Changes
```sql
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES "user"(id),
    action VARCHAR(100) NOT NULL,  -- 'file.view', 'segment.edit', 'file.export', 'file.delete'
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(255) NULL,
    details JSONB NULL,
    ip_address VARCHAR(45) NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX idx_audit_log_action ON audit_log(action);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);
```

### Definition of Done
- [ ] All file access, edits, exports, deletions audit-logged
- [ ] Admin can view audit logs with filtering
- [ ] Data retention policies configurable and enforced
- [ ] Deployment guide for FERPA-compliant setup
- [ ] Sensitive student data protected in application logs

---

## Cost Estimate (Deepgram Nova-3 Medical)

For ~500 hours/year of medical education recordings:

| Item | Cost | Notes |
|------|------|-------|
| Deepgram Nova-3 Medical (batch) | ~$231/year | 500hrs × 60min × $0.0077/min |
| Deepgram diarization add-on | ~$60-90/year | ~$0.002/min additional |
| LLM summarization (optional) | Varies | Depends on provider; $0 with local Ollama |
| Infrastructure (PostgreSQL, Redis, MinIO) | $0 (self-hosted) | Runs on existing server |
| **Total estimated** | **~$300-350/year** | Academic budget friendly |

Deepgram offers a free tier (200 minutes/month = 2,400 min/year) which covers initial development and testing.

---

## Technical Risks & Mitigation

| Risk | Severity | Mitigation |
|------|----------|------------|
| **AGPL-3.0 license** — fork must remain AGPL, source must be available if served over network | Medium | Acceptable for academic use. Keep fork open-source. Your additions are automatically AGPL. |
| **OpenSearch removal** — speaker embeddings currently stored there for vector similarity | High | At ~500hrs/year scale, compute cosine similarity in Python against small set of profiles. Add `pgvector` later if needed. |
| **Deepgram output format mismatch** — Deepgram segment/word structure differs from WhisperX | Medium | The provider abstraction normalizes to `TranscriptionResult`. Main risk is edge cases in speaker assignment mapping. |
| **WhisperX refactoring** — extracting from tightly-coupled pipeline | Medium | Wrap existing code rather than rewrite. `WhisperXProvider` delegates to existing `WhisperXService`. |
| **Celery without GPU** — existing worker assumes GPU | Low | Just change concurrency settings and remove GPU device mapping from Docker. |
| **Medical term accuracy** — Deepgram keyterms limited to 100 per request | Low | 100 terms covers most specialty vocabularies. Can rotate/prioritize terms per recording type. |
| **PostgreSQL full-text search** — less powerful than OpenSearch | Low | `tsvector` with GIN indexes handles transcript search at this scale. No vector search needed initially. |

## What to Migrate from Prototype vs Build Fresh

| Component | Approach | Rationale |
|-----------|----------|-----------|
| Timestamp-overlap merge algorithm | **Not needed** | Deepgram returns diarized output directly |
| Speaker name auto-detection | **Enhance existing** | OpenTranscribe's LLM speaker ID is more sophisticated than regex intro patterns |
| Human-in-the-loop review | **Build fresh** | OpenTranscribe's architecture better supports this with proper models/endpoints |
| Correction pattern learning | **Build from scratch** | Design algorithm for tracking corrections, detecting patterns, suggesting fixes. No existing implementation to port. |
| Benchmarking harness | **Build fresh** | Concept from prototype is valid, but needs to work with new provider abstraction |
| Flask UI / waveform | **Not needed** | OpenTranscribe's Svelte UI + WaveformPlayer is superior |
| SQLite schema | **Not needed** | PostgreSQL schema is more complete |

## How Celery Works (for reference)

Celery is a background task queue — think of it as a "to-do list" for the server. Here's the flow:

```
1. You upload a file via the web UI
2. The FastAPI web server saves the file and creates a "task" message
3. The message goes to Redis (a fast message broker — like a mailbox)
4. A Celery "worker" process picks up the task from Redis
5. The worker calls the Deepgram API, waits for results, saves to DB
6. The worker sends a WebSocket notification → your browser updates
```

You don't interact with Celery directly. It runs as a Docker container alongside the web server. For your volume (~500hrs/year), a single worker with concurrency=2 handles everything easily. No GPU needed since Deepgram is a cloud API.

## Implementation Priority & Dependencies

```
Phase A (MVP) ← START HERE
├── ASR provider abstraction (base.py, types.py, factory.py)
├── Deepgram provider implementation (primary and only active engine)
├── Core.py refactor to use provider abstraction
├── DB: confidence column, asr_provider tracking
├── Infrastructure simplification (drop OpenSearch, remove GPU reqs)
├── Frontend: provider settings, confidence display
└── Medical keyterm table + basic management

Phase B (Enhanced) ← depends on Phase A
├── Review workflow (review_status on segments + files)
├── Auto-flagging low-confidence segments
├── Review UI panel
├── Keyterm management UI
└── Enhanced speaker ID

Phase C (Learning) ← depends on Phase B
├── Correction pattern tracking (built from scratch)
├── Pattern suggestion during editing
├── Auto-apply high-confidence patterns
└── Benchmark harness (future — needs additional ASR providers)

Phase D (Production) ← can start after Phase A
├── Audit logging middleware + service (FERPA)
├── Data retention policies
├── Deployment hardening guide
└── FERPA compliance documentation
```

## Verification Plan

### Phase A Smoke Test
1. `./opentr.sh reset dev` — verify clean DB with new schema
2. Set `ASR_PROVIDER=deepgram` and `DEEPGRAM_API_KEY` in `.env`
3. Upload a medical education audio file via UI
4. Verify Celery worker picks up task and calls Deepgram API
5. Verify transcript segments appear with confidence scores
6. Verify speakers created correctly from Deepgram diarization
7. Click-to-seek in waveform works with new segments
8. Export SRT — verify timestamps and speaker labels correct
9. Verify app runs without OpenSearch (no errors, search gracefully disabled)

### Phase B Smoke Test
1. Upload file → verify low-confidence segments flagged
2. Open ReviewPanel → filter to flagged segments
3. Correct a segment → verify original_text preserved
4. Approve file → verify status changes
5. Configure medical keyterms → verify sent with next Deepgram request
