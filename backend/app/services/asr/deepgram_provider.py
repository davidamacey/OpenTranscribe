"""Deepgram Nova-3 Medical ASR provider.

Uses the Deepgram pre-recorded API for transcription with built-in diarization.
Supports keyterm prompting for medical vocabulary (up to 100 terms).
"""

import logging
from pathlib import Path
from typing import Callable

from .base import ASRProvider
from .types import Segment, TranscriptionConfig, TranscriptionResult, Word

logger = logging.getLogger(__name__)


class DeepgramProvider(ASRProvider):
    """Deepgram Nova-3 Medical ASR provider."""

    def __init__(self, api_key: str, model: str = "nova-3-medical"):
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY is required for Deepgram provider")
        self._api_key = api_key
        self._model = model

    @property
    def provider_name(self) -> str:
        return "deepgram"

    def supports_diarization(self) -> bool:
        return True

    def supports_keyterms(self) -> bool:
        return True

    async def transcribe(
        self,
        audio_path: str,
        config: TranscriptionConfig,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio using Deepgram pre-recorded API."""
        from deepgram import DeepgramClient, PrerecordedOptions

        if progress_callback:
            progress_callback(0.40, "Sending audio to Deepgram")

        client = DeepgramClient(self._api_key)

        # Build options
        options_dict: dict = {
            "model": self._model,
            "smart_format": True,
            "diarize": True,
            "punctuate": True,
            "paragraphs": True,
            "utterances": True,
        }

        # Language configuration
        if config.source_language and config.source_language != "auto":
            options_dict["language"] = config.source_language

        # Keyterm prompting (up to 100 terms)
        if config.keyterms:
            options_dict["keyterm"] = config.keyterms[:100]

        options = PrerecordedOptions(**options_dict)

        if progress_callback:
            progress_callback(0.45, "Transcribing with Deepgram")

        # Read audio file and send to Deepgram
        audio_data = Path(audio_path).read_bytes()
        response = client.listen.rest.v("1").transcribe_file(
            {"buffer": audio_data},
            options,
        )

        if progress_callback:
            progress_callback(0.55, "Processing Deepgram results")

        # Parse response into unified format
        result = self._parse_response(response)

        if progress_callback:
            progress_callback(0.65, "Diarization complete")

        return result

    def _parse_response(self, response) -> TranscriptionResult:
        """Parse Deepgram API response into unified TranscriptionResult."""
        results = response.results

        # Get detected language
        detected_language = None
        if results.channels and results.channels[0].detected_language:
            detected_language = results.channels[0].detected_language

        segments: list[Segment] = []

        # Use utterances for speaker-segmented output
        if results.utterances:
            segments = self._parse_utterances(results.utterances)
        elif results.channels:
            # Fallback: parse from channel alternatives
            segments = self._parse_channel(results.channels[0])

        model_info = response.metadata.model_info if hasattr(response, "metadata") else {}

        return TranscriptionResult(
            segments=segments,
            detected_language=detected_language,
            provider_name="deepgram",
            provider_model=self._model,
            provider_metadata={
                "request_id": getattr(response.metadata, "request_id", None),
                "model_info": str(model_info),
            },
        )

    def _parse_utterances(self, utterances) -> list[Segment]:
        """Parse Deepgram utterances into Segments."""
        segments = []
        for utt in utterances:
            speaker_label = f"SPEAKER_{utt.speaker:02d}" if utt.speaker is not None else None

            # Build word list from utterance words
            words = []
            if hasattr(utt, "words") and utt.words:
                for w in utt.words:
                    words.append(
                        Word(
                            text=w.punctuated_word if hasattr(w, "punctuated_word") else w.word,
                            start=w.start,
                            end=w.end,
                            confidence=w.confidence if hasattr(w, "confidence") else 1.0,
                            speaker_label=f"SPEAKER_{w.speaker:02d}"
                            if hasattr(w, "speaker") and w.speaker is not None
                            else speaker_label,
                        )
                    )

            # Compute average confidence from words
            avg_confidence = 1.0
            if words:
                avg_confidence = sum(w.confidence for w in words) / len(words)

            segments.append(
                Segment(
                    text=utt.transcript.strip(),
                    start=utt.start,
                    end=utt.end,
                    speaker_label=speaker_label,
                    confidence=avg_confidence,
                    words=words,
                )
            )

        return segments

    def _parse_channel(self, channel) -> list[Segment]:
        """Fallback: parse from channel alternatives when utterances unavailable."""
        segments = []
        if not channel.alternatives:
            return segments

        alt = channel.alternatives[0]
        if not hasattr(alt, "paragraphs") or not alt.paragraphs:
            # Single segment from full transcript
            words = []
            if hasattr(alt, "words") and alt.words:
                for w in alt.words:
                    words.append(
                        Word(
                            text=w.punctuated_word if hasattr(w, "punctuated_word") else w.word,
                            start=w.start,
                            end=w.end,
                            confidence=w.confidence if hasattr(w, "confidence") else 1.0,
                            speaker_label=f"SPEAKER_{w.speaker:02d}"
                            if hasattr(w, "speaker") and w.speaker is not None
                            else None,
                        )
                    )
            avg_confidence = sum(w.confidence for w in words) / len(words) if words else 1.0
            segments.append(
                Segment(
                    text=alt.transcript.strip(),
                    start=words[0].start if words else 0.0,
                    end=words[-1].end if words else 0.0,
                    confidence=avg_confidence,
                    words=words,
                )
            )
            return segments

        # Parse paragraphs for speaker-segmented output
        for paragraph in alt.paragraphs.paragraphs:
            speaker_label = (
                f"SPEAKER_{paragraph.speaker:02d}" if paragraph.speaker is not None else None
            )
            for sentence in paragraph.sentences:
                segments.append(
                    Segment(
                        text=sentence.text.strip(),
                        start=sentence.start,
                        end=sentence.end,
                        speaker_label=speaker_label,
                        confidence=alt.confidence if hasattr(alt, "confidence") else 1.0,
                    )
                )

        return segments
