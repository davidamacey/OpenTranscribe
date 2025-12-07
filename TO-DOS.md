# TO-DOS

## Feature Requests (2025-12-06)

- **Add retry count reset to UI** | Problem: Users hit max retry limit (3) and get "400 Bad Request" when trying to reprocess files. Currently requires database access to fix. | Workaround: Run `./scripts/reset-retries.sh` or `./scripts/reset-retries.sh <file_uuid>` | Files: `frontend/src/components/`, `backend/app/api/endpoints/files/reprocess.py:148-152` | Solution: Add admin button to reset retry count for a file, or auto-reset on manual reprocess request

- **Speaker merge UI** | Problem: PyAnnote NUM_SPEAKERS constraint doesn't work - 7 actual speakers detected as 19 | Files: `frontend/src/components/`, `backend/app/api/endpoints/speakers/` | Solution: Allow users to merge multiple detected speakers into one, reassigning all segments

- **Reassign segment to different speaker** | Problem: Individual transcript segments may be attributed to wrong speaker | Files: `frontend/src/components/TranscriptSegment.svelte`, `backend/app/api/endpoints/transcripts/` | Solution: Add UI to reassign a single segment's speaker from dropdown of available speakers

- **Auto-populate OpenAI models in LLM settings** | Problem: Users must manually type model names when configuring OpenAI provider. | Files: `frontend/src/components/settings/LLMSettings.svelte`, `backend/app/api/endpoints/settings/` | Solution: When OpenAI is selected as provider, fetch available models via OpenAI API (/v1/models) and populate dropdown

- **Add speaker count settings to import/reprocess UI** | Problem: Speaker diarization parameters (MIN_SPEAKERS, MAX_SPEAKERS, NUM_SPEAKERS) are only configurable via environment variables, requiring container restart. Users need per-file control. | Files: `frontend/src/components/UploadModal.svelte`, `frontend/src/components/FileActions.svelte`, `backend/app/api/endpoints/files/`, `backend/app/tasks/transcription/core.py:175-182` | Solution: Add three optional fields to upload form and reprocess dialog: min speakers, max speakers, and fixed speaker count. If fixed count is set, it overrides min/max. Pass values to transcription task, falling back to env defaults when not specified.

- **Auto-cleanup garbage transcription segments** | Problem: WhisperX can misinterpret background noise as extremely long "words" (e.g., 442-character "Brrrrr...") with no spaces, causing UI layout issues (horizontal scrollbars). | Files: `backend/app/tasks/transcription/core.py`, `frontend/src/components/settings/`, `backend/app/api/endpoints/settings/` | Solution: Add configurable setting for max word length threshold (default: 50 chars). During transcription post-processing, detect segments containing words exceeding threshold and either replace with `[background noise]`, flag for review, or truncate. Setting should be accessible in UI under transcription settings.

## Bug Reports - 2025-12-06 22:51

- **Fix custom OpenAI-compatible server connection via HTTP** | Problem: Calling a custom OpenAI-compatible server via HTTP with a custom port fails. The LLM provider configuration may be enforcing HTTPS or not properly handling non-standard ports. | Files: `backend/app/services/llm_service.py`, `backend/app/core/config.py:110-127`, `frontend/src/components/settings/` | Solution: Verify HTTP URLs are accepted without upgrade to HTTPS, ensure custom ports are preserved in API calls
