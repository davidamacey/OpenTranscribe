# Implementation Plan: Per-Transcription Whisper Model Selection

**GitHub Issue:** #153 — [FEATURE] Per-transcription Whisper model selection
**Requested by:** it-service-gemag
**Date drafted:** 2026-03-19

---

## Overview

Allow users to choose a Whisper model (e.g., `tiny`, `medium`, `large-v2`, `large-v3`,
`large-v3-turbo`) per transcription request, rather than being locked to the global
admin-set model. This enables speed-vs-accuracy trade-offs for mixed workloads: a 10-minute
meeting note can run on `tiny` in seconds while a recorded conference runs on `large-v3`
for maximum accuracy — all on the same system.

---

## Current Behavior Analysis

### Model Selection Today

Resolution order in `TranscriptionConfig._resolve_model_name()`:

```
1. _pinned_model_name (ClassVar set at worker startup)
   → prevents mid-flight swaps when admin changes DB setting
2. SystemSettings.key == "asr.local_model"  (admin-set via UI)
3. WHISPER_MODEL env var
4. Hardcoded default: "large-v3-turbo"
```

**File:** `backend/app/transcription/config.py:149-176`

### Worker Startup & Model Pinning

At GPU worker startup (`worker_ready` signal), `TranscriptionConfig.pin_model(model_name)` is
called after preloading. This sets `_pinned_model_name` as a ClassVar, making it the
authoritative value for all subsequent tasks in that worker process.

**File:** `backend/app/transcription/config.py:134-146`

### Model Loading / Caching

`ModelManager` (singleton, `backend/app/transcription/model_manager.py`) keeps one transcriber
and one diarizer warm between tasks. Cache invalidation is by `config_hash()`:

```python
def config_hash(self) -> str:
    key = f"{self.model_name}:{self.compute_type}:{self.device}:{self.device_index}"
    return hashlib.md5(key.encode()).hexdigest()[:12]
```

When the hash changes (i.e., a different model is requested), `ModelManager.get_transcriber()`
calls `transcriber.unload_model()`, clears VRAM, and loads the new model. This is already
implemented for model-switching scenarios — it just isn't exercised per-task today.

**Files:**
- `backend/app/transcription/model_manager.py:48-67`
- `backend/app/transcription/transcriber.py:98-121`

### Pipeline Architecture (3-stage Celery chain)

```
CPU: preprocess_for_transcription.s(file_uuid, task_id, min_speakers, ..., source_language, ...)
     ↓  passes context dict
GPU: transcribe_gpu_task.s(preprocess_context)
     ↓  passes extended context dict
CPU: finalize_transcription.s(result_context)
```

Parameters such as `min_speakers`, `source_language`, and `translate_to_english` already flow
through the context dict from API → dispatch → preprocess → GPU task. The per-task model name
should follow the exact same pattern.

**Files:**
- `backend/app/tasks/transcription/dispatch.py:59-141`
- `backend/app/tasks/transcription/preprocess.py:47-148`
- `backend/app/tasks/transcription/core.py:1780-1792` (`transcribe_gpu_task`)

### Where Model Override Would Hook In

In `_run_transcription_pipeline()` (`core.py:724-792`), overrides are collected into a dict and
passed to `TranscriptionConfig.from_environment(**overrides)`:

```python
# core.py:750-765
overrides: dict = dict(
    source_language=source_language,
    translate_to_english=translate_to_english,
    min_speakers=...,
    ...
)
# NOTE: No model_name override — comment says "local model is pinned at worker startup"

config = TranscriptionConfig.from_environment(**overrides)
```

`from_environment()` first calls `_resolve_model_name()` (which returns the pinned value), then
applies all `overrides` via `setattr`. So passing `model_name="tiny"` as an override **would
already work** — it overwrites the pinned value. The pin is designed to prevent accidental
mid-flight swaps from admin UI changes, not to block intentional per-task overrides.

### Existing DB Column

`media_file.whisper_model` (VARCHAR, nullable) was added in migration `v130`. It is written at
transcription completion with the model that was **actually used**. It is already displayed in
the file detail panel (`user_files.py:250`, `298`).

There is no column tracking the **requested** model — this gap needs to be filled so we can
detect fallback scenarios.

### ASR Provider Catalog

`backend/app/services/asr/factory.py:ASR_PROVIDER_CATALOG["local"]["models"]` already lists all
models with metadata including `supports_translation`, `language_support`, VRAM estimates, etc.:

| id | display_name | VRAM | Translation | Language |
|----|-------------|------|-------------|----------|
| `large-v3-turbo` | Large V3 Turbo | ~6 GB | No | english_optimized |
| `large-v3` | Large V3 | ~10 GB | Yes | multilingual |
| `large-v2` | Large V2 | ~10 GB | Yes | multilingual |
| `medium` | Medium | ~5 GB | Yes | multilingual |
| `small` | Small | ~2 GB | Yes | multilingual |
| `base` | Base | ~1 GB | Yes | multilingual |
| `tiny` | Tiny | <1 GB | Yes | multilingual |

The existing `/api/asr-settings/providers` endpoint exposes this catalog with `downloaded`
annotations, which can be reused on the frontend.

---

## Planned Changes

### 1. Database — New Migration

**File to create:** `backend/alembic/versions/v350_add_requested_whisper_model.py`

```python
revision = "v350_add_requested_whisper_model"
down_revision = "v340_add_user_media_sources"

def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'media_file'
                  AND column_name = 'requested_whisper_model'
            ) THEN
                ALTER TABLE media_file
                ADD COLUMN requested_whisper_model VARCHAR;

                COMMENT ON COLUMN media_file.requested_whisper_model IS
                    'Whisper model requested by the user at upload/reprocess time. '
                    'May differ from whisper_model if a fallback occurred.';
            END IF;
        END $$;
    """)

def downgrade():
    op.execute("ALTER TABLE media_file DROP COLUMN IF EXISTS requested_whisper_model")
```

**Why two columns?**

| Column | Semantics | Written by |
|--------|-----------|------------|
| `whisper_model` | Model that **actually ran** (ground truth) | `update_media_file_transcription_status()` at task end |
| `requested_whisper_model` | Model the user **asked for** (intent) | `prepare_upload` / reprocess endpoint before task starts |

Separating them lets the UI show "You requested `tiny` but `large-v3-turbo` was used (model
not downloaded)" without ambiguity. When no fallback occurred they are equal.

**Update `backend/app/models/media.py`:**

```python
# After the existing whisper_model column (~line 110):
requested_whisper_model = Column(String, nullable=True)
# Model requested by user at upload/reprocess time.
# Differs from whisper_model when a fallback occurred.
```

**Update `backend/app/db/migrations.py`:**
Add detection for `v350` in the startup migration runner (same pattern as existing version checks).

---

### 2. Backend — Pydantic Schemas

**File:** `backend/app/schemas/media.py`

Add `whisper_model: Optional[str]` to both request schemas:

```python
# In PrepareUploadRequest (line ~84):
whisper_model: Optional[str] = Field(
    None,
    description="Whisper model to use for this file. None = use admin-configured default. "
                "Only applies to local ASR provider. Cloud providers use their own model selection.",
    examples=["tiny", "medium", "large-v2", "large-v3", "large-v3-turbo"],
)

# In ReprocessRequest (line ~26):
whisper_model: Optional[str] = Field(
    None,
    description="Whisper model to use for reprocessing. None = use admin-configured default.",
)
```

Add a validator to both schemas:

```python
VALID_LOCAL_MODELS = frozenset({
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v1", "large-v2", "large-v3", "large-v3-turbo",
})

@field_validator("whisper_model")
@classmethod
def validate_whisper_model(cls, v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v = v.strip()
    if v and v not in VALID_LOCAL_MODELS:
        raise ValueError(
            f"Unknown Whisper model '{v}'. "
            f"Valid local models: {sorted(VALID_LOCAL_MODELS)}"
        )
    return v or None
```

---

### 3. Backend — API Endpoints

#### 3a. Prepare Upload (`backend/app/api/endpoints/files/prepare_upload.py`)

After creating the `db_file` record, store the requested model:

```python
# After line 207 (storage_path assignment):
if request.whisper_model:
    db_file.requested_whisper_model = request.whisper_model
db.flush()
```

#### 3b. Upload / Dispatch (`backend/app/api/endpoints/files/upload.py`)

The `process_upload()` and `start_transcription_task()` functions need a `whisper_model`
parameter threaded through:

```python
def start_transcription_task(
    file_id: int,
    file_uuid: str,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    num_speakers: int | None = None,
    whisper_model: str | None = None,       # NEW
    ...
):
    ...
    task_id = dispatch_transcription_pipeline(
        file_uuid=file_uuid,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        num_speakers=num_speakers,
        whisper_model=whisper_model,         # NEW
    )
```

The upload endpoint that handles form data (where `min_speakers` etc. is already accepted)
should also accept `whisper_model` — either as a form field or by reading it from
`media_file.requested_whisper_model` after the prepare step.

**Recommended approach:** Read `requested_whisper_model` from the already-created `MediaFile`
record rather than requiring the client to send it twice. This eliminates duplication and
keeps the `prepare → upload` contract clean:

```python
# In the upload function, after fetching db_file:
whisper_model = db_file.requested_whisper_model  # Set during prepare_upload
```

#### 3c. Reprocess (`backend/app/api/endpoints/files/reprocess.py`)

Update `process_file_reprocess()` and `start_reprocessing_task()`:

```python
async def process_file_reprocess(
    file_uuid: str,
    db: Session,
    current_user: User,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    num_speakers: int | None = None,
    stages: list[str] | None = None,
    whisper_model: str | None = None,   # NEW
) -> MediaFile:
    ...
    # Before dispatching, update the requested model on the record:
    if whisper_model:
        media_file.requested_whisper_model = whisker_model
        db.commit()

    start_reprocessing_task(
        file_uuid,
        min_speakers=min_speakers,
        ...
        whisper_model=whisper_model,    # NEW
    )
```

Update `start_reprocessing_task()` to pass through to `dispatch_transcription_pipeline()`.

#### 3d. URL Processing (`backend/app/api/endpoints/files/url_processing.py`)

Inspect and add `whisper_model` parameter to the URL-based download-and-transcribe endpoint,
following the same pattern as `min_speakers`.

#### 3e. Management Endpoint

Find the reprocess endpoint in `backend/app/api/endpoints/files/management.py` (or wherever
`ReprocessRequest` is consumed) and thread `request.whisper_model` through to
`process_file_reprocess()`.

---

### 4. Backend — Pipeline Dispatch

**File:** `backend/app/tasks/transcription/dispatch.py`

```python
def dispatch_transcription_pipeline(
    file_uuid: str,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    num_speakers: int | None = None,
    downstream_tasks: list[str] | None = None,
    source_language: str | None = None,
    translate_to_english: bool | None = None,
    gpu_queue: str | None = None,
    whisper_model: str | None = None,       # NEW
) -> str:
    ...
    pipeline = chain(
        preprocess_for_transcription.s(
            file_uuid=file_uuid,
            task_id=task_id,
            min_speakers=min_speakers,
            ...
            whisper_model=whisper_model,    # NEW
        ).set(queue="cpu", ...),
        ...
    )
```

Also update `dispatch_batch_transcription()` to accept and forward `whisper_model` via the
`**kwargs` that are already passed to `preprocess_for_transcription.s()`.

---

### 5. Backend — Preprocess Task

**File:** `backend/app/tasks/transcription/preprocess.py`

Add `whisper_model` to the task signature and context dict:

```python
@celery_app.task(...)
def preprocess_for_transcription(
    self,
    file_uuid: str,
    task_id: str,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    num_speakers: int | None = None,
    downstream_tasks: list[str] | None = None,
    source_language: str | None = None,
    translate_to_english: bool | None = None,
    whisper_model: str | None = None,       # NEW
) -> dict:
    ...
    return {
        ...
        "min_speakers": min_speakers,
        "max_speakers": max_speakers,
        "num_speakers": num_speakers,
        "downstream_tasks": downstream_tasks,
        "source_language": source_language,
        "translate_to_english": translate_to_english,
        "whisper_model": whisper_model,     # NEW
    }
```

---

### 6. Backend — GPU Task & Pipeline Runner

**File:** `backend/app/tasks/transcription/core.py`

#### 6a. Extract from context dict in `transcribe_gpu_task`:

```python
def transcribe_gpu_task(self, preprocess_context: dict) -> dict:
    ...
    whisper_model = preprocess_context.get("whisper_model")  # NEW
    ...
    result = _do_transcription(
        ctx, audio_file_path,
        min_speakers=...,
        ...
        whisper_model=whisper_model,    # NEW
    )
```

#### 6b. Thread through the call chain to `_run_transcription_pipeline`:

```python
def _run_transcription_pipeline(
    ctx: TranscriptionContext,
    audio_file_path: str,
    min_speakers: int | None,
    max_speakers: int | None,
    num_speakers: int | None,
    source_language: str | None = None,
    translate_to_english: bool | None = None,
    whisper_model: str | None = None,       # NEW
) -> dict:
    ...
    overrides: dict = dict(
        source_language=source_language,
        translate_to_english=translate_to_english,
        min_speakers=...,
        ...
    )

    # NEW: Apply per-task model override if provided
    if whisper_model:
        _validate_model_override(whisper_model)
        overrides["model_name"] = whisper_model
        logger.info(
            "Per-task model override: '%s' (admin default: '%s')",
            whisper_model,
            TranscriptionConfig._pinned_model_name,
        )

    config = TranscriptionConfig.from_environment(**overrides)
    # The override loop in from_environment() applies model_name AFTER _resolve_model_name(),
    # so the per-task model takes precedence over the pinned value.
```

#### 6c. Add validation helper:

```python
_VALID_LOCAL_MODELS = frozenset({
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v1", "large-v2", "large-v3", "large-v3-turbo",
})

def _validate_model_override(model_name: str) -> None:
    """Validate and log the per-task model override. Falls back gracefully."""
    if model_name not in _VALID_LOCAL_MODELS:
        logger.warning(
            "Unknown model override '%s', ignoring and using admin default",
            model_name,
        )
        return

    # Check if model is downloaded
    try:
        from app.services.asr.model_discovery import get_downloaded_model_names
        downloaded = get_downloaded_model_names()
        if model_name not in downloaded:
            logger.warning(
                "Requested model '%s' is not downloaded on this worker; "
                "falling back to admin-pinned model '%s'.",
                model_name,
                TranscriptionConfig._pinned_model_name,
            )
            # Return without adding to overrides — caller handles the None case
            raise ModelNotAvailableError(model_name)
    except ModelNotAvailableError:
        raise
    except Exception as e:
        logger.debug("Model availability check failed (%s), proceeding optimistically", e)
```

Use a custom exception (`ModelNotAvailableError`) to cleanly fall back to the default:

```python
class ModelNotAvailableError(Exception):
    def __init__(self, model_name: str):
        self.model_name = model_name
        super().__init__(f"Model '{model_name}' not available on this worker")
```

Then in `_run_transcription_pipeline`:

```python
if whisper_model:
    try:
        _validate_model_override(whisper_model)
        overrides["model_name"] = whisper_model
    except ModelNotAvailableError as e:
        logger.warning("Falling back to admin default: %s", e)
        # Keep whisper_model out of overrides → uses pinned model
```

#### 6d. Update `update_media_file_transcription_status` call site

The whisper_model written to DB at save time should be `config.model_name` (the actual model
used), which is already correct. No change needed here.

---

### 7. Backend — Concurrent Mode Guard

**Critical:** In concurrent GPU mode (`concurrent_requests > 1`), multiple threads share the
`ModelManager` singleton. Swapping a model while another thread is mid-inference will crash.

**File:** `backend/app/transcription/model_manager.py`

The existing `_lock = threading.RLock()` in `ModelManager` wraps model load/unload but NOT the
inference itself (inference happens outside the lock). This means:

- Thread A holds the model running inference (outside the lock)
- Thread B acquires the lock, sees hash mismatch, unloads the model
- Thread A crashes with a NullPointer / CUDA error

**Fix options (in order of preference):**

**Option A — Disallow per-task override in concurrent mode** (safest, MVP):

```python
# In _run_transcription_pipeline:
if whisper_model and config.concurrent_requests > 1:
    logger.warning(
        "Per-task model override ('%s') is not supported in concurrent GPU mode "
        "(concurrent_requests=%d). Using admin-pinned model '%s'.",
        whisper_model, config.concurrent_requests, TranscriptionConfig._pinned_model_name,
    )
    # Do not add model_name to overrides
```

Surface this to the user as a warning in the file detail panel.

**Option B — Inference hold lock** (performance risk, not recommended for concurrent mode):

Restructure `ModelManager` so inference is inside the lock. This serializes all concurrent
requests and negates the benefit of concurrent mode.

**Option C — Per-model worker queues** (best long-term, Phase 3):

Route tasks to dedicated per-model queues. Each queue is backed by a worker pinned to that
model. No locking needed. See Phase 3 below.

**Recommendation:** Implement Option A for the MVP. Document Option C as the path to zero
overhead for production systems.

---

### 8. Backend — Translation Constraint

`large-v3-turbo` was not trained for translation. If a user requests:
- `whisper_model = "large-v3-turbo"` AND
- `translate_to_english = true`

the transcriber will silently fall back to `task="transcribe"` (already handled in
`transcriber.py:140-153`). To give users clearer feedback:

**At API validation time** (in `PrepareUploadRequest` or the reprocess endpoint):
- Add a cross-field validator that returns a 400 error or warning if
  `whisper_model="large-v3-turbo"` and `translate_to_english=true`.

**At task time** (`_run_transcription_pipeline`):
- Log a warning and notify via WebSocket that translation was disabled for this file.
- Consider storing a `processing_warning` field on `media_file` (future work).

For MVP: emit a backend warning log and proceed with transcription-only mode. Surface this
in the file detail UI by comparing `whisper_model` to `"large-v3-turbo"` when
`translate_to_english` was set.

---

### 9. Backend — File Detail Response

`user_files.py:get_file_detailed_status()` already returns `whisper_model` in the response.
Extend it to also return `requested_whisper_model`:

```python
# user_files.py ~line 298:
"whisper_model": media_file.whisper_model,
"requested_whisper_model": media_file.requested_whisper_model,  # NEW
"model_fallback_occurred": (
    media_file.requested_whisper_model is not None
    and media_file.whisper_model is not None
    and media_file.requested_whisper_model != media_file.whisper_model
),
```

---

### 10. Frontend Changes

#### 10a. TypeScript Types

**File:** `frontend/src/lib/api/transcriptionSettings.ts` (or wherever `PrepareUploadRequest`
types live)

```typescript
export interface PrepareUploadRequest {
  filename: string;
  file_size: number;
  content_type: string;
  file_hash?: string;
  min_speakers?: number | null;
  max_speakers?: number | null;
  num_speakers?: number | null;
  whisper_model?: string | null;   // NEW
  collection_ids?: string[];
  tag_names?: string[];
  upload_batch_id?: string;
}

export interface ReprocessRequest {
  stages?: string[];
  min_speakers?: number | null;
  max_speakers?: number | null;
  num_speakers?: number | null;
  whisper_model?: string | null;   // NEW
}
```

Add a new type for local model metadata:

```typescript
export interface LocalWhisperModel {
  id: string;           // e.g., "large-v3-turbo"
  display_name: string; // e.g., "Large V3 Turbo"
  description: string;
  downloaded: boolean;
  supports_translation: boolean;
  language_support: string;  // "english_optimized" | "multilingual"
}
```

#### 10b. API Helper

**File:** `frontend/src/lib/api/asrSettings.ts` (create or extend)

```typescript
// Reuse the existing /api/asr-settings/providers endpoint:
export async function getLocalWhisperModels(): Promise<LocalWhisperModel[]> {
  const { data } = await axiosInstance.get('/api/asr-settings/providers');
  const localProvider = data.providers?.find((p: any) => p.id === 'local');
  return localProvider?.models ?? [];
}
```

This returns the catalog with `downloaded: true/false` annotations, which lets the UI
show which models are ready to use vs. need downloading.

#### 10c. FileUploader Component

**File:** `frontend/src/components/FileUploader.svelte`

**State variables** (add near the `minSpeakers`/`maxSpeakers` variables, ~line 125):

```typescript
let selectedWhisperModel: string | null = null;  // null = use system default
let availableWhisperModels: LocalWhisperModel[] = [];
let showModelSelector = false;
```

**On mount**, fetch local models alongside transcription settings:

```typescript
const [userSettings, systemDefaults, localModels] = await Promise.all([
  getTranscriptionSettings(),
  getTranscriptionSystemDefaults(),
  getLocalWhisperModels(),
]);
availableWhisperModels = localModels;
```

**User preference**: Load a saved default from `transcriptionSettings.preferred_whisper_model`
(see Section 13 — user preference storage, a Phase 2 item). For MVP, start with `null`.

**UI** (add inside the Advanced Settings panel, near the speaker count inputs):

```svelte
<!-- Whisper Model Selection -->
<div class="form-group">
  <label for="whisper-model-select">{$t('uploader.whisperModel')}</label>
  <select id="whisper-model-select" bind:value={selectedWhisperModel} class="form-control">
    <option value={null}>{$t('uploader.useSystemDefault')} ({adminModel})</option>
    {#each availableWhisperModels as model}
      <option value={model.id} disabled={!model.downloaded}>
        {model.display_name}
        {#if !model.downloaded}({$t('uploader.notDownloaded')}){/if}
        {#if model.id === adminModel}({$t('uploader.systemDefault')}){/if}
      </option>
    {/each}
  </select>
  {#if selectedWhisperModel}
    {@const modelInfo = availableWhisperModels.find(m => m.id === selectedWhisperModel)}
    {#if modelInfo}
      <p class="model-hint">{modelInfo.description}</p>
      {#if !modelInfo.supports_translation && transcribeLang !== 'auto'}
        <p class="model-warning">{$t('uploader.turboNoTranslation')}</p>
      {/if}
    {/if}
  {/if}
</div>
```

**Integrate into prepare-upload call:**

```typescript
// In the prepare upload function, add to the request body:
whisper_model: selectedWhisperModel || null,
```

**Show system default model name**: Fetch via `/api/asr-settings/local-model/active` (already
returns `active_model`). Display this in the "(use system default)" option label so users know
what they're getting.

#### 10d. File Detail View

In the file detail / info panel, display both model columns:

```svelte
{#if file.whisper_model}
  <div class="detail-row">
    <span class="label">{$t('fileDetail.whisperModel')}</span>
    <span class="value">
      {file.whisper_model}
      {#if file.model_fallback_occurred}
        <span class="badge warning" title="Requested: {file.requested_whisper_model}">
          {$t('fileDetail.modelFallback')}
        </span>
      {/if}
    </span>
  </div>
{/if}
```

#### 10e. Batch Upload

When uploading multiple files, the model selector applies to ALL files in the batch (same as
how speaker settings work today). Each file's `PrepareUploadRequest` sends the same
`whisper_model` value.

**Future enhancement (Phase 2):** Allow per-file model override in a batch upload table view.

#### 10f. i18n Keys

Add to all locale files (`frontend/src/lib/i18n/locales/*.json`):

```json
{
  "uploader": {
    "whisperModel": "Transcription Model",
    "useSystemDefault": "Use system default",
    "systemDefault": "default",
    "notDownloaded": "not downloaded",
    "turboNoTranslation": "Note: Large V3 Turbo does not support translation. Translation will be disabled for this file."
  },
  "fileDetail": {
    "whisperModel": "ASR Model",
    "modelFallback": "Fallback occurred",
    "requestedModel": "Requested model"
  }
}
```

---

## Edge Cases

### GPU Memory with Multiple Models

**Risk:** Admin has `large-v3-turbo` loaded (~6 GB). User requests `large-v3` (~10 GB). If the
GPU has 12 GB VRAM, the worker must unload `large-v3-turbo` completely before loading
`large-v3`.

**Mitigation:**
- `ModelManager.get_transcriber()` already calls `unload_model()` + `_cleanup_gpu()` (which
  calls `torch.cuda.empty_cache()`) before loading a new model. Peak VRAM during the swap is
  the minimum of the two model sizes (since unload completes before load begins).
- The model-swap window (during which the GPU queue stalls) is 30–120s depending on model size
  and whether the model is cached on disk. Subsequent requests for the same model hit the warm
  cache.
- If VRAM is insufficient even for the smaller model, the task fails with a CUDA OOM error and
  the existing OOM handler logs diagnostics and marks the file as errored.

**Admin recommendation:** Document that enabling per-task model selection on a system with
mixed model requests will incur model-swap latency. For high-throughput systems, use the Phase 3
per-model queue approach instead.

### Model Switching Overhead

**Scenario:** 100 files queued, alternating between `tiny` and `large-v3`. Each swap costs
~60s. Net overhead: ~100 × 60s = 100 minutes of wasted time.

**Mitigation for MVP:** Sort/group tasks by model in the queue before dispatching. This is
a backend batching concern, not a user-facing one.

**Better mitigation (Phase 2):** Implement a `gpu-model-{name}` queue per model. Tasks are
routed to the queue matching their requested model. Workers are pre-pinned to their queue's
model. No swaps occur.

**Better mitigation (Phase 3):** Dynamic worker pool with multiple GPUs, each running a
different model.

### Fallback Behavior

When the requested model is not available (not downloaded, or VRAM insufficient):

1. `_validate_model_override()` raises `ModelNotAvailableError`
2. `_run_transcription_pipeline` catches it and logs a warning
3. No `model_name` override is added → `TranscriptionConfig` uses the pinned admin model
4. `media_file.whisper_model` is written with the actual model used
5. `media_file.requested_whisper_model` retains the original request
6. `model_fallback_occurred = True` is surfaced in the file detail API response
7. Frontend shows a fallback badge in the file detail panel

**No failure**: The task completes successfully using the admin-default model. The user is
informed after the fact, not before, to avoid blocking the upload flow.

### Concurrent Requests with Different Models

As described in Section 7, per-task model override is disabled in concurrent mode
(`concurrent_requests > 1`). The worker logs a warning and uses the admin-pinned model.

This is the safest behavior because:
- The `ModelManager` singleton is shared across threads
- Model unload mid-inference causes crashes
- Concurrent mode is specifically designed for high-throughput same-model workloads

The frontend should detect concurrent mode via a new system info endpoint (or via the existing
ASR status endpoint) and display a tooltip explaining why the model selector is disabled.

### Queue Prioritization

When a user requests a fast model (`tiny`) for a quick turnaround, but the GPU is busy
processing a `large-v3` job (2-hour audio), the fast job must wait.

**MVP:** No special prioritization. All GPU jobs queue at the same priority.

**Phase 2 option:** Add a `priority` field to `PrepareUploadRequest`. Fast models (tiny/small)
get higher queue priority so they don't wait behind large jobs. This requires a priority queue
implementation in Celery/Redis.

### Reprocess with Model Override

When reprocessing an existing file with a different model:
- `process_file_reprocess()` accepts `whisper_model` from `ReprocessRequest`
- The existing `media_file.requested_whisper_model` is updated before dispatch
- The existing `media_file.whisper_model` is overwritten at completion with the new actual model
- Previous `requested_whisper_model` is lost (acceptable — the new request supersedes the old)

---

## Compatibility Concerns

### Migration Path

The `v350` migration uses `IF NOT EXISTS` guards (same as all other migrations). Existing
databases gain the new column with `NULL` value for all rows (backward compatible). The column
is optional everywhere.

### Backward Compatibility for Existing API Consumers

`whisper_model` is a new optional field in `PrepareUploadRequest` and `ReprocessRequest`.
Existing clients that omit it receive the same behavior as today (admin-pinned model). No
breaking changes.

The response shape of `GET /api/user-files/{uuid}/status` gains two new optional fields
(`requested_whisper_model`, `model_fallback_occurred`), which clients can ignore.

### Docker / GPU Resource Constraints

- No new Docker services or compose changes required
- No env var changes required (feature works with existing `WHISPER_MODEL` and
  `GPU_CONCURRENT_REQUESTS` config)
- GPU VRAM constraint: the feature may cause OOM if a user requests a model larger than
  available VRAM. The existing OOM handler already deals with this gracefully.

### Cloud ASR Compatibility

Per-task Whisper model selection applies **only to the local ASR provider**. For cloud
providers (Deepgram, AssemblyAI, etc.), the model is specified in the `UserASRSettings`
configuration and is not overridable per-file at this time. The API should silently ignore
`whisper_model` when the user's active ASR provider is cloud-based. Add a log at INFO level:

```python
if whisper_model and gpu_queue == "cloud-asr":
    logger.info(
        "whisper_model override '%s' ignored for cloud ASR provider", whisper_model
    )
    whisper_model = None
```

---

## Performance Considerations

### Model Loading Time

| Model | Approx. load time (NVMe cache, RTX 3080) |
|-------|------------------------------------------|
| tiny | ~3s |
| base | ~5s |
| small | ~8s |
| medium | ~15s |
| large-v2 / large-v3 | ~45–75s |
| large-v3-turbo | ~20–30s |

Loading times are dominated by disk I/O and CUDA initialization. CTranslate2 uses mmap, so
subsequent loads of the same model are faster (OS page cache).

**Impact on queue:** During model load, the GPU worker is blocked. Queued tasks wait.
For a system with frequent model switches, total queue stall is `n_switches × load_time`.

**Recommendation in docs:** Advise users that requesting uncommon models may add queue
latency. For consistent low-latency, prefer the admin-default model.

### Memory Footprint

Two-model VRAM usage (if future multi-model caching is implemented):

| Combination | VRAM |
|-------------|------|
| tiny + large-v3-turbo | ~7 GB |
| large-v3-turbo + large-v3 | ~16 GB |
| medium + large-v3-turbo | ~11 GB |

For MVP, only one model is loaded at a time. Multi-model caching is a Phase 3 concern.

### Caching Strategy

**MVP (Phase 1):** Single-model cache via existing `ModelManager`. Cache hit = zero overhead.
Cache miss = unload + load.

**Phase 2:** LRU model cache with configurable capacity. Keep the N most recently used models
loaded simultaneously (VRAM permitting). New requests for already-loaded models are served with
zero overhead regardless of which model was "last used."

**Phase 3:** Per-model worker queues. Each Celery queue is served by a worker pinned to one
model. No caching needed because the model is always the right one for that queue. Horizontal
scaling by adding workers.

---

## Testing Strategy

### Unit Tests

**File to create:** `backend/tests/unit/test_per_task_model_selection.py`

1. `test_model_override_applied_to_config`
   - Call `TranscriptionConfig.from_environment(model_name="tiny")` with a pinned model set
   - Assert `config.model_name == "tiny"` (override wins)

2. `test_model_override_changes_config_hash`
   - `config_a = TranscriptionConfig.from_environment()` (pinned to large-v3-turbo)
   - `config_b = TranscriptionConfig.from_environment(model_name="tiny")`
   - Assert `config_a.config_hash() != config_b.config_hash()`

3. `test_model_override_bypasses_pin`
   - Pin `"large-v3-turbo"`, override with `"medium"`
   - Assert `config.model_name == "medium"`

4. `test_model_override_ignored_in_concurrent_mode`
   - Set `concurrent_requests=2`, call pipeline with `whisper_model="tiny"`
   - Assert no `model_name` override in resulting config

5. `test_fallback_when_model_not_downloaded`
   - Mock `get_downloaded_model_names()` to return empty set
   - Call with `whisper_model="tiny"` → assert `ModelNotAvailableError` raised
   - Assert config uses pinned model

6. `test_schema_rejects_unknown_model`
   - `PrepareUploadRequest(whisper_model="nonexistent-model-xyz")` → `ValidationError`

7. `test_schema_accepts_valid_models`
   - For each model in `VALID_LOCAL_MODELS`: assert schema accepts it

### Integration Tests

**File to create:** `backend/tests/integration/test_model_selection_pipeline.py`

1. `test_prepare_upload_stores_requested_model`
   - POST `/api/files/prepare` with `whisper_model="medium"`
   - Assert `media_file.requested_whisper_model == "medium"`

2. `test_reprocess_stores_requested_model`
   - POST `/api/files/{uuid}/reprocess` with `{"whisper_model": "small"}`
   - Assert `media_file.requested_whisper_model == "small"`

3. `test_fallback_reflected_in_file_detail`
   - Set requested model to something not downloaded
   - After task completes, GET file detail
   - Assert `model_fallback_occurred == True`
   - Assert `whisper_model != requested_whisper_model`

4. `test_translation_warning_for_turbo`
   - Upload with `whisper_model="large-v3-turbo"` and translation enabled
   - Assert task completes (no error), actual `whisper_model == "large-v3-turbo"`
   - Assert transcript is in source language (not translated)

### E2E Tests

**File:** `backend/tests/e2e/test_model_selection.py`

1. `test_upload_with_model_selector_ui`
   - Navigate to upload UI
   - Open Advanced Settings, select "Medium" from model dropdown
   - Upload a small audio file
   - After completion, verify file detail shows "medium" as the model used

2. `test_system_default_option_shows_admin_model`
   - Login as user
   - Navigate to upload panel
   - Assert "(use system default)" option shows the admin-configured model name

3. `test_non_downloaded_models_disabled_in_ui`
   - Assert that models with `downloaded: false` appear disabled in the dropdown

---

## Implementation Phases

### Phase 1 — Core Feature (MVP)

**Scope:** Full stack end-to-end, single-model cache, no per-model queues.

**Steps in order:**

1. Write `v350` Alembic migration
2. Update `MediaFile` SQLAlchemy model (add `requested_whisper_model`)
3. Update `backend/app/db/migrations.py` detection
4. Add `whisper_model` to `PrepareUploadRequest` and `ReprocessRequest` schemas with validator
5. Store `requested_whisper_model` in `prepare_upload` endpoint
6. Thread `whisker_model` through `dispatch_transcription_pipeline()` and preprocess context
7. Add per-task model override in `_run_transcription_pipeline()` with concurrent-mode guard
8. Add `ModelNotAvailableError` and fallback logic in `_validate_model_override()`
9. Add `requested_whisper_model` + `model_fallback_occurred` to file detail API response
10. Frontend: fetch local models from `/api/asr-settings/providers` on mount
11. Frontend: add model selector dropdown to FileUploader Advanced Settings panel
12. Frontend: send `whisper_model` in prepare-upload payload
13. Frontend: display model info in file detail view with fallback badge
14. Frontend: add i18n keys for all 7 languages
15. Write unit + integration tests
16. Update CLAUDE.md noting the new column and pipeline param

**Estimated scope:** ~8–12 backend files changed, ~3–5 frontend files changed, 1 new migration.

### Phase 2 — User Preferences & Admin Controls

1. **Admin model allowlist:** Add a `SystemSettings` key `asr.allowed_models` (JSON array).
   Validate user requests against this list. Admin UI in Settings → ASR to configure.

2. **User default model preference:** Add `preferred_whisper_model` to `UserSetting`.
   Pre-populate the model selector with the user's saved preference. Save on change.

3. **Translation conflict warning at API layer:** Return a 422 or warning field when
   `whisper_model="large-v3-turbo"` is combined with `translate_to_english=true`.

4. **Per-model queue routing (optional):** Add queue names `gpu-tiny`, `gpu-medium`,
   `gpu-large-v3-turbo`, etc. in Celery config. Route tasks by requested model. Workers are
   pinned to their queue at startup. No VRAM swap overhead.

5. **Batch upload per-file model selection:** In the multi-file upload table, add a model
   column where each file can have an individual model selected.

6. **Concurrent mode model registry:** Instead of disabling the feature in concurrent mode,
   support a small set of "always-loaded" models (admin-configured) that are kept warm in
   VRAM simultaneously (VRAM budget permitting).

### Phase 3 — Multi-Model Worker Pool (High-Throughput)

1. **Dynamic worker provisioning:** Based on pending task distribution by requested model,
   spin up/down workers pinned to specific models.

2. **Multi-GPU routing:** Route each model to the GPU with enough VRAM and lowest current load.

3. **Model pre-warming:** Background job pre-loads commonly requested models to reduce
   first-task latency.

4. **GPU memory broker:** Shared service that tracks VRAM usage across workers and approves
   model load requests, preventing OOM races in multi-worker deployments.

---

## Files Changed Summary

| File | Change |
|------|--------|
| `backend/alembic/versions/v350_add_requested_whisper_model.py` | **NEW** — migration |
| `backend/app/models/media.py` | Add `requested_whisper_model` column |
| `backend/app/db/migrations.py` | Add v350 detection |
| `backend/app/schemas/media.py` | Add `whisper_model` to PrepareUploadRequest + ReprocessRequest |
| `backend/app/api/endpoints/files/prepare_upload.py` | Store `requested_whisper_model` |
| `backend/app/api/endpoints/files/upload.py` | Thread `whisper_model` to dispatch |
| `backend/app/api/endpoints/files/reprocess.py` | Thread `whisper_model`, update requested column |
| `backend/app/api/endpoints/files/url_processing.py` | Thread `whisper_model` |
| `backend/app/api/endpoints/files/management.py` | Pass `whisper_model` from ReprocessRequest |
| `backend/app/api/endpoints/user_files.py` | Return `requested_whisper_model` + fallback flag |
| `backend/app/tasks/transcription/dispatch.py` | Add `whisper_model` param to pipeline dispatch |
| `backend/app/tasks/transcription/preprocess.py` | Add `whisker_model` to task signature + context |
| `backend/app/tasks/transcription/core.py` | Apply override in `_run_transcription_pipeline` |
| `frontend/src/lib/api/asrSettings.ts` | Add `getLocalWhisperModels()` helper |
| `frontend/src/components/FileUploader.svelte` | Model selector UI + fetch + payload |
| `frontend/src/lib/i18n/locales/*.json` | New i18n keys (7 files) |
| `backend/tests/unit/test_per_task_model_selection.py` | **NEW** — unit tests |
| `backend/tests/integration/test_model_selection_pipeline.py` | **NEW** — integration tests |

---

## Open Questions for Feedback

1. **Admin allowlist:** Should admin be able to restrict which models users can select? Or is
   the download-check sufficient gating (if a model isn't downloaded, it's disabled in the UI)?

2. **Concurrent mode:** Is the concurrent GPU mode (`GPU_CONCURRENT_REQUESTS > 1`) widely used?
   If so, Phase 2 concurrent model registry support may be higher priority.

3. **Translation conflict:** Should `large-v3-turbo + translate=true` be a hard API error (422)
   or a soft warning (proceed, but warn)? The current code silently falls back to transcription
   mode; a warning might be more transparent.

4. **User default preference:** Should the model selector remember the user's last choice across
   sessions? (Phase 2 `preferred_whisper_model` in UserSetting.)

5. **Batch heterogeneous models:** For users uploading batches of files, should the model
   selector apply to all files or should there be a per-file override in the upload table?

6. **Model download flow:** Should the UI provide a "Download this model" action inline in the
   model selector when a model is shown as not downloaded? This would require a new admin
   endpoint to trigger model pre-download.
