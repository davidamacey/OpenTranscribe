---
sidebar_position: 2
---

# Speaker Diarization

OpenTranscribe identifies different speakers and segments audio by "who spoke when" using PyAnnote.audio.

## PyAnnote.audio Technology

**State-of-the-art speaker diarization**:

- Neural network-based speaker detection
- Voice activity detection (VAD)
- Speaker embedding extraction
- Overlap detection
- Clustering for speaker assignment

## How It Works

### Processing Steps

1. **Voice Activity Detection**: Identify speech vs silence
2. **Speaker Embedding**: Extract voice fingerprints
3. **Overlap Detection**: Find overlapping speakers
4. **Clustering**: Group similar voices
5. **Speaker Assignment**: Label each segment

### Speaker Fingerprinting

Each speaker gets a unique voice embedding:
- 192-dimensional vector
- Captures voice characteristics
- Used for cross-video matching
- Enables speaker recognition

## Speaker Management

### Automatic Detection

- Detects 1-50+ speakers automatically
- No manual configuration required
- Adaptive to conversation dynamics
- Handles speaker interruptions

### Speaker Profiles

**Create persistent speaker profiles**:

1. Label "Speaker 1" as "John Doe"
2. System creates global profile
3. Profile matches across all videos
4. Voice fingerprint stored for matching

### Cross-Video Recognition

**Intelligent speaker matching**:

- Voice embedding comparison
- Similarity scoring (0-100%)
- High-confidence auto-linking (greater than 85%)
- Manual verification for medium confidence
- Speaker appears in multiple recordings

**Example**:
```
Video 1: John Doe speaks
Video 2: Unknown speaker detected
System: 92% match → Suggests "John Doe"
```

## Speaker Analytics

### Talk Time Analysis

- Total speaking duration per speaker
- Percentage of conversation
- Speaking turns count
- Average turn length

### Interaction Patterns

- Interruption detection
- Turn-taking analysis
- Overlap frequency
- Silence ratio

### Speaking Metrics

- **Words per minute (WPM)**: Speaking pace
- **Question frequency**: Questions asked
- **Longest monologue**: Continuous speaking time
- **Participation balance**: Equal participation score

## AI-Powered Identification

With LLM configured, get smart suggestions:

### Context-Based Identification

- Analyzes conversation content
- Identifies speakers by role/expertise
- Detects names mentioned in conversation
- Provides confidence scores

**Example**:
```
Context: "As the CEO mentioned earlier..."
AI Suggestion: "John Smith (CEO)" - 85% confidence
```

### Verification Workflow

1. AI suggests speaker name
2. Review suggestion + confidence
3. Accept or manually correct
4. System learns from corrections

## Configuration

### Detection Range

Adjust speaker count expectations:

```bash
# .env configuration
MIN_SPEAKERS=1   # Minimum speakers
MAX_SPEAKERS=20  # Maximum speakers (no hard limit)
```

**Use Cases**:
- 1-1 interview: MIN=2, MAX=2
- Team meeting: MIN=3, MAX=10
- Conference panel: MIN=5, MAX=15
- Large event: MIN=10, MAX=50+

**Note**: PyAnnote has no hard maximum - can handle 50+ speakers for large conferences.

### Quality Settings

**For best results**:
- Clear audio (minimal background noise)
- Distinct speakers (different voices)
- Good microphone quality
- Minimal speaker overlap

## Speaker Display

### Visual Representation

- **Color coding**: Each speaker gets unique color
- **Speaker labels**: Names shown in transcript
- **Timeline view**: Speaker segments visualized
- **Speaker list**: All speakers with talk time

### Filtering & Search

- Filter transcript by speaker
- Search within speaker's words
- Export single speaker's content
- Compare speaker contributions

## Advanced Features

### Overlap Detection

Identifies when multiple speakers talk simultaneously:
- Overlap segments highlighted
- Primary/secondary speaker identification
- Overlap duration tracking
- Interruption analysis

### Speaker Verification Status

Track identification confidence:

- ✅ **Verified**: Manually confirmed
- 🤖 **AI Suggested**: LLM identification
- 🎯 **Auto-Matched**: Voice fingerprint match (greater than 85%)
- ❓ **Unverified**: Default detection

### Merge & Split (Enhanced in v0.2.0)

**Merge speakers** (New UI):
- Visual speaker merge interface with segment preview
- Select primary speaker and merge others into it
- Automatic segment reassignment
- Consolidate speaker profiles across files
- Update all segments automatically

**Split speakers**:
- Separate incorrectly merged speakers
- Re-assign segments
- Create new profiles

### Per-File Speaker Settings (New in v0.2.0)

Configure speaker detection for each upload or reprocess:

- **Upload dialog**: Set min/max speakers before transcription
- **Reprocess dialog**: Adjust speaker range for re-transcription
- **User preferences**: Save default settings in Settings → Transcription
  - **Always prompt**: Show speaker settings on every upload
  - **Use defaults**: Skip dialog, use system defaults (1-20)
  - **Use custom**: Skip dialog, use your saved min/max values

## Performance

### Accuracy

- Speaker detection: ~95% on clear audio
- Voice matching: ~90% across videos
- Overlap detection: ~85% accuracy

### Processing Time

- Diarization adds ~30% to transcription time
- Example: 1-hour audio = ~65 seconds total
- Parallel with transcription (optimized)

### Resource Usage

- **VRAM**: Additional 2GB for diarization
- **Total**: 8GB VRAM recommended
- **CPU mode**: Slower but functional

## Use Cases

### Business Meetings

- Identify all participants
- Track who spoke when
- Generate speaker-attributed notes
- Analyze participation balance

### Interviews

- Separate interviewer and subject
- Quote attribution
- Response time analysis
- Follow-up question tracking

### Podcasts

- Multi-host identification
- Guest speaker tracking
- Episode analytics
- Automated show notes

### Legal/Medical

- Court proceedings transcription
- Medical consultation records
- Deposition transcripts
- Accurate speaker attribution

## Troubleshooting

### Too Many Speakers Detected

**Solutions**:
- Lower MAX_SPEAKERS
- Improve audio quality
- Merge duplicate speakers manually

### Too Few Speakers Detected

**Solutions**:
- Increase MAX_SPEAKERS
- Check audio has multiple distinct voices
- Verify speakers have different vocal characteristics

### Poor Speaker Separation

**Causes**:
- Similar-sounding voices
- Poor audio quality
- Heavy background noise

**Solutions**:
- Use better microphones
- Separate speakers physically
- Post-process manually

## Next Steps

- [Speaker Management Guide](../user-guide/speaker-management.md) - How to use
- [First Transcription](../getting-started/first-transcription.md) - Try it
- [LLM Integration](./llm-integration.md) - Enable AI suggestions
