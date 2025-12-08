<objective>
Implement inline speaker reassignment for individual transcript segments, allowing users to click on a segment's speaker name and select a different speaker from a dropdown.

This requires both a backend endpoint to update segment speaker assignment and frontend UI for the inline dropdown.
</objective>

<context>
OpenTranscribe transcripts sometimes have segments attributed to the wrong speaker. Users need to correct individual segment attributions without affecting other segments.

Read these files to understand the current architecture:
- `@frontend/src/components/TranscriptDisplay.svelte` - Current segment display with speaker info
- `@backend/app/api/endpoints/transcripts/` - Existing transcript endpoints
- `@backend/app/schemas/media.py` - Transcript segment schemas
- `@backend/app/models/media.py` - TranscriptSegment model (has speaker_id FK)
- `@database/init_db.sql` - Database schema for transcript_segment table

Follow patterns and conventions in `@CLAUDE.md`.
</context>

<requirements>
## Backend Requirements

1. **New Endpoint**: `PUT /api/transcripts/segments/{segment_uuid}/speaker`
   - Request body: `{ "speaker_uuid": "uuid-string" }` (can be null to unassign)
   - Validate segment belongs to current user's file
   - Update the `speaker_id` foreign key
   - Return updated segment with speaker info
   - Add appropriate schema in `backend/app/schemas/`

2. **Router Registration**
   - Add endpoint to appropriate router in `backend/app/api/endpoints/transcripts/`
   - Ensure proper authentication (require logged-in user)

## Frontend Requirements

1. **Inline Speaker Dropdown**
   - When user clicks speaker name/label on a segment, show dropdown
   - Dropdown lists all speakers for this media file
   - Each option shows speaker name with color indicator
   - Include "No Speaker" option to unassign
   - Clicking outside closes dropdown without changes

2. **Visual Design**
   - Dropdown appears near the clicked speaker name
   - Currently assigned speaker highlighted/checked
   - Hover states for options
   - Loading indicator while saving
   - Smooth transitions

3. **State Management**
   - Optimistic UI update (show change immediately)
   - Rollback on error with toast notification
   - Update segment in local state after successful save

4. **Integration**
   - Works alongside existing segment text editing
   - Uses existing speaker color system
   - Available in normal view mode (not just edit mode)
</requirements>

<implementation>
## Backend Files

1. `./backend/app/schemas/transcript.py` (NEW or extend)
   ```python
   class SegmentSpeakerUpdate(BaseModel):
       speaker_uuid: Optional[str] = None  # null to unassign
   ```

2. `./backend/app/api/endpoints/transcripts/segments.py` (NEW or extend existing)
   - PUT endpoint for speaker reassignment
   - Query segment by UUID, verify ownership
   - Look up speaker by UUID if provided
   - Update segment.speaker_id
   - Return updated segment

3. Register in router (`backend/app/api/router.py` if needed)

## Frontend Files

1. `./frontend/src/components/SegmentSpeakerDropdown.svelte` (NEW)
   - Props: `segment`, `speakers`, `currentSpeakerId`
   - Events: `change` (with new speaker UUID)
   - Handles dropdown open/close state
   - Positioned relative to trigger element

2. `./frontend/src/lib/api/transcripts.ts` (NEW or extend)
   - `updateSegmentSpeaker(segmentUuid: string, speakerUuid: string | null)`

3. `./frontend/src/components/TranscriptDisplay.svelte`
   - Import and use SegmentSpeakerDropdown
   - Handle speaker change events
   - Update local segment state
</implementation>

<output>
Backend files:
- `./backend/app/schemas/transcript.py` - New/updated schema
- `./backend/app/api/endpoints/transcripts/segments.py` - New endpoint
- Router registration if needed

Frontend files:
- `./frontend/src/components/SegmentSpeakerDropdown.svelte` - New dropdown component
- `./frontend/src/lib/api/transcripts.ts` - API client function
- `./frontend/src/components/TranscriptDisplay.svelte` - Integration
</output>

<verification>
Before completing, verify:

Backend:
1. Endpoint responds to PUT requests correctly
2. Proper authentication/authorization checks
3. Returns updated segment data
4. Handles null speaker_uuid (unassign)

Frontend:
1. Clicking speaker name opens dropdown
2. Dropdown shows all available speakers with colors
3. Selecting speaker calls API and updates UI
4. Error handling with rollback works
5. Both light and dark themes work
6. Run `npm run check` - no TypeScript errors
7. Test with actual API call (not mocked)
</verification>

<success_criteria>
- Backend endpoint works: `curl -X PUT /api/transcripts/segments/{uuid}/speaker -d '{"speaker_uuid": "..."}'`
- Clicking speaker name in transcript shows dropdown
- Selecting different speaker updates segment immediately
- Speaker colors update correctly after reassignment
- No TypeScript errors in frontend
- No Python errors in backend
</success_criteria>
