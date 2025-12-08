<objective>
Add per-file speaker diarization settings (min speakers, max speakers, fixed speaker count) to the upload and reprocess UI.

This allows users to control speaker detection on a per-file basis without requiring container restarts to change environment variables. When fields are left empty, the system falls back to environment variable defaults (MIN_SPEAKERS, MAX_SPEAKERS, NUM_SPEAKERS).
</objective>

<context>
OpenTranscribe is a transcription application using WhisperX and PyAnnote for speaker diarization. Currently, speaker count parameters are only configurable via environment variables.

Read these files to understand existing patterns:
- @frontend/src/components/FileUploader.svelte - Main upload component
- @frontend/src/components/ReprocessButton.svelte - Reprocess trigger component
- @backend/app/api/endpoints/files.py - File upload/reprocess API endpoints
- @backend/app/tasks/transcription/core.py:175-182 - Where speaker params are passed to whisperx_service
- @backend/app/schemas/file.py - File-related Pydantic schemas
- @CLAUDE.md - Project conventions and architecture
</context>

<requirements>
<frontend>
1. Add a collapsible "Advanced Settings" panel to both FileUploader.svelte upload dialog and any reprocess modal/dialog
2. The advanced panel should contain three optional number inputs:
   - "Min Speakers" (positive integer, optional)
   - "Max Speakers" (positive integer, optional)
   - "Fixed Speaker Count" (positive integer, optional) - when set, overrides min/max
3. Show placeholder text indicating the current env default values (fetch from backend if possible, or show "Uses system default")
4. Validation: min <= max when both are set; fixed count overrides min/max (disable min/max inputs when fixed is set)
5. Match existing UI patterns for form styling, dark/light mode support
6. Panel should be collapsed by default to keep the upload experience simple for most users
</frontend>

<backend>
1. Update file upload endpoint to accept optional speaker parameters: min_speakers, max_speakers, num_speakers
2. Update reprocess endpoint similarly
3. Create/update Pydantic schemas to include these optional fields
4. Pass values through to the Celery task, falling back to settings.MIN_SPEAKERS, settings.MAX_SPEAKERS, settings.NUM_SPEAKERS when not provided
5. Store the per-file speaker settings in the database so reprocessing can use them (optional enhancement)
</backend>

<api_contract>
Upload/reprocess request body should accept optional fields:
```json
{
  "min_speakers": 2,      // optional, positive int
  "max_speakers": 5,      // optional, positive int
  "num_speakers": null    // optional, positive int - overrides min/max when set
}
```
</api_contract>
</requirements>

<implementation>
1. Start with backend schema and endpoint changes
2. Update the Celery task to accept and use these parameters
3. Add frontend UI components with proper validation
4. Test the full flow: upload with custom settings → verify parameters reach whisperx_service

Constraints (with reasoning):
- Use existing component patterns - the codebase has established UI conventions that should be followed for consistency
- Don't create new utility files for this feature - it's contained enough to live in existing files
- Fallback to env defaults must happen in backend, not frontend - the backend is the source of truth for configuration
</implementation>

<output>
Modify these files:
- `backend/app/schemas/file.py` - Add optional speaker count fields
- `backend/app/api/endpoints/files.py` - Accept new parameters in upload/reprocess
- `backend/app/tasks/transcription/core.py` - Use passed parameters with fallback
- `frontend/src/components/FileUploader.svelte` - Add advanced settings panel
- `frontend/src/components/ReprocessButton.svelte` - Add same settings to reprocess

If a separate reprocess modal exists, modify that instead of/in addition to ReprocessButton.
</output>

<verification>
Before declaring complete:
1. Run TypeScript check: `cd frontend && npm run check` - must pass
2. Verify the backend starts without errors: check docker logs for backend service
3. Test upload flow with custom speaker settings in browser
4. Test reprocess flow with custom speaker settings
5. Verify fallback behavior: upload without settings should use env defaults
6. Verify dark mode styling matches existing components
</verification>

<success_criteria>
- Users can set min/max/fixed speaker count when uploading files
- Users can set these parameters when reprocessing files
- Empty fields correctly fall back to environment variable defaults
- Fixed speaker count disables/overrides min/max fields
- UI matches existing design patterns and supports dark mode
- No TypeScript errors
- Backend accepts and correctly passes parameters to transcription pipeline
</success_criteria>
