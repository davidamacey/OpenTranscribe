# Implementation Plan: Issue #152 — Option to Disable AI Summary Generation

**Issue**: [#152 — \[FEATURE\] Option to disable AI summary generation](https://github.com/davidamacey/OpenTranscribe/issues/152)
**Reporter**: it-service-gemag
**Target Release**: 0.4.0
**Plan Author**: Claude Code (claude-sonnet-4-6)
**Date**: 2026-03-19

---

## Table of Contents

1. [Overview](#1-overview)
2. [Current Behavior Analysis](#2-current-behavior-analysis)
3. [Proposed Design](#3-proposed-design)
4. [Database Changes](#4-database-changes)
5. [Backend Changes](#5-backend-changes)
6. [Frontend Changes](#6-frontend-changes)
7. [Edge Cases](#7-edge-cases)
8. [Compatibility Concerns](#8-compatibility-concerns)
9. [Testing Strategy](#9-testing-strategy)
10. [Implementation Phases](#10-implementation-phases)

---

## 1. Overview

The user (it-service-gemag) requires a dedicated flag to disable AI summary generation without removing the LLM provider configuration. Primary use cases:

- **Bulk voicemail processing**: Hundreds of short recordings where summaries add cost and latency with no value.
- **CRM integrations**: Pipeline consumes transcripts programmatically; summaries are unused.
- **Cost optimization**: Cloud LLM API costs (OpenAI, Anthropic, etc.) should be controlled, not incurred automatically.

The key constraint: users still want LLM features (speaker ID suggestions, topic extraction, custom prompts) — they just don't want the post-transcription summary auto-dispatched for every file.

### Solution Summary

Implement a **three-tier control model**:

| Tier | Scope | Who Controls | Mechanism |
|------|-------|-------------|-----------|
| **System-level** | All users | Admin | `system_settings` key `ai.summary_enabled` |
| **User-level** | One user's files | User | `user_setting` key `ai_summary_enabled` |
| **Per-file** | Single upload | User at upload time | `skip_summary` flag in upload/URL API request |

Precedence (highest to lowest): **System → User → Per-file**

---

## 2. Current Behavior Analysis

### 2.1 Pipeline Flow

After transcription completes, the 3-stage pipeline chain triggers background enrichment:

```
GPU transcription → postprocess.py finalize_transcription()
  → enrich_and_dispatch() [Celery task]
      → _index_transcript()                 # search indexing
      → trigger_automatic_summarization()   # ← summary dispatch lives here
      → _dispatch_speaker_attributes()
      → _dispatch_speaker_clustering()
```

**Key file**: `backend/app/tasks/transcription/core.py:1162` — `trigger_automatic_summarization()`

```python
def trigger_automatic_summarization(
    file_id: int, file_uuid: str, tasks_to_run: list[str] | None = None
):
    # tasks_to_run=None means "run everything"
    if tasks_to_run is None or "summarization" in tasks_to_run:
        summary_task = summarize_transcript_task.delay(file_uuid=file_uuid, ...)
```

This function is also called from `postprocess.py:220` via `enrich_and_dispatch`.

### 2.2 The Summarization Task

`backend/app/tasks/summarization.py` — `summarize_transcript_task` (Celery task `ai.generate_summary`):

1. Fetches `MediaFile` from DB by UUID
2. Loads `LLMService` from user settings (falls back to system settings)
3. If no LLM configured → sets `summary_status = "not_configured"`, returns early
4. Builds full transcript text + speaker stats
5. Calls `llm_service.generate_summary()`
6. Stores result in both PostgreSQL (`media_file.summary_data` JSONB) and OpenSearch (`summary_opensearch_id`)
7. Sends WebSocket notification to frontend

### 2.3 LLM Service Architecture

`backend/app/services/llm_service.py` — Providers: `openai`, `vllm`, `ollama`, `anthropic`, `openrouter`, `custom`.

- **User-level config**: `user_llm_settings` table — each user has one or more named LLM configs; the active one is tracked via `user_setting` key `active_llm_config_id`.
- **System-level fallback**: `.env` vars (`LLM_PROVIDER`, `VLLM_BASE_URL`, etc.) used when user has no personal config.
- `LLMService.create_from_user_settings(user_id)` → tries user config first, falls back to system.

### 2.4 Existing `summary_status` Values

Column `media_file.summary_status` (VARCHAR, nullable):

| Value | Meaning |
|-------|---------|
| `null` / `"pending"` | Not yet generated; awaiting dispatch |
| `"processing"` | Celery task is actively running |
| `"completed"` | Summary stored in OpenSearch/PostgreSQL |
| `"failed"` | Task error; retryable |
| `"not_configured"` | LLM provider not configured; non-retryable until configured |

**Gap**: No value for "intentionally disabled." This is what we add.

### 2.5 Manual Trigger API

`POST /api/files/{file_uuid}/summarize` in `backend/app/api/endpoints/summarization.py`:
- Checks LLM availability
- Dispatches `summarize_transcript_task` directly
- Users use this to re-generate or generate for the first time on demand

### 2.6 Reprocess / Selective Reprocess

`backend/app/api/endpoints/files/reprocess.py` — `process_file_reprocess()`:
- Accepts `stages: list[str]` — if `"summarization"` is in the list, it clears and re-runs summary
- This already gives power users granular control per-file

### 2.7 Retry Mechanism

`POST /api/files/{file_uuid}/retry-summary` in `backend/app/api/endpoints/files/summary_status.py`:
- Only works if `summary_status == "failed"` and LLM is available

### 2.8 `UserSetting` Model

`backend/app/models/prompt.py` — `UserSetting` table (`user_setting`):
- Key-value store per user: `setting_key` (VARCHAR 100) + `setting_value` (TEXT)
- No migration needed to add new keys — the schema is already flexible
- Existing keys include: `transcription_source_language`, `llm_output_language`, `org_context_text`, `active_llm_config_id`, etc.

### 2.9 `SystemSettings` Model

`backend/app/models/system_settings.py` — `SystemSettings` table (`system_settings`):
- Global key-value store: `key` + `value`
- Existing keys include: `search.embedding_model`, ASR settings, retry limits, etc.

---

## 3. Proposed Design

### 3.1 Three-Tier Control Model

```
trigger_automatic_summarization() called after transcription
    │
    ▼
1. Check system_settings key "ai.summary_enabled"
   If "false" → set media_file.summary_status = "disabled", return, notify user
    │
    ▼
2. Look up file's owner user_id
   Check user_setting key "ai_summary_enabled" for that user
   If "false" → set media_file.summary_status = "disabled", return, notify user
    │
    ▼
3. Check media_file.summary_status == "disabled"
   (Set at upload time via skip_summary=True flag)
   If already "disabled" → return without overwriting, notify user
    │
    ▼
4. Proceed with normal LLM check and summary dispatch
```

### 3.2 New `summary_status` Value: `"disabled"`

Add `"disabled"` as a first-class status value, distinct from `"not_configured"`:

| Status | Meaning | Retryable |
|--------|---------|-----------|
| `"disabled"` | Intentionally turned off | Only via explicit user action (re-enable + generate) |
| `"not_configured"` | No LLM provider set up | Yes, once LLM is configured |

### 3.3 Manual Trigger Behavior

The `POST /{file_uuid}/summarize` endpoint represents **explicit user intent**. Design:

- **System-level disabled** (admin setting): Block manual trigger for non-admin users (HTTP 423 or 403). Admin users can still manually trigger. The error message explains why.
- **User-level disabled**: The manual trigger **ignores** the user's own auto-summary preference and generates anyway (it's a deliberate on-demand request). This lets users have auto-disabled but still generate for specific files they care about.
- **Per-file disabled** (`summary_status == "disabled"` from upload flag): Manual trigger **resets the per-file disable** and generates. The user explicitly clicked "Generate Summary" on that file — that overrides the skip flag.

This approach respects the principle of least surprise: user preference controls auto-dispatch; explicit button clicks are not blocked.

### 3.4 New `summary_status` WebSocket Event

When a summary is skipped due to disable settings, send a `summarization_status` WebSocket event with `status: "disabled"` and an explanatory message — so the frontend can update the UI in real-time, the same as it does for `"not_configured"`.

### 3.5 Proposed API for Per-Upload Skip

Add optional `skip_summary: bool = False` to:
- Upload request body (`POST /api/files/upload`)
- URL processing request body (`POST /api/files/url`)

When `skip_summary=True`, set `media_file.summary_status = "disabled"` immediately on file creation, before the pipeline starts. The pipeline checks this field and skips.

---

## 4. Database Changes

### 4.1 No New Table Columns Required

Both `user_setting` and `system_settings` are already key-value stores. No `ALTER TABLE` is needed. The new status value `"disabled"` is a string stored in the existing VARCHAR column.

### 4.2 New `user_setting` Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ai_summary_enabled` | `"true"` / `"false"` | `"true"` | Per-user: auto-generate summaries after transcription |

### 4.3 New `system_settings` Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ai.summary_enabled` | `"true"` / `"false"` | `"true"` | System-wide: allow AI summary generation |

### 4.4 Alembic Migration: `v350_add_ai_summary_settings`

```python
# backend/alembic/versions/v350_add_ai_summary_settings.py

revision = "v350_add_ai_summary_settings"
down_revision = "v340_add_user_media_sources"

def upgrade():
    # Seed the system-wide default (true = enabled, matches current behavior)
    op.execute("""
        INSERT INTO system_settings (key, value, description)
        VALUES (
            'ai.summary_enabled',
            'true',
            'Global toggle for AI summary generation. Set to false to disable for all users.'
        )
        ON CONFLICT (key) DO NOTHING;
    """)

def downgrade():
    op.execute("DELETE FROM system_settings WHERE key = 'ai.summary_enabled'")
```

**Why seed a default?**: Makes the setting visible in the admin panel from day one and provides an audit trail. Users who never change it see `"true"`.

### 4.5 Migration Detection

Update `backend/app/db/migrations.py` — `_detect_schema_version()` to detect this migration by checking for the `ai.summary_enabled` system setting key.

### 4.6 `summary_status` Value Documentation

Add `"disabled"` to the inline comment in `backend/app/models/media.py`:

```python
summary_status = Column(
    String,
    default="pending",
    nullable=True,
)  # pending, processing, completed, failed, not_configured, disabled
```

No schema change needed — it's already a VARCHAR.

---

## 5. Backend Changes

### 5.1 New Constant

**File**: `backend/app/core/constants.py`

```python
# AI Summary settings defaults
DEFAULT_AI_SUMMARY_ENABLED = True
```

### 5.2 New Helper Module

**New file**: `backend/app/utils/summary_settings.py`

Centralizes all summary-enable checks to avoid scattered DB queries:

```python
def is_summary_enabled_system(db: Session) -> bool:
    """Check system_settings key 'ai.summary_enabled'. Defaults to True."""
    ...

def is_summary_enabled_for_user(db: Session, user_id: int) -> bool:
    """Check user_setting key 'ai_summary_enabled' for a user. Defaults to True."""
    ...

def get_summary_disable_reason(db: Session, user_id: int) -> str | None:
    """Return human-readable reason why summary is disabled, or None if enabled.

    Returns:
        "system" if system-wide disabled
        "user" if user preference
        None if enabled
    """
    ...
```

These functions follow the same pattern as `is_llm_available()` in `llm_service.py`.

### 5.3 `trigger_automatic_summarization()` — Core Change

**File**: `backend/app/tasks/transcription/core.py` (line ~1208)

Current code dispatches `summarize_transcript_task` unconditionally (when `tasks_to_run` allows it). Change to:

```python
if tasks_to_run is None or "summarization" in tasks_to_run:
    # NEW: Check disable settings before dispatching
    from app.utils.summary_settings import get_summary_disable_reason
    from app.db.session_utils import session_scope
    from app.models.media import MediaFile

    with session_scope() as db:
        media_file = db.query(MediaFile).filter(MediaFile.uuid == file_uuid).first()
        if not media_file:
            logger.warning(f"File {file_uuid} not found for summary dispatch")
        else:
            # Check if file was already marked disabled (per-upload skip_summary flag)
            if str(media_file.summary_status) == "disabled":
                logger.info(f"Summary disabled for file {file_id} (per-file flag)")
                _send_summary_disabled_notification(int(media_file.user_id), file_id)
            else:
                # Check system and user settings
                disable_reason = get_summary_disable_reason(db, int(media_file.user_id))
                if disable_reason:
                    media_file.summary_status = "disabled"
                    db.commit()
                    logger.info(f"Summary disabled for file {file_id} (reason: {disable_reason})")
                    _send_summary_disabled_notification(int(media_file.user_id), file_id, disable_reason)
                else:
                    # Normal path: dispatch
                    summary_task = summarize_transcript_task.delay(
                        file_uuid=file_uuid,
                        prompt_uuid=collection_prompt_uuid,
                    )
                    logger.info(f"Automatic summarization task {summary_task.id} started for file {file_id}")
```

Add helper `_send_summary_disabled_notification()` that sends a `summarization_status` WebSocket event with `status="disabled"` and an appropriate user-facing message.

### 5.4 `summarize_transcript_task` — Safety Net

**File**: `backend/app/tasks/summarization.py`

Add an early-exit check at the top of the task body (inside `session_scope`):

```python
# Safety net: task may be called directly (e.g., retry endpoint) when
# file was per-upload disabled. Manual trigger endpoint resets status
# before dispatching, so this only blocks zombie tasks from old queues.
if str(media_file.summary_status) == "disabled":
    logger.info(f"Summary task skipped — file {file_id} has disabled status")
    update_task_status(db, task_id, "completed", progress=1.0, completed=True)
    return {"status": "skipped", "file_id": file_id, "message": "Summary generation is disabled for this file"}
```

Note: The system/user setting checks are NOT duplicated here. The `trigger_automatic_summarization` function is the gatekeeper for auto-dispatch. The manual trigger endpoint has its own check (see §5.7).

### 5.5 User Settings API

**File**: `backend/app/api/endpoints/user_settings.py`

Add two new endpoint handlers following the pattern of existing settings (e.g., `llm_output_language`):

```python
@router.get("/ai-summary")
async def get_ai_summary_setting(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get user's auto-summary preference."""
    setting = db.query(UserSetting).filter(
        UserSetting.user_id == current_user.id,
        UserSetting.setting_key == "ai_summary_enabled",
    ).first()
    enabled = True if not setting else setting.setting_value.lower() != "false"
    return {"ai_summary_enabled": enabled}


@router.put("/ai-summary")
async def update_ai_summary_setting(
    enabled: bool = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Enable or disable automatic AI summary generation for this user."""
    _upsert_user_setting(db, int(current_user.id), "ai_summary_enabled", str(enabled).lower())
    return {"ai_summary_enabled": enabled, "message": f"AI summary auto-generation {'enabled' if enabled else 'disabled'}"}
```

### 5.6 Admin/System Settings API

**File**: `backend/app/api/endpoints/admin.py` (or a new `backend/app/api/endpoints/llm_settings.py` section)

```python
@router.get("/system/ai-summary")
async def get_system_ai_summary_setting(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get system-wide AI summary setting (admin only)."""
    _require_admin(current_user)
    setting = db.query(SystemSettings).filter(SystemSettings.key == "ai.summary_enabled").first()
    enabled = True if not setting else setting.value.lower() != "false"
    return {"ai_summary_enabled": enabled, "scope": "system"}


@router.put("/system/ai-summary")
async def update_system_ai_summary_setting(
    enabled: bool = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Enable or disable AI summary generation system-wide (admin only)."""
    _require_admin(current_user)
    _upsert_system_setting(db, "ai.summary_enabled", str(enabled).lower(),
        "Global toggle for AI summary auto-generation")
    return {"ai_summary_enabled": enabled, "scope": "system"}
```

### 5.7 Manual Trigger Endpoint — Behavior Update

**File**: `backend/app/api/endpoints/summarization.py` — `trigger_summarization()`

```python
@router.post("/{file_uuid}/summarize")
async def trigger_summarization(...):
    ...
    # Existing: check LLM availability
    # NEW: check system-wide disable (non-admin users blocked)
    if not current_user.role == "admin":
        from app.utils.summary_settings import is_summary_enabled_system
        if not is_summary_enabled_system(db):
            raise HTTPException(
                status_code=423,  # Locked
                detail="AI summary generation has been disabled by the system administrator. Contact your admin to re-enable.",
            )

    # Per-file disabled status: manual trigger resets it (explicit user intent)
    if str(media_file.summary_status) == "disabled":
        # Reset the per-file disable so the task can run
        media_file.summary_status = "pending"
        db.commit()
        logger.info(f"User manually triggered summary for file {file_id}; resetting per-file disabled status")

    # Note: we do NOT check the user-level ai_summary_enabled preference here.
    # Manual trigger = explicit intent = overrides the "don't auto-generate" preference.

    task = summarize_transcript_task.delay(
        file_uuid=file_uuid,
        force_regenerate=request.force_regenerate,
        prompt_uuid=request.prompt_uuid,
    )
    ...
```

**Rationale**: HTTP 423 (Locked) is semantically appropriate — the resource is locked by admin policy. Alternative is 403 (Forbidden).

### 5.8 Summary Status Endpoint — Update

**File**: `backend/app/api/endpoints/files/summary_status.py` — `get_summary_status()`

Add `summary_enabled` fields to the response:

```python
from app.utils.summary_settings import is_summary_enabled_system, is_summary_enabled_for_user

system_enabled = is_summary_enabled_system(db)
user_enabled = is_summary_enabled_for_user(db, int(current_user.id))

return {
    "file_id": str(media_file.uuid),
    "summary_status": media_file.summary_status or "pending",
    "summary_exists": bool(media_file.summary_data or media_file.summary_opensearch_id),
    "llm_available": llm_available,
    "can_retry": can_retry,
    "transcription_status": media_file.status,
    "filename": media_file.filename,
    # NEW fields:
    "summary_enabled_system": system_enabled,
    "summary_enabled_user": user_enabled,
    "can_generate": (
        llm_available
        and media_file.status == "completed"
        and (current_user.role == "admin" or system_enabled)
    ),
}
```

### 5.9 Upload Endpoint — Per-File Skip

**File**: `backend/app/api/endpoints/files/upload.py`

Add `skip_summary: bool = False` to the upload form/body schema. When `True`, after creating the `MediaFile` record, immediately set:

```python
if skip_summary:
    media_file.summary_status = "disabled"
    db.commit()
```

The pipeline then reads this at dispatch time (see §5.3) and skips summary.

**Schema change**: Update the relevant Pydantic schema in `backend/app/schemas/media.py` to include `skip_summary: bool = False`.

### 5.10 URL Processing Endpoint — Per-File Skip

**File**: `backend/app/api/endpoints/files/url_processing.py`

Same as §5.9 — add `skip_summary: bool = False` to the URL download request body.

### 5.11 Reprocess Endpoint — No Change Needed

The existing selective reprocess flow already lets users omit `"summarization"` from the stages list. No changes required for reprocessing. However, document this clearly in the API OpenAPI description.

### 5.12 `_handle_no_llm_configured()` vs `_handle_summary_disabled()`

Currently `summarization.py` has `_handle_no_llm_configured()` for the "no LLM" path. Consider adding a parallel `_handle_summary_disabled()` function for symmetry and to produce correct WebSocket notifications with the right user-facing message.

---

## 6. Frontend Changes

### 6.1 LLM Settings Panel — User-Level Toggle

**File**: `frontend/src/components/settings/LLMSettings.svelte`

Add a toggle below the LLM provider list (only visible when user has LLM configured):

```svelte
<div class="setting-row">
  <div class="setting-label">
    <span>{$t('settings.llm.autoSummary')}</span>
    <span class="setting-desc">{$t('settings.llm.autoSummaryDesc')}</span>
  </div>
  <label class="toggle">
    <input type="checkbox" bind:checked={autoSummaryEnabled} on:change={saveAutoSummary} />
    <span class="toggle-slider"></span>
  </label>
</div>
```

- Disabled state shows explanatory text: "Summaries will not be generated automatically after transcription. You can still generate them manually per-file."
- The toggle should use the `btn` / global classes and respect light/dark mode.
- Save via `PUT /api/settings/ai-summary`.

### 6.2 Admin Settings Panel — System-Level Toggle

**File**: `frontend/src/components/settings/LLMSettings.svelte` or a new `AISettings.svelte` under `settings/`

Add a section visible only to admin users. It should:
- Show the current system-wide state
- Display a warning when disabling: "This will prevent ALL users from generating AI summaries automatically. Manual generation will also be blocked for non-admin users."
- Use a confirmation dialog before disabling system-wide.
- Communicate this is a global change affecting all users.

### 6.3 Summary Status Display

**File**: `frontend/src/components/SummaryDisplay.svelte` and `SummaryActions.svelte`

Handle `summary_status === "disabled"` in the UI:

- Show a muted badge: "Summary disabled" instead of "Generate Summary"
- Show a "Generate Summary Anyway" button (bypasses auto-disable, maps to manual trigger endpoint)
- When system-level disabled (non-admin): hide the "Generate Anyway" button; show "Contact admin to enable summaries"
- When per-file disabled: show "Generate Anyway" (explicit user action)

### 6.4 Upload UI — Per-File Skip Option

**File**: `frontend/src/components/FileUploader.svelte`

Add an optional toggle in the upload form (collapsed by default under "Advanced options"):

```svelte
<!-- Advanced options accordion -->
<div class="advanced-option">
  <label>
    <input type="checkbox" bind:checked={skipSummary} />
    {$t('upload.skipSummary')}
  </label>
  <span class="hint">{$t('upload.skipSummaryHint')}</span>
</div>
```

Pass `skip_summary` in the upload API call. This option should only be visible when an LLM provider is configured (otherwise summary never generates anyway).

### 6.5 URL Processing UI

**File**: URL processing modal/form

Same toggle as upload UI (§6.4).

### 6.6 Bulk Upload

When bulk uploading multiple files, the `skip_summary` toggle in the upload UI applies to all files in the batch. This is the correct behavior for the voicemail bulk-upload use case.

### 6.7 i18n Strings

Add to all 7 locale files (`en`, `es`, `fr`, `de`, `pt`, `zh`, `ja`) in `frontend/src/lib/i18n/locales/`:

```json
{
  "settings": {
    "llm": {
      "autoSummary": "Auto-generate summaries",
      "autoSummaryDesc": "Automatically generate AI summaries after each transcription completes",
      "autoSummaryDisabledHint": "Summaries will not be generated automatically. You can still generate them manually per file."
    }
  },
  "upload": {
    "skipSummary": "Skip AI summary for this upload",
    "skipSummaryHint": "Transcription will complete without generating an AI summary"
  },
  "summary": {
    "statusDisabled": "Summary generation disabled",
    "generateAnyway": "Generate Summary Anyway",
    "systemDisabled": "AI summaries have been disabled by the administrator",
    "adminEnableHint": "Contact your administrator to enable AI summary generation"
  }
}
```

---

## 7. Edge Cases

### 7.1 Files Already Processing When Setting Changes

**Scenario**: Admin disables system-wide summary while 50 files are in the Celery GPU queue.

**Behavior**: The Celery task for each file calls `trigger_automatic_summarization()` at postprocess time, which reads the setting live from the DB. If disabled at that point, those files get `summary_status = "disabled"`. There is no retroactive cancellation of already-queued `summarize_transcript_task` jobs (this is by design — cancellation is complex and risky).

**Recommendation**: Document this in admin UI. If immediate cessation is critical, admins can also terminate the Celery NLP queue workers.

### 7.2 Re-enabling After Bulk Disable

**Scenario**: User disables auto-summary, uploads 200 files, then re-enables.

**Behavior**: The 200 existing files with `summary_status = "disabled"` will NOT auto-generate summaries. They need to be explicitly triggered.

**Plan**: Add a bulk "Generate Summaries" action to the gallery (similar to the existing bulk operations). This dispatches `summarize_transcript_task` for all completed files where `summary_status == "disabled"`.

**API**: `POST /api/files/bulk-summarize` — body: `{ "file_uuids": [...] }` or `{ "all_disabled": true }`.

### 7.3 Retry Endpoint and `disabled` Status

**File**: `backend/app/api/endpoints/files/summary_status.py` — `retry_summary()`

Current code: only allows retry if `summary_status in ["failed", "pending"]`.

**Update**: If status is `"disabled"`, return HTTP 400 with message: "This file has summary generation disabled. Use 'Generate Summary' to manually create one, or update your settings to re-enable auto-generation."

The `can_retry` field in the status response should be `False` when status is `"disabled"`.

### 7.4 Summary Search and Analytics Impact

When `summary_status = "disabled"`, no summary is stored in OpenSearch. The search and analytics endpoints (`/api/summaries/search`, `/api/summaries/analytics`) should degrade gracefully — disabled files simply don't appear in summary search results. No changes needed to the search code; OpenSearch just has no document for that file.

### 7.5 API Consumer (External Integrations / CRM)

External systems polling `GET /api/files/{file_uuid}/summary-status` will see:
- `summary_status: "disabled"` — NEW value they need to handle
- `can_generate: false` — NEW field (or `true` if admin)

**Backward compatibility**: This is a new status value. Existing consumers that treat unknown values as "not ready" will gracefully skip. Document the new value in the API changelog.

### 7.6 Cost Tracking

If in future there's cost tracking per summary (e.g., token usage logging), the `"disabled"` status correctly means $0 cost for that file. No cost tracking changes needed now; just ensure the `"disabled"` status is excluded from any future cost aggregations.

### 7.7 Per-User Disable vs Admin's Own Files

If admin disables system-wide summaries, they can still manually trigger summaries on any file (see §5.7 — admin bypasses system disable check). This allows the admin to test that summaries still work while enforcing cost control for the user base.

### 7.8 Shared LLM Config and Individual User Disable

**Scenario**: User A shares their LLM config with User B. User B has `ai_summary_enabled = false`. User A uploads a file → auto-summary generated. User B uploads a file → skipped.

**Behavior**: Correct — the setting is per-user, not per-LLM-config. Each user's own `ai_summary_enabled` is checked using the file's `user_id`.

### 7.9 `summary_status` on Reprocess

When a user triggers a full reprocess (`stages = ["transcription"]`), `clear_existing_transcription_data()` resets `summary_status = "pending"`. This means:
- A file that was per-upload disabled (`summary_status = "disabled"`) will have its status reset on full reprocess.
- After reprocess completes, `trigger_automatic_summarization()` re-checks the user/system settings. If the user has auto-summary disabled, it gets `"disabled"` again. If enabled, a summary is generated.

**This is the correct behavior** — full reprocess is a clean slate.

However, selective reprocess only clearing summary stage (`stages = ["summarization"]`) should preserve the user's intent:
- If user disabled auto-summary, selective re-run of summarization should still generate it (because they explicitly selected that stage in the UI).
- `dispatch_selective_tasks()` directly calls `summarize_transcript_task.delay()` for the `"summarization"` stage — this bypasses `trigger_automatic_summarization()`, so the disable check doesn't apply. **This is intentional** — selective stage reprocess is explicit user action.

### 7.10 Collection-Level Disable

**Out of scope for this issue.** A future enhancement could add a `skip_summary: bool` field to the `Collection` model so all files added to that collection inherit the setting.

### 7.11 `downstream_tasks` Thread-Through (Per-File Alternative)

An alternative implementation for per-file skip: instead of setting `summary_status = "disabled"` at upload time, exclude `"summarization"` from the `downstream_tasks` list threaded through the pipeline. This would require:
- Upload → `dispatch_transcription_pipeline(downstream_tasks=["analytics", "topic_extraction"])` (excluding `summarization`)
- The existing `downstream_tasks` mechanism would naturally skip summarization

**Why we use the status field approach instead**: The `downstream_tasks` exclusion only works for the pipeline chain. If the file is later reprocessed or a manual trigger is issued, the `downstream_tasks` are gone. Persisting `summary_status = "disabled"` on the file itself is the durable, auditable approach.

---

## 8. Compatibility Concerns

### 8.1 Backward Compatibility

- The new `"disabled"` status value is additive. Existing code that handles `summary_status` uses string comparisons (`== "completed"`, `== "failed"`) so unrecognized values are benign.
- No existing API response fields are removed or renamed.
- New fields (`summary_enabled_system`, `summary_enabled_user`, `can_generate`) added to the status endpoint response — additive only.
- New `skip_summary` upload parameter defaults to `False` — no change for existing callers.

### 8.2 Existing Integrations

External API consumers should update their clients to:
1. Handle `summary_status: "disabled"` (treat like "will not be generated").
2. Respect the new `can_generate` field before offering summary generation UI.

Add `"disabled"` to API documentation changelog.

### 8.3 Docker / Environment Variables

No new `.env` variables needed. All settings are DB-stored (consistent with the existing pattern for LLM provider config, ASR settings, etc.).

### 8.4 OpenSearch

No OpenSearch schema changes. When summary is disabled, no document is indexed — OpenSearch simply has no entry for that file's summary, which is gracefully handled by existing null-check logic.

### 8.5 Migration Path for Existing Deployments

1. Deploy new version → migration `v350` runs automatically on backend startup.
2. `system_settings.ai.summary_enabled` seeded as `"true"` → no behavior change.
3. All existing users default to `ai_summary_enabled = true` (no `user_setting` row means default = enabled).
4. Admins can then toggle as needed.

---

## 9. Testing Strategy

### 9.1 Unit Tests

**New test file**: `backend/tests/unit/test_summary_settings.py`

```python
class TestSummarySettings:
    def test_is_summary_enabled_system_default(self, db): ...
    def test_is_summary_enabled_system_when_disabled(self, db): ...
    def test_is_summary_enabled_for_user_default(self, db): ...
    def test_is_summary_enabled_for_user_when_disabled(self, db): ...
    def test_get_summary_disable_reason_system_takes_precedence(self, db): ...
    def test_get_summary_disable_reason_user_when_system_enabled(self, db): ...
    def test_get_summary_disable_reason_both_enabled(self, db): ...
```

### 9.2 Integration Tests — Pipeline

**New tests in**: `backend/tests/test_selective_reprocess.py` or a new `test_summary_disable.py`

```python
class TestAutoSummaryDisable:
    def test_system_disable_skips_auto_summary(self): ...
    def test_user_disable_skips_auto_summary(self): ...
    def test_per_file_skip_at_upload(self): ...
    def test_system_disable_blocks_manual_trigger_for_non_admin(self): ...
    def test_system_disable_allows_manual_trigger_for_admin(self): ...
    def test_user_disable_does_not_block_manual_trigger(self): ...
    def test_re_enable_does_not_retroactively_generate(self): ...
    def test_full_reprocess_resets_disabled_status(self): ...
    def test_selective_reprocess_summarization_ignores_user_setting(self): ...
    def test_disabled_status_not_retryable(self): ...
    def test_disabled_status_websocket_notification(self): ...
```

### 9.3 API Tests

**New test file**: `backend/tests/api/endpoints/test_summary_disable.py`

```python
class TestSummaryDisableEndpoints:
    def test_get_user_ai_summary_setting_default(self): ...
    def test_update_user_ai_summary_setting(self): ...
    def test_get_system_ai_summary_setting_admin_only(self): ...
    def test_update_system_ai_summary_setting_admin_only(self): ...
    def test_summary_status_endpoint_includes_new_fields(self): ...
    def test_upload_with_skip_summary_sets_disabled_status(self): ...
    def test_manual_trigger_resets_per_file_disabled(self): ...
    def test_manual_trigger_blocked_when_system_disabled_non_admin(self): ...
```

### 9.4 Frontend Tests

- Type-check: `npm run check` — verify `SummaryDisplay.svelte` handles `"disabled"` status
- Build verification: `npm run build`
- E2E test scenario: upload file with `skip_summary=True`, verify UI shows "Summary disabled" badge, click "Generate Summary Anyway", verify summary appears.

### 9.5 Regression Tests

Verify existing behavior is unchanged when no settings are modified:
- Upload → transcription → auto-summary generated (unchanged flow)
- Manual trigger works as before
- Retry works as before
- `not_configured` status still works when no LLM is set up

---

## 10. Implementation Phases

### Phase 1 — Core Backend (non-breaking, no UI)

1. **Constants**: Add `DEFAULT_AI_SUMMARY_ENABLED` to `constants.py`
2. **Helper module**: Create `backend/app/utils/summary_settings.py`
3. **Migration**: Create `backend/alembic/versions/v350_add_ai_summary_settings.py`
4. **Pipeline gatekeeper**: Modify `trigger_automatic_summarization()` in `core.py` to check system/user settings and per-file status
5. **Task safety net**: Add early-exit check in `summarize_transcript_task`

**At end of Phase 1**: Auto-summary is controllable via direct DB manipulation. No UI yet.

### Phase 2 — API Layer

6. **User settings API**: Add `GET/PUT /api/settings/ai-summary` in `user_settings.py`
7. **Admin API**: Add `GET/PUT /api/admin/ai-summary` in `admin.py`
8. **Status endpoint update**: Add new fields to `GET /{file_uuid}/summary-status`
9. **Manual trigger update**: Add system-disable check to `POST /{file_uuid}/summarize`
10. **Upload schema update**: Add `skip_summary: bool = False` to upload and URL request schemas
11. **Retry endpoint update**: Block retry when `status == "disabled"`
12. **`migrations.py` update**: Add detection for `v350`

**At end of Phase 2**: Full API coverage; can be used by API consumers and CRM integrations immediately.

### Phase 3 — Frontend

13. **User-level toggle**: Add auto-summary toggle in `LLMSettings.svelte`
14. **Admin-level toggle**: Add system summary toggle in admin settings panel
15. **Status display**: Update `SummaryDisplay.svelte` / `SummaryActions.svelte` for `"disabled"` status
16. **Upload UI**: Add per-upload skip option to `FileUploader.svelte`
17. **URL processing UI**: Add same option to URL processing form
18. **i18n**: Add all new translation keys for all 7 languages

### Phase 4 — Bulk Operations (optional, can be deferred)

19. **Bulk summarize API**: `POST /api/files/bulk-summarize` for retroactive generation on disabled files
20. **Gallery bulk action**: "Generate Summaries" bulk action in the gallery view

### Phase 5 — Polish and Documentation

21. **Tests**: Write all test cases from §9
22. **API changelog**: Document new `"disabled"` status value and new endpoint fields
23. **Admin docs**: Update admin guide with system-level toggle instructions
24. **CHANGELOG.md**: Update with Keep-a-Changelog format entry under `[Unreleased]`

---

## Appendix A: File Modification Summary

| File | Change Type | Phase |
|------|------------|-------|
| `backend/alembic/versions/v350_add_ai_summary_settings.py` | New | 1 |
| `backend/app/core/constants.py` | Modify (add constant) | 1 |
| `backend/app/utils/summary_settings.py` | New | 1 |
| `backend/app/tasks/transcription/core.py` | Modify (gatekeeper check) | 1 |
| `backend/app/tasks/summarization.py` | Modify (safety net) | 1 |
| `backend/app/models/media.py` | Modify (comment only) | 1 |
| `backend/app/db/migrations.py` | Modify (detection) | 2 |
| `backend/app/api/endpoints/user_settings.py` | Modify (new endpoints) | 2 |
| `backend/app/api/endpoints/admin.py` | Modify (new endpoints) | 2 |
| `backend/app/api/endpoints/files/summary_status.py` | Modify (new fields) | 2 |
| `backend/app/api/endpoints/summarization.py` | Modify (system disable check) | 2 |
| `backend/app/api/endpoints/files/upload.py` | Modify (skip_summary param) | 2 |
| `backend/app/api/endpoints/files/url_processing.py` | Modify (skip_summary param) | 2 |
| `backend/app/schemas/media.py` | Modify (upload schema) | 2 |
| `frontend/src/components/settings/LLMSettings.svelte` | Modify (user toggle) | 3 |
| `frontend/src/components/settings/LLMSettings.svelte` or new `AISettings.svelte` | Modify/New (admin toggle) | 3 |
| `frontend/src/components/SummaryDisplay.svelte` | Modify (disabled state) | 3 |
| `frontend/src/components/SummaryActions.svelte` | Modify (disabled state) | 3 |
| `frontend/src/components/FileUploader.svelte` | Modify (per-file skip) | 3 |
| `frontend/src/lib/i18n/locales/*.json` (7 files) | Modify (new keys) | 3 |
| `backend/tests/unit/test_summary_settings.py` | New | 5 |
| `backend/tests/api/endpoints/test_summary_disable.py` | New | 5 |
| `CHANGELOG.md` | Modify | 5 |

---

## Appendix B: New API Fields Reference

### `GET /api/files/{file_uuid}/summary-status` — New Fields

```json
{
  "file_id": "uuid",
  "summary_status": "disabled",
  "summary_exists": false,
  "llm_available": true,
  "can_retry": false,
  "transcription_status": "completed",
  "filename": "voicemail_001.mp3",
  "summary_enabled_system": true,
  "summary_enabled_user": false,
  "can_generate": true
}
```

### `POST /api/files/upload` — New Body Field

```json
{
  "skip_summary": true
}
```

### `POST /api/settings/ai-summary` — New Endpoint

```
PUT /api/settings/ai-summary
Body: { "enabled": false }
Response: { "ai_summary_enabled": false, "message": "AI summary auto-generation disabled" }
```

### `GET/PUT /api/admin/system/ai-summary` — New Admin Endpoint

```
PUT /api/admin/system/ai-summary
Body: { "enabled": false }
Response: { "ai_summary_enabled": false, "scope": "system" }
```
