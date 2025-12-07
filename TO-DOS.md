# TO-DOS

## Feature Requests (2025-12-06)

- ~~**Add retry count reset to UI**~~ ✅ DONE 2025-12-07 | Added comprehensive retry management: (1) Admin "System Settings" panel with configurable max retries and toggle to disable limits, (2) "Reset Retries" button on file detail page for admins when files hit retry limit, (3) Backend uses dynamic config from system_settings table. Files: `backend/app/models/system_settings.py`, `backend/app/services/system_settings_service.py`, `backend/app/api/endpoints/admin.py`, `frontend/src/components/settings/RetrySettings.svelte`

- ~~**Speaker merge UI**~~ ✅ DONE 2025-12-07 | Multi-select checkboxes to merge duplicate speakers. Files: `frontend/src/components/SpeakerMerge.svelte`, `frontend/src/lib/api/speakers.ts`. Uses existing backend merge endpoint.

- ~~**Reassign segment to different speaker**~~ ✅ DONE 2025-12-07 | Inline dropdown on segment speaker names. Click speaker badge to reassign via portal dropdown. Backend: `PUT /api/transcripts/segments/{uuid}/speaker`. Files: `frontend/src/components/SegmentSpeakerDropdown.svelte`, `frontend/src/lib/api/transcripts.ts`, `backend/app/api/endpoints/transcript_segments.py`

- ~~**Auto-populate OpenAI models in LLM settings**~~ ✅ DONE 2025-12-07 | Added "Discover Models" button for OpenAI, vLLM, and OpenRouter providers. Backend endpoint fetches from `/v1/models`, frontend displays model selector dropdown. Button disabled until required fields filled (base_url, api_key for providers that need it).

- ~~**Add speaker count settings to import/reprocess UI**~~ ✅ DONE 2025-12-07 | Settings dialog added for min, max, and fixed speaker count configuration.

- **Auto-cleanup garbage transcription segments** | Problem: WhisperX can misinterpret background noise as extremely long "words" (e.g., 442-character "Brrrrr...") with no spaces, causing UI layout issues (horizontal scrollbars). | Files: `backend/app/tasks/transcription/core.py`, `frontend/src/components/settings/`, `backend/app/api/endpoints/settings/` | Solution: Add configurable setting for max word length threshold (default: 50 chars). During transcription post-processing, detect segments containing words exceeding threshold and either replace with `[background noise]`, flag for review, or truncate. Setting should be accessible in UI under transcription settings.

## Bug Reports - 2025-12-06 22:51

- ~~**Fix custom OpenAI-compatible server connection via HTTP**~~ ✅ FIXED 2025-12-07 | Root cause: `LLMProvider.OPENAI` endpoint was hardcoded to `https://api.openai.com/v1/chat/completions`, ignoring `config.base_url`. Fixed by using `build_endpoint(config.base_url)` with fallback to official API.

- ~~**API Key field missing in edit mode**~~ ✅ FIXED 2025-12-07 | API key now fetched and populated in edit mode like other fields. Added backend endpoint to return decrypted key for authorized user's own configs.
