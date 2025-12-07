<objective>
Implement auto-cleanup for garbage transcription segments caused by WhisperX misinterpreting background noise as extremely long "words" (e.g., 442-character "Brrrrr..." strings with no spaces).

This causes UI layout issues (horizontal scrollbars) and degrades transcript quality. The solution should detect these garbage patterns during post-processing and replace them with a clean marker.
</objective>

<context>
OpenTranscribe uses WhisperX for transcription. Sometimes background noise (fans, static, rumbling) gets transcribed as very long nonsense words without spaces. These need to be detected and cleaned up.

Read these files to understand the architecture:
- `@backend/app/tasks/transcription/core.py` - Where transcription post-processing happens
- `@backend/app/services/system_settings_service.py` - Existing system settings pattern
- `@backend/app/api/endpoints/admin.py` - Existing admin settings endpoints
- `@frontend/src/components/settings/RetrySettings.svelte` - Example settings component
- `@database/init_db.sql` - System settings table structure

Follow patterns and conventions in `@CLAUDE.md`.
</context>

<requirements>
## Backend Requirements

1. **System Settings** (extend existing pattern)
   - Add two new settings to `system_settings` table:
     - `transcription.max_word_length` (integer, default: 50)
     - `transcription.garbage_cleanup_enabled` (boolean, default: true)
   - Add functions in `system_settings_service.py`:
     - `get_garbage_cleanup_config()` returning both settings
     - `update_garbage_cleanup_config()` for updates

2. **Admin API Endpoints**
   - `GET /admin/settings/garbage-cleanup` - Get current config
   - `PUT /admin/settings/garbage-cleanup` - Update config
   - Add schemas in `backend/app/schemas/admin.py`

3. **Transcription Post-Processing**
   - In `backend/app/tasks/transcription/core.py`, add cleanup step after transcription
   - For each segment, check each word:
     - If word length > max_word_length threshold AND word has no spaces
     - Replace that word with `[background noise]`
   - Only run if `garbage_cleanup_enabled` is true
   - Log when garbage is detected and cleaned

## Frontend Requirements

1. **GarbageCleanupSettings.svelte** (new component)
   - Toggle to enable/disable garbage cleanup
   - Number input for max word length threshold (min: 20, max: 200)
   - Help text explaining the feature
   - Save button with loading state
   - Follow RetrySettings.svelte patterns exactly

2. **Integration in SettingsModal.svelte**
   - Add to ADMINISTRATION section (after RetrySettings)
   - Import and render GarbageCleanupSettings component

3. **API Client**
   - Add to `frontend/src/lib/api/adminSettings.ts`:
     - `getGarbageCleanupConfig()`
     - `updateGarbageCleanupConfig()`
</requirements>

<implementation>
## Detection Logic

A word is considered "garbage" if:
1. `len(word) > max_word_length` (default 50)
2. Word contains no spaces (it's a single continuous string)
3. Optionally: word has high character repetition (e.g., "rrrrrr", "brrrrr")

Replace the garbage word with `[background noise]` - keep the rest of the segment text intact.

## Files to Create/Modify

Backend:
- `./database/init_db.sql` - Add default settings
- `./backend/app/services/system_settings_service.py` - Add config functions
- `./backend/app/schemas/admin.py` - Add schemas
- `./backend/app/api/endpoints/admin.py` - Add endpoints
- `./backend/app/tasks/transcription/core.py` - Add cleanup logic

Frontend:
- `./frontend/src/components/settings/GarbageCleanupSettings.svelte` - New component
- `./frontend/src/components/SettingsModal.svelte` - Import and add component
- `./frontend/src/lib/api/adminSettings.ts` - Add API functions
</implementation>

<output>
Create/modify these files:
- `./database/init_db.sql` - Add INSERT for new settings
- `./backend/app/services/system_settings_service.py` - Add garbage cleanup functions
- `./backend/app/schemas/admin.py` - Add GarbageCleanupConfig schemas
- `./backend/app/api/endpoints/admin.py` - Add GET/PUT endpoints
- `./backend/app/tasks/transcription/core.py` - Add post-processing cleanup
- `./frontend/src/components/settings/GarbageCleanupSettings.svelte` - New settings UI
- `./frontend/src/components/SettingsModal.svelte` - Add import and component
- `./frontend/src/lib/api/adminSettings.ts` - Add API client functions
</output>

<verification>
Before completing, verify:

1. Database: New settings exist in init_db.sql
2. Backend API: Test endpoints respond correctly
   - `curl http://localhost:5174/api/admin/settings/garbage-cleanup`
3. Frontend: Component renders in Settings modal under ADMINISTRATION
4. TypeScript: Run `npm run check` in frontend - no errors
5. Integration: Settings changes persist and affect transcription behavior
</verification>

<success_criteria>
- Admin can toggle garbage cleanup on/off in Settings
- Admin can configure max word length threshold
- New transcriptions automatically clean up garbage words
- Garbage words replaced with `[background noise]` marker
- Settings persist in database
- No TypeScript or Python errors
</success_criteria>
