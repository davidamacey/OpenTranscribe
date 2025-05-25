# Transcription with WhisperX

OpenTranscribe uses WhisperX for transcription, alignment, and speaker diarization capabilities. This combines the powerful features of OpenAI's Whisper with word-level alignment and speaker identification.

## Features

- **Fast batch processing**: WhisperX leverages faster-whisper for batched inference (70x realtime with large-v2)
- **Accurate word-level timestamps**: Uses wav2vec2 alignment for precise word timing
- **Speaker diarization**: Identifies different speakers in the audio using pyannote.audio
- **Automatic translation**: Always converts audio to English transcripts
- **Video metadata extraction**: Extracts detailed metadata from video files using ExifTool (resolution, frame rate, codec, etc.)

## Configuration

The following configuration options can be set in the `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `WHISPER_MODEL` | Whisper model size to use | `large-v2` |
| `DIARIZATION_MODEL` | Pyannote diarization model | `pyannote/speaker-diarization-3.1` |
| `BATCH_SIZE` | Batch size for processing (reduce if low on GPU memory) | `16` |
| `COMPUTE_TYPE` | Computation precision (`float16` or `int8`) | `float16` |
| `MIN_SPEAKERS` | Minimum number of speakers to detect (optional) | `1` |
| `MAX_SPEAKERS` | Maximum number of speakers to detect (optional) | `10` |
| `HUGGINGFACE_TOKEN` | HuggingFace API token for diarization models | Required |
| `MODELS_DIRECTORY` | Directory to store downloaded models | `/app/models` |

## Requirements

Required Python packages are listed in `requirements-transcription.txt`:

```
whisperx>=3.1.0        # WhisperX for audio transcription, alignment, and diarization
torch>=2.0.0           # PyTorch for neural network processing
ffmpeg-python>=0.2.0   # Audio processing utilities
nltk>=3.8.1            # For summarization functionality
sentence-transformers>=2.5.0  # For embedding generation
```

## HuggingFace Authentication

You must obtain a HuggingFace API token to use the speaker diarization functionality. Create an account at [HuggingFace](https://huggingface.co/) and generate a token at https://huggingface.co/settings/tokens.

You also need to accept the user agreement for the following models:
- [Segmentation](https://huggingface.co/pyannote/segmentation)
- [Speaker-Diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)

## Troubleshooting

- **High GPU Memory Usage**: Try reducing `BATCH_SIZE` or changing `COMPUTE_TYPE` to `int8`
- **Slow Processing**: Consider using a smaller model like `medium` or `small` 
- **Speaker Identification Issues**: Adjust `MIN_SPEAKERS` and `MAX_SPEAKERS` if you know the approximate speaker count

## References

- [WhisperX GitHub Repository](https://github.com/m-bain/whisperX)
- [Pyannote Audio](https://github.com/pyannote/pyannote-audio)
