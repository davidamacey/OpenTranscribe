# TO-DOS

## Feature Requests (2025-12-06)

- **Add retry count reset to UI** | Problem: Users hit max retry limit (3) and get "400 Bad Request" when trying to reprocess files. Currently requires database access to fix. | Workaround: Run `./scripts/reset-retries.sh` or `./scripts/reset-retries.sh <file_uuid>` | Files: `frontend/src/components/`, `backend/app/api/endpoints/files/reprocess.py:148-152` | Solution: Add admin button to reset retry count for a file, or auto-reset on manual reprocess request

- **Speaker merge UI** | Problem: PyAnnote NUM_SPEAKERS constraint doesn't work - 7 actual speakers detected as 19 | Files: `frontend/src/components/`, `backend/app/api/endpoints/speakers/` | Solution: Allow users to merge multiple detected speakers into one, reassigning all segments

- **Reassign segment to different speaker** | Problem: Individual transcript segments may be attributed to wrong speaker | Files: `frontend/src/components/TranscriptSegment.svelte`, `backend/app/api/endpoints/transcripts/` | Solution: Add UI to reassign a single segment's speaker from dropdown of available speakers

- ~~**Auto-populate OpenAI models in LLM settings**~~ ✅ DONE 2025-12-07 | Added "Discover Models" button for OpenAI, vLLM, and OpenRouter providers. Backend endpoint fetches from `/v1/models`, frontend displays model selector dropdown. Button disabled until required fields filled (base_url, api_key for providers that need it).

- ~~**Add speaker count settings to import/reprocess UI**~~ ✅ DONE 2025-12-07 | Settings dialog added for min, max, and fixed speaker count configuration.

- **Auto-cleanup garbage transcription segments** | Problem: WhisperX can misinterpret background noise as extremely long "words" (e.g., 442-character "Brrrrr...") with no spaces, causing UI layout issues (horizontal scrollbars). | Files: `backend/app/tasks/transcription/core.py`, `frontend/src/components/settings/`, `backend/app/api/endpoints/settings/` | Solution: Add configurable setting for max word length threshold (default: 50 chars). During transcription post-processing, detect segments containing words exceeding threshold and either replace with `[background noise]`, flag for review, or truncate. Setting should be accessible in UI under transcription settings.

## Bug Reports - 2025-12-06 22:51

- ~~**Fix custom OpenAI-compatible server connection via HTTP**~~ ✅ FIXED 2025-12-07 | Root cause: `LLMProvider.OPENAI` endpoint was hardcoded to `https://api.openai.com/v1/chat/completions`, ignoring `config.base_url`. Fixed by using `build_endpoint(config.base_url)` with fallback to official API.

- ~~**API Key field missing in edit mode**~~ ✅ FIXED 2025-12-07 | API key now fetched and populated in edit mode like other fields. Added backend endpoint to return decrypted key for authorized user's own configs.
