# Issue #37 Investigation: Speaker Recommendations for Unlabeled Speakers

## Bug Summary
The speaker recommendation system is not suggesting matches from other videos when users are in the edit speakers section **BEFORE** any speaker labeling has occurred. Users should see dropdown suggestions with confidence scores for potential speaker matches across their video library immediately upon viewing unlabeled speakers.

## Problem Analysis

### Current State
- Edit speakers dropdown is empty for unlabeled speakers
- No cross-video suggestions appear before manual labeling
- Voice fingerprint matching only triggers after manual labeling
- Auto-propagation (≥75% confidence) works correctly AFTER labeling

### Expected Behavior
1. User uploads multiple videos with same speakers
2. Videos processed with speaker diarization and voice fingerprinting
3. User goes to edit speakers for any video
4. **BEFORE labeling**, dropdown shows suggestions like:
   - "Speaker from Video B - 87% match"
   - "Speaker from Video C - 82% match"
5. User can accept suggestion or create new identity
6. Auto-propagation continues to work after labeling

## Investigation Plan

### Phase 1: Current Implementation Analysis
- [ ] **Backend Speaker Service** (`backend/app/services/speaker_service.py`)
  - Understand current voice embedding storage and comparison logic
  - Identify where cross-video matching occurs
  - Find why pre-labeling suggestions aren't generated
  
- [ ] **API Endpoints** (`backend/app/api/endpoints/speakers.py`)
  - Review existing speaker suggestion endpoints
  - Check if there's an endpoint for unlabeled speaker suggestions
  - Analyze data structure returned for suggestions

- [ ] **Frontend Components** 
  - `frontend/src/components/EditSpeakers.svelte` - Edit interface behavior
  - `frontend/src/lib/api/speakers.ts` - API integration
  - Check how suggestions are requested and displayed

- [ ] **Database Schema**
  - Review speaker and voice embedding tables
  - Understand relationship between speakers across videos
  - Check if unlabeled speakers have embeddings stored

### Phase 2: Gap Analysis
- [ ] **Missing Backend Logic**
  - Identify gaps in cross-video matching for unlabeled speakers
  - Determine if voice embeddings are computed for unlabeled speakers
  - Check confidence score calculation logic

- [ ] **Missing Frontend Integration**
  - Find where suggestion requests should be made
  - Identify UI components that need updates
  - Check suggestion display formatting

### Phase 3: Solution Design
- [ ] **Backend Enhancement Plan**
  - Design API endpoint for unlabeled speaker suggestions
  - Plan database queries for cross-video embedding comparison
  - Define confidence threshold and response format

- [ ] **Frontend Enhancement Plan**
  - Design suggestion display in edit speakers dropdown
  - Plan API integration for fetching suggestions
  - Design user interaction flow for accepting suggestions

### Phase 4: Implementation
- [ ] **Backend Changes**
  - Implement unlabeled speaker suggestion logic
  - Create/modify API endpoints
  - Add confidence score calculations

- [ ] **Frontend Changes**
  - Update EditSpeakers component
  - Add API calls for suggestions
  - Implement suggestion display and selection

### Phase 5: Testing & Validation
- [ ] **Multi-Video Test Scenario**
  - Upload 3+ videos with same speakers
  - Test suggestion appearance before labeling
  - Verify confidence scores and video references
  - Test suggestion acceptance workflow

- [ ] **Edge Cases**
  - Test with no matching speakers across videos
  - Test with low confidence matches (below threshold)
  - Test with large video libraries for performance

## Key Files to Investigate

### Backend
- `backend/app/services/speaker_service.py` - Core speaker logic
- `backend/app/api/endpoints/speakers.py` - API endpoints
- `backend/app/models/` - Database models
- `backend/app/schemas/` - API schemas

### Frontend  
- `frontend/src/components/EditSpeakers.svelte` - Edit interface
- `frontend/src/lib/api/speakers.ts` - API client
- Related speaker management components

### Database
- Speaker table structure
- Voice embedding storage
- Cross-video speaker relationships

## Technical Questions to Answer

1. **Voice Embeddings**: Are voice embeddings computed and stored for unlabeled speakers during diarization?
2. **Comparison Logic**: Does existing code support comparing embeddings across videos for unlabeled speakers?
3. **API Structure**: Is there an existing pattern for suggestion APIs that can be extended?
4. **Frontend State**: How does the EditSpeakers component currently manage suggestion data?
5. **Performance**: What's the computational cost of cross-video embedding comparison?

## Success Criteria

- [ ] Edit speakers dropdown shows suggestions for unlabeled speakers
- [ ] Suggestions include video source and confidence scores
- [ ] Minimum confidence threshold prevents low-quality suggestions  
- [ ] Users can accept suggestions or ignore them
- [ ] Existing auto-propagation functionality remains intact
- [ ] Performance maintained for large video libraries
- [ ] Clear visual indication of suggestion source and confidence

## Progress Log

### [2025-06-29] - Investigation Started
- Created investigation plan
- Identified key files and components to analyze
- Set up todo tracking for systematic investigation

### [2025-06-29] - Current Implementation Analysis
**Backend API** (`/backend/app/api/endpoints/speakers.py`):
- ✅ The `list_speakers` endpoint has logic to find matches for unlabeled speakers (lines 150-168)
- ✅ Uses `match_speaker_to_known_speakers` to find matches with verified speakers 
- ✅ Gets cross-video matches using `get_speaker_matches` (lines 170-185)
- ✅ Returns `cross_video_matches` in the API response
- ❌ **Issue**: Only matches to VERIFIED speakers with display names, not to other unlabeled speakers

**Speaker Matching Service** (`/backend/app/services/speaker_matching_service.py`):
- ✅ Has `match_speaker_to_known_speakers` function (lines 46-86) - matches to verified speakers only
- ✅ Has `get_speaker_matches` function (lines 534-580) - gets matches from SpeakerMatch table
- ✅ `find_and_store_speaker_matches` function (lines 425-532) stores matches in database
- ✅ Uses OpenSearch for similarity matching
- ❌ **Issue**: The main matching logic only looks for verified speakers, not unlabeled ones

**Frontend** (`/frontend/src/components/SpeakerEditor.svelte`):
- ✅ Shows suggestions if there's a `suggested_name` and `confidence` >= 0.5 (lines 158-166)
- ✅ Displays confidence badges and suggested names
- ❌ **Issue**: Only uses `suggested_name` field, not the `cross_video_matches` data from API
- ❌ **Issue**: No dropdown or selection UI for cross-video matches

**Key Problems Identified:**
1. **Backend**: `match_speaker_to_known_speakers` only matches to verified speakers (line 71-72 in matching service)
2. **Backend**: Need logic to match unlabeled speakers to other unlabeled speakers across videos
3. **Frontend**: Not utilizing the `cross_video_matches` data that's already being returned by the API
4. **Frontend**: No UI for selecting from multiple cross-video suggestions

**Frontend** (`/frontend/src/components/TranscriptDisplay.svelte`):
- ✅ **EXCELLENT**: Comprehensive cross-video matching UI already exists (lines 586-665)
- ✅ Shows detailed match information with confidence scores
- ✅ Displays matches from other videos with expand/collapse functionality
- ✅ Uses the `cross_video_matches` data from API

**Frontend** (`/frontend/src/components/SpeakerEditor.svelte`):
- ❌ **KEY ISSUE**: Only uses `suggested_name` field, completely ignores `cross_video_matches` data
- ❌ Missing dropdown suggestions for cross-video matches
- ❌ This is likely the "edit speakers section" mentioned in the issue

**Database Schema** (`/backend/app/models/media.py`):
- ✅ SpeakerMatch table exists with speaker1_id, speaker2_id, and confidence
- ✅ Speaker table has all necessary fields: suggested_name, confidence, display_name, verified

**Root Cause Analysis:**
1. **Backend Issue**: `match_speaker_to_known_speakers` only matches to VERIFIED speakers with display_names (lines 71-72 in SpeakerMatchingService)
2. **Frontend Issue**: SpeakerEditor.svelte (the "edit speakers" interface) doesn't use cross_video_matches data
3. **UI Location Issue**: TranscriptDisplay has the cross-video UI, but SpeakerEditor is likely where users go to "edit speakers"

**Solution Requirements:**
1. Modify backend to generate cross-video matches for unlabeled speakers to other unlabeled speakers  
2. Update SpeakerEditor.svelte to show cross-video match suggestions like TranscriptDisplay does
3. Ensure the suggestions appear BEFORE manual labeling

## Solution Design

### Backend Changes Required

1. **Modify SpeakerMatchingService.match_speaker_to_known_speakers()** (`/backend/app/services/speaker_matching_service.py:46-86`)
   - Currently only matches to verified speakers with display_names (lines 71-72)
   - **Change**: Add logic to also find matches from other unlabeled speakers across videos
   - **Implementation**: Create new method `find_unlabeled_speaker_matches()` that searches for similar embeddings regardless of verification status

2. **Update speakers API endpoint** (`/backend/app/api/endpoints/speakers.py:143-211`)
   - Already returns cross_video_matches (line 198)
   - **Enhance**: Ensure cross_video_matches includes unlabeled-to-unlabeled suggestions
   - **Add**: Include video source information and confidence scoring for suggestions

### Frontend Changes Required

1. **SpeakerEditor.svelte Enhancements** (`/frontend/src/components/SpeakerEditor.svelte`)
   - Currently only shows `suggested_name` field (lines 158-166)
   - **Add**: Cross-video match suggestions UI similar to TranscriptDisplay.svelte (lines 586-665)
   - **Add**: Dropdown with suggestions showing:
     - "Speaker from Video B - 87% match"
     - Confidence badges and video references
     - Ability to select suggestions

2. **UI/UX Design**
   - Show suggestions BEFORE manual labeling (when speaker.display_name is empty)
   - Display confidence percentages and source video information
   - Allow users to accept suggestions or type custom names
   - Maintain existing functionality for verified speakers

### Implementation Plan

#### Phase 1: Backend Enhancement
1. Create `find_unlabeled_speaker_matches()` method in SpeakerMatchingService
2. Modify `list_speakers()` endpoint to populate cross_video_matches for unlabeled speakers
3. Test backend API returns correct cross-video matches

#### Phase 2: Frontend Enhancement  
1. Add cross-video suggestions UI to SpeakerEditor.svelte
2. Integrate suggestion selection logic
3. Test complete user workflow

#### Phase 3: Integration Testing
1. Test with multiple videos containing same speakers
2. Verify suggestions appear before labeling
3. Confirm auto-propagation still works after labeling

### Key Implementation Details

**Backend - New Method Structure:**
```python
def find_unlabeled_speaker_matches(self, embedding: np.ndarray, user_id: int, exclude_speaker_id: int) -> List[Dict[str, Any]]:
    """Find matches to unlabeled speakers across videos"""
    # Use OpenSearch to find similar embeddings
    # Return speaker matches regardless of verification status
    # Include video source and confidence information
```

**Frontend - Enhanced SpeakerEditor:**
- Add cross_video_matches conditional rendering
- Show suggestion dropdown with confidence scores
- Include video source information ("from Video B")
- Maintain existing input field functionality

### Expected User Flow After Implementation

1. User uploads Video A, B, C (same speaker in all)
2. Videos processed with speaker diarization and voice fingerprinting  
3. User goes to Video A → Edit Speakers button
4. SpeakerEditor shows "SPEAKER_1" with dropdown containing:
   - "Speaker from Video B - 89% match"
   - "Speaker from Video C - 85% match"
5. User sees that SPEAKER_1 matches speakers in other videos but needs to provide a unique identifiable name (e.g., "John", "Interviewer") to label and propagate across all matching videos
6. Auto-propagation applies to high-confidence matches (≥75%)

**Next Steps:**
1. ✅ Complete solution design
2. ✅ Implement backend changes for unlabeled speaker matching
3. ✅ Implement frontend changes in SpeakerEditor.svelte 
4. ⏳ Test complete workflow with multiple videos

## Implementation Summary

### Backend Changes Completed ✅

1. **Added `find_unlabeled_speaker_matches()` method** in `SpeakerMatchingService` (lines 88-160)
   - Uses OpenSearch to find similar embeddings across videos
   - Returns matches regardless of verification status
   - Includes video source information and confidence scores

2. **Enhanced speakers API endpoint** in `/api/speakers/` (lines 173-196)
   - Added logic to find cross-video matches for unlabeled speakers  
   - Merges unlabeled matches with existing cross_video_matches
   - Sets confidence score for UI display

### Frontend Changes Completed ✅

1. **Enhanced SpeakerEditor.svelte** with cross-video suggestions UI
   - Added `cross_video_matches` and `showMatches` to speaker data structure
   - Added collapsible suggestion card showing matches from other videos
   - Includes confidence badges and video source information
   - Added help text: "Provide a name to label this speaker across all matching videos"

2. **UI Features Added:**
   - Expandable/collapsible match display with smooth transitions
   - Confidence percentages with color coding
   - Video source information (truncated titles)
   - Clean, accessible interface matching existing design patterns

### Key Implementation Details

- **Threshold**: Uses 50% confidence minimum for displaying suggestions
- **UI Logic**: Only shows for unlabeled speakers (`!speaker.suggested_name && !speaker.verified && !speaker.display_name`)
- **User Experience**: Clear messaging that user needs to provide identifiable name to propagate across videos
- **Performance**: Limits display to top 3 matches with "...and X more" indicator

### Testing Ready 🧪
- Services are running with hot reload enabled
- Implementation complete and ready for multi-video testing
- Expected workflow: Upload multiple videos → Edit Speakers → See cross-video suggestions → Label speaker → Auto-propagation

---

*This document will be updated throughout the investigation and implementation process.*