---
sidebar_position: 2
---

# Speaker Management

OpenTranscribe provides powerful speaker diarization and management features to identify and organize speakers across all your media files.

## Speaker Diarization

**Automatic speaker detection** using PyAnnote.audio identifies different speakers and segments audio by "who spoke when".

### Enabling Speaker Diarization

1. Configure HuggingFace token (required):
   - See [HuggingFace Setup](../installation/huggingface-setup.md)

2. Enable in UI settings or `.env`:
   ```bash
   MIN_SPEAKERS=1
   MAX_SPEAKERS=20  # Increase for large meetings/conferences
   ```

3. Process files - speakers automatically detected

## Speaker Profiles

### Creating Speaker Profiles

Speakers are automatically identified as "Speaker 1", "Speaker 2", etc. You can create persistent profiles:

1. Click on speaker label
2. Enter speaker name
3. Save profile

**Auto-profile creation**: When you label a speaker, OpenTranscribe automatically creates a global profile that can be matched across videos.

### Cross-Video Speaker Recognition

OpenTranscribe uses **voice fingerprinting** to identify the same speaker across different media files:

- Voice embeddings analyzed for similarity
- High-confidence matches auto-linked
- Speaker labels propagate across videos
- View all appearances of a speaker

### LLM-Powered Identification

If LLM is configured, get AI-powered speaker name suggestions based on:
- Conversation context
- Topics discussed
- Speaking patterns
- Professional role indicators

## Speaker Analytics

View comprehensive speaker statistics:

- **Talk Time**: Total speaking duration
- **Word Count**: Words spoken
- **Turn-Taking**: Number of speaking turns
- **Interruptions**: Detected interruptions
- **Speaking Pace**: Words per minute
- **Question Frequency**: Questions asked
- **Cross-Media Appearances**: Videos featuring speaker

## Managing Speakers

### Edit Speaker Labels

1. Click speaker name in transcript
2. Edit name
3. Changes apply to all segments

### Merge Speakers

If diarization incorrectly splits one speaker:

1. Select segments
2. Assign to same speaker profile
3. Consolidate analytics

### Speaker Verification Status

Track speaker identification confidence:
- ✅ Verified: Manually confirmed
- 🤖 AI Suggested: LLM identification
- 🎯 Auto-Matched: Voice fingerprint match
- ❓ Unverified: Default detection

## Configuration

### Adjust Speaker Detection Range

For meetings with many participants:

```bash
# .env configuration
MIN_SPEAKERS=2       # Minimum speakers to detect
MAX_SPEAKERS=50      # Maximum speakers (no hard limit)
```

**Note**: PyAnnote can handle 50+ speakers for large conferences.

### Speaker Display Preferences

Customize in UI settings:
- Color coding by speaker
- Show/hide speaker analytics
- Filter by speaker
- Export with speaker labels

## Troubleshooting

### All Speakers Shown as "Speaker 1"

**Causes**:
- HuggingFace token not configured
- Single speaker in audio
- Poor audio quality

**Solutions**:
- Verify HuggingFace setup
- Check audio has multiple speakers
- Ensure clear audio quality

### Too Many/Few Speakers Detected

**Solutions**:
```bash
# Adjust detection range
MIN_SPEAKERS=1
MAX_SPEAKERS=30  # Tune based on actual speaker count
```

### Speaker Segments Fragmented

**Cause**: Diarization split one speaker into multiple

**Solution**: Manually merge segments to same profile

## Best Practices

1. **Label Important Speakers**: Create profiles for frequent speakers
2. **Verify AI Suggestions**: Review LLM-suggested names
3. **Use Consistent Names**: Maintain naming convention
4. **Review Cross-Video Matches**: Confirm auto-matched speakers
5. **Adjust Detection Range**: Tune MIN/MAX_SPEAKERS for your use case

## Next Steps

- [First Transcription](../getting-started/first-transcription.md)
- [AI Summarization](./ai-summarization.md)
- [Search & Filters](./search-and-filters.md)
