<objective>
Implement a speaker merge UI that allows users to select multiple speakers and merge them into one target speaker.

The backend merge endpoint already exists at `POST /api/speakers/{speaker_uuid}/merge/{target_speaker_uuid}`. This task focuses on creating the frontend UI to use this endpoint effectively.
</objective>

<context>
OpenTranscribe is a transcription application where PyAnnote speaker diarization sometimes detects too many speakers (e.g., 19 speakers when there are only 7 actual people). Users need to consolidate/merge duplicate speakers.

Read these files to understand the current architecture:
- `@frontend/src/routes/files/[id]/+page.svelte` - Main file detail page
- `@frontend/src/components/TranscriptDisplay.svelte` - Transcript display with speaker info
- `@frontend/src/components/EditSpeakersButton.svelte` - Existing speaker editor toggle
- `@frontend/src/lib/api/` - API client patterns
- `@backend/app/api/endpoints/speakers.py` - Existing merge endpoint (lines with "merge")

Follow patterns and conventions in `@CLAUDE.md`.
</context>

<requirements>
1. **Speaker List with Multi-Select**
   - Display all speakers for the current media file in a list/grid
   - Each speaker shows: display name (or original name), segment count, color indicator
   - Checkbox for each speaker to enable multi-selection
   - Visual distinction for selected speakers

2. **Merge Controls**
   - "Merge Selected" button (disabled until 2+ speakers selected)
   - When clicked, show dialog/dropdown to pick the TARGET speaker (the one to keep)
   - Target selection should only show from the selected speakers
   - Clear explanation: "Merge X speakers into [target]. All segments will be reassigned."

3. **Merge Execution**
   - Call existing merge endpoint for each source speaker: `POST /api/speakers/{source}/merge/{target}`
   - Show loading state during merge operations
   - Handle errors gracefully with toast notifications
   - Refresh speaker list and transcript after successful merge

4. **Integration**
   - Add to existing speaker editing flow (when `isEditingSpeakers` is true)
   - Use existing toast store for notifications
   - Maintain existing speaker color system
</requirements>

<implementation>
Create or modify these files:

1. `./frontend/src/components/SpeakerMerge.svelte` (NEW)
   - Self-contained component for speaker merge UI
   - Props: `speakers` (array), `fileUuid` (string)
   - Events: `merged` (dispatched after successful merge)

2. `./frontend/src/lib/api/speakers.ts` (NEW or extend existing)
   - Add `mergeSpeakers(sourceUuid: string, targetUuid: string)` function
   - Use existing axios instance pattern

3. `./frontend/src/components/TranscriptDisplay.svelte` or `./frontend/src/routes/files/[id]/+page.svelte`
   - Integrate SpeakerMerge component in speaker editing mode
   - Handle `merged` event to refresh data

Follow existing UI patterns:
- Use CSS variables for theming (--primary-color, --background-color, etc.)
- Support both light and dark modes
- Use existing button styles (.btn, .btn-primary, .btn-secondary)
- Use existing toast store for notifications
</implementation>

<output>
Files to create/modify:
- `./frontend/src/components/SpeakerMerge.svelte` - New merge UI component
- `./frontend/src/lib/api/speakers.ts` - API client for speaker operations
- Integration into existing page/component for speaker editing mode
</output>

<verification>
Before completing, verify:
1. Component renders speaker list with checkboxes
2. Selecting 2+ speakers enables the merge button
3. Target speaker selection works correctly
4. Merge API calls succeed and UI updates
5. Error handling displays appropriate messages
6. Both light and dark themes work correctly
7. Run `npm run check` in frontend directory to verify no TypeScript errors
</verification>

<success_criteria>
- Users can select multiple speakers via checkboxes
- Users can designate which speaker to merge into (target)
- Merge operation calls backend and updates UI
- Clear visual feedback during and after merge
- No TypeScript errors
</success_criteria>
