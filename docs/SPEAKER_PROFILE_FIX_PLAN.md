# Speaker Profile Management System - Fix Implementation Plan

## Overview
This document outlines the complete fix for the speaker profile management system to ensure proper speaker identification, profile creation, cross-video matching, and suggestion display. The system should work intuitively from a fresh deployment with no migration needed.

## Current Issues
1. Profile embeddings are never created or updated when speakers are labeled
2. Profile search is incorrectly searching for speakers with profile_id instead of actual profile embeddings
3. All speakers incorrectly show Joe Rogan suggestions at 100% confidence
4. Cross-media "appears in" functionality not working
5. Missing LLM and voice embedding suggestions

## System Workflow

### 1. First Video Upload
```
Video → WhisperX → Speakers (SPEAKER_00, etc.) → Embeddings stored
                 ↓
         LLM Analysis (if configured) → Suggested names stored
```

### 2. User Labels Speaker
```
User labels SPEAKER_00 as "Joe Rogan"
    ↓
Create/Find SpeakerProfile(name="Joe Rogan")
    ↓
Assign speaker.profile_id
    ↓
Calculate profile embedding (average of all "Joe Rogan" speakers)
    ↓
Store profile embedding in OpenSearch (separate from speaker embeddings)
```

### 3. Second Video Upload
```
New speakers → Compare embeddings to:
    1. Profile embeddings (for auto-labeling)
    2. Other speaker embeddings (for suggestions)
    ↓
If match found with profile → Auto-label with profile name
    ↓
Update profile embedding with new speaker
```

### 4. Viewing Speakers
```
For each speaker, show:
    1. LLM suggestions (from import, stored in suggested_name)
    2. Voice matches (from embedding similarity to other speakers)
    3. Profile matches (from embedding similarity to profiles)
    ↓
"Appears in" shows all videos with same profile_id
```

## Implementation Changes Required

### 1. Profile Embedding Storage Architecture

Store profile embeddings separately from speaker embeddings in OpenSearch:
- Speaker documents: id="1", "2", "3" (speaker IDs)
- Profile documents: id="profile_1", "profile_2" (prefixed profile IDs)

### 2. Fix Speaker Labeling → Profile Creation

**File: `backend/app/api/endpoints/speakers.py`**

```python
def update_speaker(...):
    if speaker_update.display_name and speaker_update.display_name.strip():
        # Auto-create or find profile
        profile = db.query(SpeakerProfile).filter(
            SpeakerProfile.name == speaker_update.display_name,
            SpeakerProfile.user_id == current_user.id
        ).first()

        if not profile:
            # Create new profile
            profile = SpeakerProfile(
                name=speaker_update.display_name,
                user_id=current_user.id,
                uuid=str(uuid.uuid4()),
                description=f"Auto-created profile for {speaker_update.display_name}"
            )
            db.add(profile)
            db.flush()

        speaker.profile_id = profile.id
        speaker.verified = True
        db.commit()

        # CRITICAL: Calculate and store profile embedding
        ProfileEmbeddingService.update_profile_embedding(db, profile.id)
```

### 3. Fix Profile Embedding Service

**File: `backend/app/services/profile_embedding_service.py`**

```python
def update_profile_embedding(db, profile_id):
    # Get all speakers assigned to this profile
    speakers = db.query(Speaker).filter(Speaker.profile_id == profile_id).all()

    embeddings = []
    for speaker in speakers:
        embedding = get_speaker_embedding(speaker.id)
        if embedding:
            embeddings.append(embedding)

    if embeddings:
        # Calculate average embedding
        avg_embedding = np.mean(embeddings, axis=0)

        # Store as profile document in OpenSearch
        from app.services.opensearch_service import store_profile_embedding
        store_profile_embedding(
            profile_id=profile_id,
            profile_name=profile.name,
            embedding=avg_embedding.tolist(),
            speaker_count=len(embeddings),
            user_id=profile.user_id
        )
```

### 4. Add Profile Embedding Storage to OpenSearch

**File: `backend/app/services/opensearch_service.py`**

```python
def store_profile_embedding(profile_id, profile_name, embedding, speaker_count, user_id):
    """Store profile embedding with distinct document type"""
    doc = {
        "document_type": "profile",  # CRITICAL: Distinguish from speakers
        "profile_id": profile_id,
        "profile_name": profile_name,
        "user_id": user_id,
        "embedding": embedding,
        "speaker_count": speaker_count,
        "updated_at": datetime.now().isoformat()
    }

    # Use prefixed ID to avoid conflicts with speaker documents
    opensearch_client.index(
        index=settings.OPENSEARCH_SPEAKER_INDEX,
        body=doc,
        id=f"profile_{profile_id}"
    )
```

### 5. Fix Profile Search Logic

**File: `backend/app/services/smart_speaker_suggestion_service.py`**

```python
def _get_profile_suggestions_optimized(embedding, user_id, db, threshold):
    # Search ONLY profile documents, not speakers with profile_id
    query = {
        "size": 10,
        "query": {
            "bool": {
                "must": [
                    {"term": {"document_type": "profile"}},  # CRITICAL: Only profiles
                    {"term": {"user_id": user_id}}
                ],
                "filter": {
                    "script_score": {
                        "query": {"match_all": {}},
                        "script": {
                            "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                            "params": {"query_vector": embedding.tolist()}
                        }
                    }
                }
            }
        },
        "min_score": threshold
    }

    response = opensearch_client.search(index=settings.OPENSEARCH_SPEAKER_INDEX, body=query)

    # Process results correctly
    suggestions = []
    for hit in response["hits"]["hits"]:
        score = (hit["_score"] - 1.0)  # Remove the +1.0 we added
        source = hit["_source"]

        suggestions.append({
            "profile_id": source["profile_id"],
            "profile_name": source["profile_name"],
            "confidence": score,
            "speaker_count": source["speaker_count"],
            "source": "profile_embedding"
        })

    return suggestions
```

### 6. Implement Three Types of Suggestions

**File: `backend/app/services/smart_speaker_suggestion_service.py`**

```python
def consolidate_suggestions(speaker_id, user_id, db, threshold=0.5):
    suggestions = []
    speaker = db.query(Speaker).filter(Speaker.id == speaker_id).first()
    embedding = get_speaker_embedding(speaker_id)

    # 1. LLM suggestions (from import process)
    if speaker.suggested_name and speaker.confidence:
        suggestions.append({
            "type": "llm_analysis",
            "name": speaker.suggested_name,
            "confidence": speaker.confidence,
            "source": "llm_analysis",
            "reason": "AI analysis of conversation context"
        })

    # 2. Profile suggestions (speaker-to-profile matching)
    profile_suggestions = _get_profile_suggestions_optimized(embedding, user_id, db, threshold)
    for ps in profile_suggestions:
        ps["type"] = "profile"
        ps["source"] = "profile_embedding"
        suggestions.append(ps)

    # 3. Voice suggestions (speaker-to-speaker matching)
    voice_suggestions = _get_voice_suggestions(embedding, user_id, db, threshold)
    for vs in voice_suggestions:
        vs["type"] = "voice"
        vs["source"] = "voice_embedding"
        suggestions.append(vs)

    # Deduplicate by name, keeping highest confidence
    unique_suggestions = {}
    for s in suggestions:
        name = s.get("name") or s.get("profile_name")
        if name not in unique_suggestions or s["confidence"] > unique_suggestions[name]["confidence"]:
            unique_suggestions[name] = s

    return list(unique_suggestions.values())
```

### 7. Add Voice Suggestions (Speaker-to-Speaker)

**File: `backend/app/services/smart_speaker_suggestion_service.py`**

```python
def _get_voice_suggestions(embedding, user_id, db, threshold):
    # Search for similar speakers (not profiles)
    query = {
        "size": 10,
        "query": {
            "bool": {
                "must": [
                    {"term": {"user_id": user_id}},
                    {"bool": {
                        "must_not": {"exists": {"field": "document_type"}}  # Exclude profiles
                    }}
                ],
                "filter": {
                    "script_score": {
                        "query": {"match_all": {}},
                        "script": {
                            "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                            "params": {"query_vector": embedding.tolist()}
                        }
                    }
                }
            }
        },
        "min_score": threshold
    }

    response = opensearch_client.search(index=settings.OPENSEARCH_SPEAKER_INDEX, body=query)

    # Group by display_name to consolidate
    voice_matches = {}
    for hit in response["hits"]["hits"]:
        source = hit["_source"]
        if source.get("display_name") and not source["display_name"].startswith("SPEAKER_"):
            name = source["display_name"]
            score = hit["_score"] - 1.0

            if name not in voice_matches or score > voice_matches[name]["confidence"]:
                voice_matches[name] = {
                    "name": name,
                    "confidence": score,
                    "media_file_id": source.get("media_file_id")
                }

    return list(voice_matches.values())
```

### 8. Fix Speaker Matching on New Video Upload

**File: `backend/app/services/speaker_matching_service.py`**

```python
def process_speaker(...):
    # When auto-accepting a match to a profile
    if match["auto_accept"] and match.get("profile_id"):
        speaker.profile_id = match["profile_id"]
        speaker.verified = True
        speaker.display_name = match["suggested_name"]
        db.flush()

        # Update speaker in OpenSearch
        update_speaker_profile(speaker.id, speaker.profile_id, True)

        # CRITICAL: Update profile embedding with new speaker
        ProfileEmbeddingService.update_profile_embedding(db, speaker.profile_id)

        # Propagate to similar speakers
        self._propagate_profile_assignment(speaker.id, speaker.profile_id, user_id)
```

### 9. Fix Frontend Cross-Media Calls

**File: `frontend/src/components/SpeakerProfileManager.svelte`**

```svelte
<!-- Remove restrictive conditions, make all speakers clickable -->
{#each sortedSpeakers as speaker}
  <button
    class="speaker-card {getSpeakerStatus(speaker)} clickable"
    on:click={() => handleSpeakerClick(speaker)}
  >
    <!-- Speaker content -->
  </button>
{/each}

<!-- Ensure handleSpeakerClick always fetches cross-media -->
<script>
async function handleSpeakerClick(speaker) {
  selectedSpeaker = speaker;

  // Always fetch both suggestions and cross-media occurrences
  const [suggestionsResponse, occurrencesResponse] = await Promise.all([
    axiosInstance.get(`/api/speaker-profiles/speakers/${speaker.id}/suggestions`),
    axiosInstance.get(`/api/speakers/${speaker.id}/cross-media`)
  ]);

  suggestions = suggestionsResponse.data;
  crossMediaOccurrences = occurrencesResponse.data;
  showVerification = true;
}
</script>
```

## User Experience Flow

From a fresh deployment (`./opentr.sh reset dev`), the system should work intuitively:

### User Journey:

1. **Upload First Video**
   - System identifies speakers (SPEAKER_00, SPEAKER_01, etc.)
   - Embeddings are automatically calculated and stored
   - LLM suggestions generated (if configured)
   - User sees unlabeled speakers with suggestions

2. **Label a Speaker**
   - User clicks on SPEAKER_00 and labels as "Joe Rogan"
   - System automatically:
     - Creates a SpeakerProfile for "Joe Rogan"
     - Calculates profile embedding from speaker embedding
     - Stores profile embedding in OpenSearch
   - User sees speaker now verified with profile badge

3. **Upload Second Video**
   - System compares new speakers to profile embeddings
   - Automatically labels matching speakers as "Joe Rogan"
   - Updates Joe Rogan's profile embedding with new data
   - User sees speakers auto-labeled correctly

4. **View Any Speaker**
   - Click shows all three suggestion types:
     - LLM: Context-based name suggestions
     - Voice: Similar speakers from other videos
     - Profile: Matching speaker profiles
   - "Appears in" dropdown shows all videos with this speaker/profile

### Automatic Behind-the-Scenes:
- Profile creation on first label
- Profile embedding calculation and updates
- Cross-video speaker matching
- Embedding averaging for better accuracy over time

## Testing Checklist

1. [ ] Upload video 1 → Speakers created with embeddings
2. [ ] Label speaker as "Joe Rogan" → Profile created with embedding
3. [ ] Upload video 2 → Joe Rogan auto-matched via profile embedding
4. [ ] Click any speaker → See LLM + Voice + Profile suggestions
5. [ ] "Appears in" shows both videos for Joe Rogan
6. [ ] Confidence scores are accurate (not all 100%)
7. [ ] Different speakers show different suggestions (not all Joe Rogan)
8. [ ] Profile embeddings update when new speakers are added

## Key Principles

1. **Profile embeddings are separate** from speaker embeddings in OpenSearch
2. **Three suggestion types** must always be available: LLM, Voice, Profile
3. **Profile embeddings are averaged** from all assigned speaker embeddings
4. **Auto-create profiles** when speakers are first labeled
5. **Update profile embeddings** whenever speakers are added/removed
6. **Cross-media search** uses profile_id to find all occurrences

## Performance Considerations

1. Use batch operations when updating multiple profiles
2. Cache profile embeddings for frequently accessed profiles
3. Use OpenSearch's native kNN search for efficiency
4. Limit suggestion results to top N matches
5. Index profile documents separately for faster queries

## Error Handling

1. Handle missing embeddings gracefully
2. Fall back to full recalculation if incremental update fails
3. Log all profile embedding updates for debugging
4. Validate embeddings before storage
5. Handle OpenSearch connection failures

## Implementation Order

1. **Phase 1: Core Profile System** (Critical)
   - Add store_profile_embedding to OpenSearch service
   - Fix profile embedding creation on speaker labeling
   - Ensure profile embeddings are calculated as averages
   - Store profiles with document_type="profile" in OpenSearch

2. **Phase 2: Fix Search & Matching** (Critical)
   - Fix profile search to query document_type="profile" only
   - Fix speaker-to-profile matching for new videos
   - Update profile embeddings when new speakers are added
   - Fix confidence scoring to show actual similarity scores

3. **Phase 3: Three-Type Suggestion System** (Important)
   - Show LLM suggestions from import process
   - Add voice suggestions (speaker-to-speaker matching)
   - Fix profile suggestions (speaker-to-profile matching)
   - Ensure all three types always appear

4. **Phase 4: Frontend Integration** (Important)
   - Fix cross-media endpoint calling for all speakers
   - Remove restrictive click conditions
   - Display all suggestion types with proper badges
   - Show "appears in" dropdown with all videos

5. **Phase 5: Testing & Polish** (Final)
   - Test with `./opentr.sh reset dev` for fresh start
   - Verify intuitive user flow
   - Optimize OpenSearch queries for speed
   - Ensure proper error handling