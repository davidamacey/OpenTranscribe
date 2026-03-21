# Implementation Plan: Disable Speaker Diarization Option
**GitHub Issue:** #151 — "[FEATURE] Option to disable speaker diarization"
**Target Release:** 0.4.0
**Estimated Complexity:** Medium
**Author:** Claude Code
**Date:** 2026-03-19

---

## 1. Overview

Add a toggle to skip PyAnnote speaker diarization entirely. This serves recordings known to have a single speaker (voicemails, dictations, podcasts with one host, etc.) where diarization incorrectly splits audio into phantom speakers, producing a degraded transcript.

When disabled, every transcript segment is assigned a single canonical speaker (`SPEAKER_00`). The transcription itself is unaffected; only the speaker-separation step is skipped.

### User-facing options
| Surface | Scope | When available |
|---------|-------|----------------|
| Settings → Transcription | Per-user default | Always |
| File Upload dialog (advanced) | Per-file override | Always |
| URL download dialog | Per-file override | Always |
| Selective Reprocess modal | Per-file override | When reprocessing |
| Bulk action panel | Per-batch override | Bulk reprocess |

---

## 2. Current Behavior Analysis

### Pipeline overview
```
Upload/URL → dispatch_transcription_pipeline()
               └─ CPU: preprocess_for_transcription   (download, audio extract, WAV)
               └─ GPU: transcribe_gpu_task             (WhisperX + PyAnnote + speaker assign)
               └─ CPU: finalize_transcription          (native embeddings → COMPLETED)
                         └─ enrich_and_dispatch        (search index, summarize, cluster, attrs)
```

### Where diarization is called (the critical path)
`backend/app/transcription/pipeline.py:136` — `TranscriptionPipeline.process()`:
```python
diarizer = self.manager.get_diarizer(self.config)
diarize_df, overlap_info, native_embeddings = diarizer.diarize(audio)
```
This is **always executed** — there is no conditional check. It runs on the GPU worker.

### What diarization produces
1. `diarize_df` — DataFrame mapping time windows → `SPEAKER_XX` labels
2. `overlap_info` — overlapping speech regions (used to mark segments)
3. `native_embeddings` — 256-dim WeSpeaker centroids per speaker (used for profile matching)

### Downstream consumers of diarization output
| Component | File | What it does with diarization output |
|-----------|------|--------------------------------------|
| `assign_speakers()` | `transcription/speaker_assigner.py` | Maps WhisperX segments to speaker labels using `diarize_df` |
| `extract_unique_speakers()` | `tasks/transcription/speaker_processor.py` | Extracts set of unique speaker labels from segments |
| `create_speaker_mapping()` | `tasks/transcription/speaker_processor.py` | Creates DB `Speaker` rows per unique label |
| `process_segments_with_speakers()` | same | Enriches segments with DB speaker_id FK |
| `mark_overlapping_segments()` | same | Marks segments within overlap regions |
| `_process_speaker_embeddings_native()` / `_process_speaker_embeddings()` | `core.py` | Matches speakers to `SpeakerProfile` via embeddings |
| `_store_native_centroids_in_v4_staging()` | `core.py` | Stores centroids in OpenSearch `speakers_v4` index |
| `cluster_speakers_for_file` | `tasks/speaker_clustering.py` | Clusters speakers cross-file |
| `detect_speaker_attributes_task` | `tasks/speaker_attribute_task.py` | Gender/age detection per speaker |

### Configuration touch points
- `TranscriptionConfig` (`transcription/config.py`): `min_speakers`, `max_speakers`, `num_speakers`
- `_get_user_transcription_settings()` (`tasks/transcription/core.py`): reads `UserSetting` keys for speaker ranges
- `dispatch_transcription_pipeline()` (`tasks/transcription/dispatch.py`): accepts speaker params, builds chain
- `preprocess_for_transcription()` (`tasks/transcription/preprocess.py`): forwards speaker params in context dict to GPU task

### Retry / re-queue behavior
`management.py:retry_file_processing()` calls `dispatch_transcription_pipeline(file_uuid=file_uuid)` with **no speaker parameters** — it only passes the file UUID. This is important: if the file originally had diarization disabled, a retry must preserve that intent. The solution is to persist `diarization_disabled` on the `MediaFile` row and read it back on retry.

---

## 3. Database Changes

### 3a. New `MediaFile` column

Add a boolean column to track whether diarization was disabled for a given file. This enables:
- Correct retry behavior (reads flag from DB, no user re-input needed)
- Accurate provenance in metadata display
- Future analytics/filtering ("files without diarization")

**File:** `backend/app/models/media.py`

Add after the `diarization_provider` column (~line 117):
```python
diarization_disabled = Column(Boolean, nullable=False, default=False,
    server_default="false")  # True when user explicitly skipped diarization
```

### 3b. Alembic migration

**File:** `backend/alembic/versions/v350_add_diarization_disabled.py`

```python
"""Add diarization_disabled flag to media_file.

Revision ID: v350_add_diarization_disabled
Revises: v340_add_user_media_sources
Create Date: 2026-03-XX
"""
from alembic import op

revision = "v350_add_diarization_disabled"
down_revision = "v340_add_user_media_sources"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'media_file'
                  AND column_name = 'diarization_disabled'
            ) THEN
                ALTER TABLE media_file
                    ADD COLUMN diarization_disabled BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
        END $$;
    """)


def downgrade():
    op.execute(
        'ALTER TABLE media_file DROP COLUMN IF EXISTS diarization_disabled'
    )
```

**Also update** `backend/app/db/migrations.py` detection logic to include this version in the migration chain check.

### 3c. UserSetting key (no migration needed)

The `user_setting` table is a key-value store. A new setting key requires no migration.

| Setting key | Type (stored as string) | Default | Meaning |
|-------------|------------------------|---------|---------|
| `transcription_disable_diarization` | `"true"` / `"false"` | `"false"` | User's default preference |

---

## 4. Backend Changes

### 4a. `TranscriptionConfig` — add `enable_diarization` field

**File:** `backend/app/transcription/config.py`

Add to the `TranscriptionConfig` dataclass:
```python
enable_diarization: bool = True   # Set False to skip PyAnnote entirely
```

In `from_environment()`, read from env override (optional, for ops use):
```python
enable_diarization=os.getenv("ENABLE_DIARIZATION", "true").lower() == "true",
```
Task-level overrides (via `setattr`) will override this when the pipeline sets it per-file.

### 4b. `TranscriptionPipeline.process()` — conditional diarization

**File:** `backend/app/transcription/pipeline.py`

Replace the unconditional diarization block (steps 3–6) with:

```python
if self.config.enable_diarization:
    # Step 3: Load diarizer (existing logic)
    ...
    # Step 4: Diarize with PyAnnote v4 (existing logic)
    diarizer = self.manager.get_diarizer(self.config)
    diarize_df, overlap_info, native_embeddings = diarizer.diarize(audio)
    ...
    # Step 5: Segment dedup (existing logic)
    # Step 6: Assign speakers (existing logic)
    result = assign_speakers(diarize_df, transcript)
    if overlap_info.get("count", 0) > 0:
        result["overlap_info"] = overlap_info
    if native_embeddings:
        result["native_speaker_embeddings"] = native_embeddings
else:
    # Diarization disabled: assign single speaker to all segments
    logger.info("Diarization disabled — assigning SPEAKER_00 to all segments")
    if self.config.enable_dedup:
        from app.utils.segment_dedup import clean_segments
        transcript["segments"] = clean_segments(transcript["segments"])
    for seg in transcript.get("segments", []):
        seg["speaker"] = "SPEAKER_00"
        for word in seg.get("words", []):
            word["speaker"] = "SPEAKER_00"
    result = transcript
    overlap_info = {"count": 0, "duration": 0.0, "regions": []}
    native_embeddings = None
```

This ensures the return dict shape is identical whether diarization ran or not.

Note: when `enable_diarization=False`, the `ModelManager` should **not** load the diarizer model. The `get_diarizer()` call is the expensive one (~10–40s). Skipping it frees significant VRAM.

### 4c. `_get_user_transcription_settings()` — read the new setting

**File:** `backend/app/tasks/transcription/core.py`

In `_get_user_transcription_settings()`, add `"transcription_disable_diarization"` to the `setting_keys` list and return it:

```python
setting_keys = [
    ...existing keys...,
    "transcription_disable_diarization",
]

return {
    ...existing keys...,
    "disable_diarization": settings_map.get(
        "transcription_disable_diarization", "false"
    ).lower() == "true",
}
```

### 4d. `_run_transcription_pipeline()` — pass `disable_diarization` to config

**File:** `backend/app/tasks/transcription/core.py`

In `_run_transcription_pipeline()`, add `disable_diarization` as a parameter and include it in the overrides dict:

```python
def _run_transcription_pipeline(
    ctx,
    audio_file_path,
    min_speakers, max_speakers, num_speakers,
    source_language=None,
    translate_to_english=None,
    disable_diarization=False,   # NEW
) -> dict:
    ...
    overrides: dict = dict(
        ...existing overrides...,
        enable_diarization=not disable_diarization,   # NEW
    )
```

### 4e. `transcribe_gpu_task` context dict — propagate the flag

**File:** `backend/app/tasks/transcription/core.py`

The `transcribe_gpu_task` receives the context dict produced by `preprocess_for_transcription`. Add `disable_diarization` to the context read:

```python
disable_diarization = context.get("disable_diarization", False)
```

Pass it to `_run_transcription_pipeline()`.

### 4f. `update_media_file_transcription_status()` — record disabled state

**File:** `backend/app/tasks/transcription/storage.py`

Add `diarization_disabled: bool = False` parameter to this function. When `True`:
- Set `media_file.diarization_model = None` (or the string `"disabled"` for clarity)
- Set `media_file.diarization_disabled = True`

### 4g. Skip speaker embeddings when diarization disabled

**File:** `backend/app/tasks/transcription/core.py` — `_run_post_gpu_background()`

Add a guard before the speaker embedding block:

```python
if not result.get("diarization_disabled", False):
    _run_speaker_embeddings_with_retry(...)
    if native_embeddings_for_v4 and not _should_use_native_embeddings(result):
        _store_native_centroids_in_v4_staging(...)
```

When diarization is disabled, skip embedding extraction and profile matching — there is only one speaker and no useful embedding to compute from a diarization run.

### 4h. `finalize_transcription()` (postprocess) — skip native embedding processing

**File:** `backend/app/tasks/transcription/postprocess.py`

```python
use_native = gpu_result.get("use_native_embeddings", False)
diarization_disabled = gpu_result.get("diarization_disabled", False)

if use_native and native_embeddings and not diarization_disabled:
    _process_native_embeddings(...)
```

### 4i. `enrich_and_dispatch()` — skip clustering for single-speaker files

**File:** `backend/app/tasks/transcription/postprocess.py`

```python
def _dispatch_speaker_clustering(file_uuid, user_id, downstream_tasks):
    # Skip clustering for single-speaker files (trivial, no cross-file value)
    if downstream_tasks is not None and "speaker_clustering" in downstream_tasks:
        return
    ...
    # Existing dispatch — the cluster task itself handles 1-speaker case gracefully
```

Speaker attribute detection (gender/age) should **still run** for single-speaker files — it is useful and the task already handles 1-speaker correctly.

### 4j. `rediarize_task` — update `diarization_disabled` flag after re-diarization

**File:** `backend/app/tasks/rediarize_task.py`

When rediarization completes successfully, set `media_file.diarization_disabled = False` in the finalization step:

```python
with session_scope() as db:
    media_file = get_file_by_uuid(db, file_uuid)
    if media_file:
        media_file.diarization_disabled = False
    update_task_status(db, task_id, "completed", ...)
    update_media_file_status(db, file_id, FileStatus.COMPLETED)
```

This means: a user who uploaded with diarization disabled can later run "Re-diarize" from the Selective Reprocess modal to retroactively add speaker separation. After rediarization, the file is no longer marked as diarization-disabled.

---

## 5. Dispatch Layer Changes

### 5a. `dispatch_transcription_pipeline()`

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
    disable_diarization: bool | None = None,   # NEW — None = read from user settings
) -> str:
```

When `disable_diarization is None`, the value is resolved from the user's `UserSetting` inside `preprocess_for_transcription` (same pattern as min/max speakers). When explicitly passed as `True` or `False`, it overrides the user setting.

Pass it through to `preprocess_for_transcription.s(... disable_diarization=disable_diarization)`.

### 5b. `dispatch_batch_transcription()`

Add the same `disable_diarization` parameter and forward it to each per-file chain's preprocess task.

### 5c. `preprocess_for_transcription()` — accept, resolve, and forward flag

**File:** `backend/app/tasks/transcription/preprocess.py`

```python
def preprocess_for_transcription(
    self,
    file_uuid: str,
    task_id: str,
    ...,
    disable_diarization: bool | None = None,   # NEW
) -> dict:
```

Resolution logic inside the task (mirrors `_get_user_transcription_settings` pattern):
```python
# Resolve disable_diarization: explicit arg > user DB setting
if disable_diarization is None:
    with session_scope() as db:
        user_settings = _get_user_transcription_settings(db, user_id)
        disable_diarization = user_settings["disable_diarization"]
```

Return it in the context dict:
```python
return {
    ...existing keys...,
    "disable_diarization": disable_diarization,
}
```

### 5d. `transcribe_gpu_task` — read and forward flag, persist to MediaFile

**File:** `backend/app/tasks/transcription/core.py`

```python
disable_diarization = context.get("disable_diarization", False)

# Persist diarization_disabled on MediaFile before running pipeline
with session_scope() as db:
    media_file = get_refreshed_object(db, MediaFile, ctx.file_id)
    if media_file:
        media_file.diarization_disabled = disable_diarization
        db.commit()
```

Pass `disable_diarization` down to `_run_transcription_pipeline()`.

In the GPU result dict sent to postprocess, include:
```python
gpu_result = {
    ...existing keys...,
    "diarization_disabled": disable_diarization,
}
```

---

## 6. API Endpoint Changes

### 6a. User settings endpoints

**File:** `backend/app/api/endpoints/user_settings.py`

Add `disable_diarization` to the `DEFAULT_TRANSCRIPTION_SETTINGS` dict:
```python
DEFAULT_TRANSCRIPTION_SETTINGS = {
    ...existing...,
    "disable_diarization": False,
}
```

In the GET transcription settings handler, read and return:
```python
"disable_diarization": settings_map.get(
    "transcription_disable_diarization", "false"
).lower() == "true"
```

In the PUT transcription settings handler, save when provided:
```python
if update.disable_diarization is not None:
    upsert_user_setting(db, user_id,
        "transcription_disable_diarization",
        str(update.disable_diarization).lower())
```

### 6b. `TranscriptionSettings` schema

**File:** `backend/app/schemas/transcription_settings.py`

```python
class TranscriptionSettings(BaseModel):
    ...
    disable_diarization: bool = Field(
        default=False,
        description="Skip speaker diarization entirely; all segments assigned to a single speaker",
    )

class TranscriptionSettingsUpdate(BaseModel):
    ...
    disable_diarization: Optional[bool] = Field(
        default=None,
        description="Skip speaker diarization entirely",
    )

class TranscriptionSystemDefaults(BaseModel):
    ...
    disable_diarization_default: bool = Field(
        default=False,
        description="System default for disable_diarization",
    )
```

### 6c. File upload endpoint

**File:** `backend/app/api/endpoints/files/crud.py` (the main upload route)

Add query/body parameter `disable_diarization: bool = False` and pass it to `start_transcription_task()`, which passes it to `dispatch_transcription_pipeline()`.

### 6d. URL processing endpoint

**File:** `backend/app/api/endpoints/files/url_processing.py`

Add `disable_diarization: bool = False` to `URLProcessingRequest` model and pass it through to the youtube processing task, which must in turn pass it to the transcription pipeline.

**File:** `backend/app/tasks/youtube_processing.py`

The `process_youtube_url_task` eventually calls `dispatch_transcription_pipeline()`. Add `disable_diarization` parameter to the task and forward it.

### 6e. Reprocess endpoint (`start_reprocessing_task`)

**File:** `backend/app/api/endpoints/files/reprocess.py`

```python
def start_reprocessing_task(
    file_uuid: str,
    min_speakers=None, max_speakers=None, num_speakers=None,
    downstream_tasks=None,
    user_id=None, db=None,
    disable_diarization: bool | None = None,  # NEW — None = read from user/file default
) -> None:
    dispatch_transcription_pipeline(
        ...,
        disable_diarization=disable_diarization,
    )
```

### 6f. Retry endpoint

**File:** `backend/app/api/endpoints/files/management.py`

In `retry_file_processing()`, before calling `dispatch_transcription_pipeline()`, read the stored flag:
```python
# Preserve the diarization setting from the original processing run
disable_diarization = bool(db_file.diarization_disabled)

task_id = dispatch_transcription_pipeline(
    file_uuid=file_uuid,
    disable_diarization=disable_diarization,
)
```

This ensures a file that was originally processed without diarization retries without diarization.

### 6g. Bulk action endpoint

**File:** `backend/app/api/endpoints/files/management.py`

`BulkActionRequest` already has `min_speakers`, `max_speakers`, `num_speakers` fields. Add:
```python
disable_diarization: Optional[bool] = None
```

In the bulk reprocess handler, pass `disable_diarization` to `start_reprocessing_task()` for each file.

### 6h. MediaFile schema — expose `diarization_disabled`

**File:** `backend/app/schemas/media.py`

Add to the `MediaFile` response schema:
```python
diarization_disabled: bool = Field(default=False)
diarization_model: Optional[str] = None
```

This allows the frontend to show diarization status in the file metadata display.

---

## 7. Frontend Changes

### 7a. `TranscriptionSettings.svelte`

**File:** `frontend/src/components/settings/TranscriptionSettings.svelte`

Add a "Speaker Detection" section with the new toggle above the existing min/max speaker fields. The toggle should:
- Default to `false` (diarization enabled)
- When `true`: dim/disable the min/max speaker inputs (they become irrelevant)
- Show a brief explanation: "For voicemails, dictations, or recordings with a single speaker. Skips speaker separation to improve accuracy and speed."
- Be part of the dirty-state tracking and save/reset flow

```svelte
let disableDiarization = false;
let originalDisableDiarization = false;

$: settingsChanged = ... || disableDiarization !== originalDisableDiarization;
```

### 7b. `FileUploader.svelte`

**File:** `frontend/src/components/FileUploader.svelte`

In the Advanced Settings panel, add a "Single speaker / No diarization" toggle:
- Positioned above the min/max speaker inputs
- When checked: dim the speaker count inputs
- Pre-populated from the user's saved preference (`transcriptionSettings.disable_diarization`)
- Respect the `speaker_prompt_behavior` setting (if `use_defaults`, it should still be overrideable per-file)
- Passed as `disable_diarization` in the upload request body or query param

The upload API call should include:
```typescript
formData.append('disable_diarization', String(disableDiarization));
```

Or if the endpoint takes a JSON body for metadata, include it there.

### 7c. `SelectiveReprocessModal.svelte`

**File:** `frontend/src/components/SelectiveReprocessModal.svelte`

When `selectedStages` includes `'transcription'`, show a "Diarization" subsection in the Settings step:
```
[ ] Disable speaker diarization
    Skip speaker separation for single-speaker recordings.
```

The `showSpeakerSettings` computed value (`selectedStages.has('transcription') || selectedStages.has('rediarize')`) already controls whether the settings step appears — diarization toggle should appear alongside min/max speakers when transcription is selected.

Pass `disable_diarization` in the reprocess request body.

### 7d. `BulkAudioExtractionModal.svelte` / bulk upload flow

For bulk uploads, add the same toggle to the bulk upload modal with a "Apply to all files" label.

### 7e. `MetadataDisplay.svelte`

**File:** `frontend/src/components/MetadataDisplay.svelte`

In the processing details section, add a "Speaker Analysis" row:
- When `diarization_disabled = true`: show "Disabled (single speaker mode)"
- When `diarization_disabled = false` and `diarization_model` is set: show the model name

### 7f. `$lib/api/transcriptionSettings.ts`

**File:** `frontend/src/lib/api/transcriptionSettings.ts`

Add to the `TranscriptionSettings` interface:
```typescript
export interface TranscriptionSettings {
  ...existing fields...
  disable_diarization: boolean;
}

export const DEFAULT_TRANSCRIPTION_SETTINGS: TranscriptionSettings = {
  ...existing defaults...
  disable_diarization: false,
};
```

Add to `TranscriptionSettingsUpdate`:
```typescript
export interface TranscriptionSettingsUpdate {
  ...existing fields...
  disable_diarization?: boolean;
}
```

### 7g. i18n translation keys

All 7 locale files (`en`, `es`, `fr`, `de`, `pt`, `zh`, `ja`) need these keys added:

```json
"settings": {
  "transcription": {
    "disableDiarization": "Disable speaker diarization",
    "disableDiarizationDesc": "Skip speaker separation. Use for voicemails, dictations, or single-speaker recordings.",
    "disableDiarizationWarning": "Speaker profiles and cross-file speaker matching will not run.",
    "speakerDetectionDisabled": "Speaker detection disabled"
  }
},
"uploader": {
  "singleSpeaker": "Single speaker (no diarization)",
  "singleSpeakerDesc": "Faster processing. Use for voicemails, dictations, lectures."
},
"metadata": {
  "diarizationDisabled": "Disabled (single speaker mode)",
  "diarizationModel": "Diarization model"
}
```

**Note:** Translation values for non-English locales should be written by a native speaker or reviewed — the English keys above are the authoritative source.

---

## 8. Edge Cases and Compatibility

### 8a. Retry behavior
A file that was uploaded with diarization disabled stores `diarization_disabled=True` on the `MediaFile` row. The retry endpoint reads this flag and passes it to `dispatch_transcription_pipeline`. If the user wants to retry WITH diarization (e.g., they changed their mind after the file errored), they should use "Selective Reprocess → Transcription" and uncheck the toggle, not the retry button. The retry button is intended to retry the same configuration.

### 8b. Existing transcriptions
All existing `MediaFile` rows get `diarization_disabled=False` via the migration's `DEFAULT FALSE`. This is correct — they were processed with diarization.

### 8c. Rediarization as an upgrade path
A user who uploaded a voicemail with diarization disabled later realizes the recording actually had two voices. They can use Selective Reprocess → Re-diarize to retroactively add speaker separation without re-transcribing. After `rediarize_task` completes, `diarization_disabled` is set to `False`.

### 8d. Cloud ASR providers (Deepgram, AssemblyAI, etc.)
Cloud ASR providers do not use PyAnnote. Their results already go through `extract_unique_speakers()` with a fallback to `SPEAKER_00` when the provider doesn't return speaker labels. The `disable_diarization` flag must also gate the PyAnnote step specifically — it should NOT affect whether cloud ASR providers return diarization data from their own systems.

**Recommended approach:** `disable_diarization` only controls the local PyAnnote step. When using cloud ASR, the flag is ignored (cloud providers handle their own diarization). Alternatively, the UI can show a note: "Diarization is handled by your cloud ASR provider and cannot be disabled separately."

### 8e. `num_speakers=1` vs `disable_diarization=True`
Currently users can set `num_speakers=1` in the advanced settings, which technically forces diarization to produce a single speaker. However this is different:
- `num_speakers=1` still runs PyAnnote (wastes GPU time, may still produce artifacts)
- `disable_diarization=True` skips PyAnnote entirely (faster, no phantom speaker from the model)

Both should be supported. The new toggle is the better choice for known single-speaker files.

### 8f. Speaker attribute detection with single speaker
When diarization is disabled, there is still a `SPEAKER_00` DB row. The `detect_speaker_attributes_task` runs against each speaker of the file and will still detect gender/age for `SPEAKER_00`. This is useful (e.g., voicemail from a known speaker). Do NOT skip this task.

### 8g. LLM speaker identification
The LLM identification task (`identify_speakers_llm_task`) will run on the single `SPEAKER_00`. It may suggest a name for the speaker based on context clues in the transcript (e.g., "Hi, this is John calling..."). This is useful — do NOT skip.

### 8h. Speaker clustering
With a single speaker per file, `cluster_speakers_for_file` will produce a trivial cluster. The task handles this gracefully (1-speaker files simply do not generate cross-file cluster groupings). Continue dispatching it — the overhead is negligible and it simplifies the dispatch logic.

### 8i. OpenSearch search indexing
Unaffected. Transcripts are indexed regardless of diarization state.

### 8j. Analytics task
Unaffected. Analytics (word count, speaking time) work on transcript segments regardless of speaker count.

### 8k. Summary generation
Unaffected. The LLM summary works with 1-speaker transcripts. The BLUF summary format still works — there just won't be a multi-speaker breakdown.

### 8l. `waveform_data` and overlap detection
`overlap_info` will be empty (`{"count": 0, "duration": 0.0, "regions": []}`). The `mark_overlapping_segments()` call in `_process_transcription_result()` already handles empty `overlap_regions` gracefully (returns segments unchanged).

### 8m. `speaker_prompt_behavior` interaction
When `disable_diarization=True`, the `speaker_prompt_behavior` ("always_prompt", "use_defaults", "use_custom") becomes irrelevant. The frontend should:
- Hide/disable the speaker count controls when the diarization toggle is on
- Not send min/max speaker values with the request (they are ignored by the backend anyway, but cleaner UX)

### 8n. API backward compatibility
All new parameters are optional with default values that preserve current behavior:
- `disable_diarization=False` (or `None`→reads user setting→default `false`)

Existing API clients that don't send this parameter get current behavior. No breaking change.

### 8o. Waveform generation
Waveform generation (`generate_waveform_task`) runs in parallel with the transcription pipeline and is unaffected.

### 8p. `ENABLE_DIARIZATION` env var (system-wide)
While implementing the per-user/per-file toggle, also support an env var `ENABLE_DIARIZATION=false` that disables diarization system-wide (useful for resource-constrained deployments without a HuggingFace token). This is already partially supported by the `TranscriptionConfig.from_environment()` approach. The per-file/per-user setting then becomes an additional control on top.

Resolution order for `enable_diarization`:
1. Per-file explicit flag (from API request, highest priority)
2. User's saved setting (`transcription_disable_diarization`)
3. `ENABLE_DIARIZATION` env var (system-wide override)
4. Default: `True` (diarization enabled)

---

## 9. Testing Strategy

### 9a. Unit tests

**File:** `backend/tests/unit/test_transcription_pipeline.py`

- `test_pipeline_diarization_disabled_assigns_speaker_00`: Mock WhisperX result, set `enable_diarization=False`, assert all segments have `speaker="SPEAKER_00"`, no overlap_info, no native_embeddings.
- `test_pipeline_diarization_disabled_skips_diarizer_load`: Assert `ModelManager.get_diarizer()` is NOT called when `enable_diarization=False`.
- `test_transcription_config_enable_diarization_default_true`: `TranscriptionConfig()` has `enable_diarization=True`.
- `test_transcription_config_env_override`: `ENABLE_DIARIZATION=false` env sets `enable_diarization=False`.

**File:** `backend/tests/unit/test_user_settings.py`

- `test_disable_diarization_setting_saved`: PUT `/api/settings/transcription` with `disable_diarization=true` saves the key.
- `test_disable_diarization_setting_read`: GET `/api/settings/transcription` returns `disable_diarization=true` after saving.
- `test_disable_diarization_default_false`: New user gets `disable_diarization=false`.

### 9b. Integration tests

**File:** `backend/tests/integration/test_transcription_pipeline.py`

- `test_full_pipeline_diarization_disabled`: Upload a file with `disable_diarization=True`, assert:
  - MediaFile.diarization_disabled == True
  - MediaFile.diarization_model is None
  - All TranscriptSegments have speaker.name == "SPEAKER_00"
  - Exactly one Speaker row for the file
  - No speaker embeddings in OpenSearch for this file
- `test_retry_preserves_diarization_disabled`: Upload with disabled, simulate error, retry, assert diarization_disabled still True.
- `test_rediarize_clears_diarization_disabled`: Upload with disabled, run rediarize, assert diarization_disabled becomes False.

### 9c. API tests

- `test_upload_with_disable_diarization_param`: POST `/files/upload` with `disable_diarization=true`, assert pipeline receives flag.
- `test_reprocess_with_disable_diarization`: POST `/files/{uuid}/reprocess` with selective stages + `disable_diarization=true`.
- `test_bulk_reprocess_with_disable_diarization`: POST bulk action with `disable_diarization=true`.

### 9d. Frontend tests (svelte-check / playwright)

- `TranscriptionSettings.svelte`: Toggle appears, changes dirty state, saves correctly.
- `FileUploader.svelte`: Toggle pre-populated from user settings, overrides work, speaker inputs dim when toggle on.
- `SelectiveReprocessModal.svelte`: Toggle appears in settings step when transcription stage selected.

---

## 10. Implementation Order (Phases)

### Phase 1: Foundation (no breaking changes)
1. Add `diarization_disabled` column to `MediaFile` — Alembic migration `v350`
2. Update `MediaFile` SQLAlchemy model
3. Update `TranscriptionConfig` dataclass with `enable_diarization: bool = True`
4. Update `TranscriptionPipeline.process()` with conditional diarization
5. Add `disable_diarization` to `TranscriptionSettings` schema (Pydantic)
6. Update user settings GET/PUT endpoints to read/write the new setting key

### Phase 2: Pipeline propagation
7. Update `_get_user_transcription_settings()` to read `transcription_disable_diarization`
8. Update `_run_transcription_pipeline()` to accept and pass `enable_diarization`
9. Update `preprocess_for_transcription()` to accept, resolve (from user settings when `None`), and forward `disable_diarization`
10. Update `dispatch_transcription_pipeline()` and `dispatch_batch_transcription()` with new param
11. Update `transcribe_gpu_task` to read context dict flag, persist to DB, and pass to pipeline
12. Update `finalize_transcription()` postprocess to skip embedding processing when disabled

### Phase 3: API surface
13. Upload endpoint: add `disable_diarization` parameter
14. URL processing endpoint + youtube task: add parameter
15. Reprocess endpoint: add parameter
16. Retry endpoint: read from `MediaFile.diarization_disabled`
17. Bulk action endpoint: add parameter to `BulkActionRequest`
18. MediaFile response schema: expose `diarization_disabled` field

### Phase 4: Rediarization
19. Update `rediarize_task` to set `diarization_disabled=False` on completion

### Phase 5: Frontend
20. Add `disable_diarization` to `$lib/api/transcriptionSettings.ts` type definitions
21. Update `TranscriptionSettings.svelte` with toggle
22. Update `FileUploader.svelte` with per-file toggle
23. Update `SelectiveReprocessModal.svelte` with toggle in settings step
24. Update `MetadataDisplay.svelte` to show diarization status
25. Add i18n keys to all 7 locale files

### Phase 6: Testing & verification
26. Write unit tests for pipeline and user settings
27. Write integration tests for full flow
28. Manual end-to-end test: upload voicemail → verify single speaker, verify speed improvement
29. Verify retry preserves flag
30. Verify rediarize clears flag

---

## 11. File Summary

| File | Change type | Notes |
|------|-------------|-------|
| `backend/alembic/versions/v350_add_diarization_disabled.py` | **New** | Migration for `media_file.diarization_disabled` |
| `backend/app/db/migrations.py` | **Modify** | Add v350 detection |
| `backend/app/models/media.py` | **Modify** | Add `diarization_disabled` column |
| `backend/app/transcription/config.py` | **Modify** | Add `enable_diarization` field |
| `backend/app/transcription/pipeline.py` | **Modify** | Conditional diarization block |
| `backend/app/schemas/transcription_settings.py` | **Modify** | Add `disable_diarization` field |
| `backend/app/api/endpoints/user_settings.py` | **Modify** | GET/PUT new setting key |
| `backend/app/tasks/transcription/core.py` | **Modify** | `_get_user_transcription_settings`, `_run_transcription_pipeline`, `transcribe_gpu_task`, `_run_post_gpu_background` |
| `backend/app/tasks/transcription/preprocess.py` | **Modify** | Accept/resolve/forward flag |
| `backend/app/tasks/transcription/dispatch.py` | **Modify** | New param on both dispatch functions |
| `backend/app/tasks/transcription/postprocess.py` | **Modify** | Skip embeddings when disabled |
| `backend/app/tasks/transcription/storage.py` | **Modify** | `update_media_file_transcription_status` writes disabled state |
| `backend/app/tasks/rediarize_task.py` | **Modify** | Clear flag on completion |
| `backend/app/tasks/youtube_processing.py` | **Modify** | Forward flag to pipeline |
| `backend/app/api/endpoints/files/upload.py` | **Modify** | New param → `start_transcription_task` |
| `backend/app/api/endpoints/files/url_processing.py` | **Modify** | New param in request model |
| `backend/app/api/endpoints/files/reprocess.py` | **Modify** | New param in `start_reprocessing_task` |
| `backend/app/api/endpoints/files/management.py` | **Modify** | Retry reads DB, bulk adds param |
| `backend/app/schemas/media.py` | **Modify** | Expose `diarization_disabled` in response |
| `frontend/src/lib/api/transcriptionSettings.ts` | **Modify** | Add field to interfaces |
| `frontend/src/components/settings/TranscriptionSettings.svelte` | **Modify** | Add toggle |
| `frontend/src/components/FileUploader.svelte` | **Modify** | Add per-file toggle |
| `frontend/src/components/SelectiveReprocessModal.svelte` | **Modify** | Add toggle in settings step |
| `frontend/src/components/MetadataDisplay.svelte` | **Modify** | Show diarization status |
| `frontend/src/lib/i18n/locales/en.json` (+ 6 others) | **Modify** | New i18n keys |
