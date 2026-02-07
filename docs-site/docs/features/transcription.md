---
sidebar_position: 1
---

# Transcription Engine

OpenTranscribe uses WhisperX with the faster-whisper backend for state-of-the-art speech recognition.

## WhisperX Technology

**WhisperX** combines multiple AI models for superior transcription:

- **Whisper**: OpenAI's robust speech recognition model
- **Faster-Whisper**: Optimized inference engine (4-8x faster)
- **WAV2VEC2**: Word-level timestamp alignment
- **Voice Activity Detection**: Precise speech detection

## Performance

### Speed

- **GPU**: 70x realtime (1-hour file in ~50 seconds)
- **CPU**: 0.5-1x realtime (slower than playback)
- **Batch Processing**: Process multiple files concurrently

### Accuracy

OpenTranscribe uses the **large-v3-turbo** model by default (as of v0.4.0):

- Word Error Rate (WER): ~3-5% on clean audio
- Robust to accents and speech variations
- Handles technical terminology well
- Works with background noise
- **6x faster than previous large-v2 model**

## Model Selection

Choose the right Whisper model for your use case:

| Use Case | Model | Speed | Accuracy | Why |
|----------|-------|-------|----------|-----|
| **English audio** | `large-v3-turbo` | **6x faster** | Excellent | Default, fastest option |
| **Spanish/French/German/Japanese** | `large-v3-turbo` | **6x faster** | Excellent | Good accuracy, fast |
| **Thai/Cantonese/Vietnamese** | `large-v3` | Standard | Better | Turbo has reduced accuracy for these |
| **Translation to English** | `large-v3` | Standard | Excellent | **Turbo cannot translate** |
| **Maximum accuracy needed** | `large-v3` | Standard | **Best** | Slightly better than turbo |

**Critical Note**: The `large-v3-turbo` model cannot translate audio to English. If you enable "Translate to English" in settings, you must switch to `large-v3`.

**Configuration**:

Set the model in Settings → Transcription → Model Selection, or via environment variable:

```bash
WHISPER_MODEL=large-v3-turbo  # Default (6x faster)
WHISPER_MODEL=large-v3        # For translation or maximum accuracy
WHISPER_MODEL=large-v2        # Legacy (not recommended)
```

## Multi-Language Support

**100+ Languages Supported**:

OpenTranscribe supports transcription in over 100 languages, including:

- English (US, UK, Australian, Indian)
- Spanish, French, German, Italian, Portuguese
- Russian, Japanese, Chinese (Simplified/Traditional)
- Arabic, Hindi, Korean, Vietnamese, Thai
- Dutch, Polish, Turkish, Swedish, Norwegian
- And 80+ more languages from the Whisper model

### Language Settings (New in v0.2.0)

**User-Configurable Options**:

1. **Source Language**:
   - Auto-detect (default) - Whisper automatically identifies the language
   - Manual selection - Specify language for improved accuracy

2. **Translation to English**:
   - Toggle on/off - Choose to keep original language or translate
   - Default: Off (keeps original language)
   - Useful when you need English output from foreign audio

3. **Word-Level Timestamp Support**:
   - ~42 languages have full word-level alignment
   - Languages without alignment fall back to segment-level timestamps
   - UI shows alignment support indicator for each language

**Language Settings Location**: Settings → Transcription → Language Settings

## Word-Level Timestamps

Every word gets precise timing:

```json
{
  "word": "OpenTranscribe",
  "start": 1.24,
  "end": 1.89,
  "confidence": 0.98
}
```

**Benefits**:
- Click transcript to seek in media player
- Precise speaker segment boundaries
- Accurate subtitle generation
- Time-stamped comments

## Audio Processing

### Waveform Visualization

- Visual representation of audio
- Click-to-seek functionality
- Speaker segment highlighting
- Real-time progress indicator

### Audio Enhancement

- Noise reduction (automatic)
- Volume normalization
- Sample rate conversion
- Multi-channel audio support

## Available Models (Advanced)

While `large-v3-turbo` is recommended for most users, other models are available for specific needs:

| Model | VRAM | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| tiny | 1GB | Fastest | Good | Quick drafts, testing |
| base | 1GB | Very fast | Better | Testing |
| small | 2GB | Fast | Great | CPU systems |
| medium | 5GB | Moderate | Excellent | Balanced performance |
| large-v2 | 6GB | Slower | Excellent | Legacy (slower than turbo) |
| **large-v3-turbo** | 6GB | **6x faster** | **Excellent** | **Production (default)** |
| large-v3 | 6GB | Standard | **Best** | Translation, maximum accuracy |

**Default Recommendation**: Use `large-v3-turbo` for production (6x faster with excellent accuracy)

**Alternative**: Use `large-v3` if you need translation to English or maximum accuracy

## Technical Details

### Processing Pipeline

1. **Audio Extraction**: Extract audio from video files
2. **Preprocessing**: Normalize, resample to 16kHz
3. **Voice Activity Detection**: Identify speech segments
4. **Transcription**: Generate text with timestamps
5. **Alignment**: Refine word-level timing with WAV2VEC2
6. **Post-processing**: Format and index results

### Supported Formats

**Audio**:
- MP3, WAV, FLAC, M4A, OGG, WMA
- Any format FFmpeg can decode

**Video**:
- MP4, MOV, AVI, MKV, WebM, FLV
- Audio extracted automatically

### File Size Limits

- Maximum upload: **4GB**
- Suitable for GoPro and high-quality recordings
- No duration limits
- Handles multi-hour recordings

## Quality Optimization

### Best Practices

**For Best Results**:
- Use lossless formats (WAV, FLAC) when possible
- Ensure clear audio (minimal background noise)
- Use external microphones for better quality
- Avoid excessive compression

**GPU Optimization**:
- Use `float16` compute type
- Increase batch size (if VRAM available)
- Enable GPU acceleration
- Use large-v3-turbo model (default, 6x faster)

**CPU Optimization**:
- Use smaller model (small or medium)
- Use `int8` compute type
- Reduce batch size
- Consider cloud GPU for large jobs

## Advanced Features

### Auto-Cleanup Garbage Segments (New in v0.2.0)

Automatically detects and removes erroneous transcription artifacts:

**What It Cleans**:
- Random special characters and symbols
- Gibberish text from audio noise
- Extremely short nonsense segments
- Repeated characters/patterns

**Configuration** (Settings → Transcription):
- **Enable/Disable**: Toggle garbage cleanup on/off
- **Threshold**: Set maximum word length for detection

**Default**: Enabled with sensible thresholds

:::tip
Enable this feature for cleaner transcripts, especially with noisy audio or music in the background.
:::

### Custom Vocabulary

- Technical terms recognized
- Industry-specific jargon
- Proper nouns and acronyms
- Context-aware recognition

### Punctuation & Formatting

- Automatic punctuation
- Sentence capitalization
- Paragraph breaks
- Quote detection

### Confidence Scoring

Every word includes confidence score:
- High confidence: greater than 0.9
- Medium confidence: 0.7-0.9
- Low confidence: less than 0.7

Use for quality control and review.

## Integration

### Export Formats

- **Plain Text**: Simple transcript
- **SRT**: Subtitles with timestamps
- **VTT**: Web video subtitles
- **JSON**: Full data with metadata

### API Access

Programmatic access via REST API:
- Upload files
- Check transcription status
- Retrieve results
- Manage transcriptions

## Comparison

### vs. Cloud Services

| Feature | OpenTranscribe | Cloud Services |
|---------|----------------|----------------|
| **Privacy** | 100% local | Data sent to cloud |
| **Cost** | Free (after hardware) | Per-minute fees |
| **Speed** | 70x realtime | Varies |
| **Internet** | Not required | Required |
| **Customization** | Full control | Limited |

### vs. Manual Transcription

- **70x faster** than human transcription
- **Consistent quality** (no fatigue)
- **Word-perfect timing** (impossible manually)
- **Lower cost** (no per-hour fees)

## Next Steps

- [GPU Setup](../installation/gpu-setup.md) - Enable GPU acceleration
- [First Transcription](../getting-started/first-transcription.md) - Try it out
- [Speaker Diarization](./speaker-diarization.md) - Add speaker detection
