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

OpenTranscribe uses the **large-v2** model by default:

- Word Error Rate (WER): ~3-5% on clean audio
- Robust to accents and speech variations
- Handles technical terminology well
- Works with background noise

## Multi-Language Support

**50+ Languages Supported**:

- English (US, UK, Australian, Indian)
- Spanish, French, German, Italian
- Portuguese, Russian, Japanese, Chinese
- Arabic, Hindi, Korean, and many more

**Automatic Translation**:
- Transcribe in original language
- Automatically translate to English
- Preserve word-level timestamps

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

## Model Selection

Choose model based on your needs:

| Model | VRAM | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| tiny | 1GB | Fastest | Good | Quick drafts |
| base | 1GB | Very fast | Better | Testing |
| small | 2GB | Fast | Great | CPU systems |
| medium | 5GB | Moderate | Excellent | Balanced |
| **large-v2** | 6GB | Standard | **Best** | **Production** |
| large-v3 | 6GB | Standard | Best | Latest model |

**Recommendation**: Use `large-v2` for production (best accuracy/speed balance)

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
- Use large-v2 model

**CPU Optimization**:
- Use smaller model (small or medium)
- Use `int8` compute type
- Reduce batch size
- Consider cloud GPU for large jobs

## Advanced Features

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
