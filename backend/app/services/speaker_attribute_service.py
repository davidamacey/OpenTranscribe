"""
Speaker attribute detection service.

Uses SpeechBrain's gender-recognition-wav2vec2 model for gender classification
and name-based gender heuristics as a fallback. Age range is estimated from
voice characteristics using spectral analysis. Runs on CPU queue after
transcription.
"""

import logging
import subprocess
from typing import Any
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# SpeechBrain gender classifier - fine-tuned wav2vec2 on CommonVoice
GENDER_MODEL = "speechbrain/gender-recognition-wav2vec2-commonvoice-14-en"

# Age range bins used for display
AGE_RANGES = ["child", "teen", "young_adult", "adult", "senior"]


class SpeakerAttributeService:
    """Predicts speaker gender from audio using SpeechBrain's gender classifier."""

    def __init__(self):
        self._gender_classifier = None
        self._model_loaded = False

    def load_models(self) -> None:
        """Lazy-load SpeechBrain gender classifier."""
        if self._model_loaded:
            return

        try:
            from speechbrain.inference.classifiers import EncoderClassifier

            self._gender_classifier = EncoderClassifier.from_hparams(
                source=GENDER_MODEL,
                run_opts={"device": "cpu"},
            )
            self._model_loaded = True
            logger.info(f"SpeechBrain gender classifier loaded: {GENDER_MODEL}")
        except Exception as e:
            logger.error(f"Failed to load SpeechBrain gender model: {e}")
            raise

    @staticmethod
    def _load_audio_ffmpeg(audio_path: str, target_sr: int = 16000):
        """Load audio via ffmpeg pipe to numpy/torch.

        Avoids torchaudio backend issues (soundfile/sox not installed in
        container). ffmpeg is always available and handles all formats.
        Outputs mono float32 PCM at target_sr.
        """
        import torch

        cmd = [
            "ffmpeg",
            "-i",
            audio_path,
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-ac",
            "1",
            "-ar",
            str(target_sr),
            "-v",
            "quiet",
            "pipe:1",
        ]
        result = subprocess.run(cmd, capture_output=True, check=True)  # noqa: S603 # nosec B603
        audio_np = np.frombuffer(result.stdout, dtype=np.float32).copy()
        waveform = torch.from_numpy(audio_np).unsqueeze(0)  # [1, samples]
        return waveform, target_sr

    def predict_attributes(
        self,
        audio_path: str,
        segments: list[dict[str, Any]],
        speaker_mapping: dict[str, int],
    ) -> dict[str, dict[str, Any]]:
        """Predict gender for each speaker in the audio file.

        Args:
            audio_path: Path to the audio file (wav/mp3/etc).
            segments: List of diarized segments with "speaker", "start", "end" keys.
            speaker_mapping: Maps speaker label (e.g. "SPEAKER_00") to DB speaker id.

        Returns:
            Dict keyed by speaker label with predicted attributes.
        """
        self.load_models()

        import torch

        try:
            waveform, sample_rate = self._load_audio_ffmpeg(audio_path)
        except Exception as e:
            logger.error(f"Failed to load audio for attribute detection: {e}")
            return {}

        # Convert to mono if needed (ffmpeg already does this, defensive check)
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        # Group segments by speaker
        speaker_segments: dict[str, list[dict]] = {}
        for seg in segments:
            label = seg.get("speaker", "SPEAKER_00")
            if label not in speaker_segments:
                speaker_segments[label] = []
            speaker_segments[label].append(seg)

        results = {}

        for speaker_label, segs in speaker_segments.items():
            if speaker_label not in speaker_mapping:
                continue

            try:
                # Use the 5 longest segments for most representative sample
                sorted_segs = sorted(segs, key=lambda s: s["end"] - s["start"], reverse=True)
                selected = sorted_segs[:5]

                # Accumulate gender class probabilities across clips
                gender_probs_list = []

                for seg in selected:
                    start_sample = int(seg["start"] * sample_rate)
                    end_sample = int(seg["end"] * sample_rate)

                    # Skip clips under 0.5s - too short for reliable classification
                    if end_sample - start_sample < int(sample_rate * 0.5):
                        continue

                    clip = waveform[:, start_sample:end_sample]
                    if clip.shape[1] == 0:
                        continue

                    with torch.no_grad():
                        # classify_batch returns (out_prob, score, index, label)
                        out_prob, score, index, label = self._gender_classifier.classify_batch(clip)  # type: ignore[union-attr]
                        # out_prob shape: [batch, num_classes] — take first item
                        gender_probs_list.append(out_prob[0].cpu().numpy())

                if not gender_probs_list:
                    logger.warning(f"No valid clips for speaker {speaker_label}")
                    continue

                # Average probabilities across clips for robust prediction
                avg_probs = np.mean(gender_probs_list, axis=0)
                predicted_idx = int(np.argmax(avg_probs))
                gender_confidence = float(avg_probs[predicted_idx])

                # Map model output label to our schema
                label_map = self._gender_classifier.hparams.label_encoder.ind2lab  # type: ignore[union-attr]
                raw_label = label_map.get(predicted_idx, "unknown").lower()
                predicted_gender = raw_label if raw_label in ("male", "female") else "unknown"

                # Age range from spectral characteristics of the audio clips
                age_range, age_conf = self._estimate_age_range(waveform, selected, sample_rate)

                results[speaker_label] = {
                    "predicted_gender": predicted_gender,
                    "predicted_age_range": age_range,
                    "attribute_confidence": {
                        "gender": round(gender_confidence, 3),
                        "age_range": round(age_conf, 3),
                    },
                }
                logger.info(
                    f"Speaker {speaker_label}: gender={predicted_gender} "
                    f"({gender_confidence:.2f}), age={age_range} ({age_conf:.2f})"
                )

            except Exception as e:
                logger.warning(f"Attribute prediction failed for {speaker_label}: {e}")
                continue

        return results

    def _estimate_age_range(
        self,
        waveform: Any,
        segments: list[dict],
        sample_rate: int,
    ) -> tuple[str, float]:
        """Estimate age range using spectral centroid and zero-crossing rate.

        These are proxy features - not as reliable as gender. The confidence
        is intentionally capped lower to reflect this uncertainty.
        """
        zcr_values = []
        centroid_values = []

        for seg in segments:
            start_sample = int(seg["start"] * sample_rate)
            end_sample = int(seg["end"] * sample_rate)
            clip = waveform[:, start_sample:end_sample]
            if clip.shape[1] < sample_rate * 0.5:
                continue

            audio = clip[0].numpy()

            # Zero-crossing rate - higher in younger voices
            signs = np.sign(audio)
            zcr = np.mean(np.abs(np.diff(signs)) / 2)
            zcr_values.append(zcr)

            # Spectral centroid - higher in brighter/younger voices
            fft = np.abs(np.fft.rfft(audio))
            freqs = np.fft.rfftfreq(len(audio), 1 / sample_rate)
            if fft.sum() > 0:
                centroid = float(np.sum(freqs * fft) / np.sum(fft))
                centroid_values.append(centroid)

        if not zcr_values:
            return "adult", 0.3

        avg_zcr = np.mean(zcr_values)
        avg_centroid = np.mean(centroid_values) if centroid_values else 2000.0

        # Thresholds derived from typical voice characteristics
        # Confidence is capped at 0.65 - age estimation is inherently uncertain
        if avg_zcr > 0.12 and avg_centroid > 2500:
            return "young_adult", 0.55
        elif avg_zcr > 0.08 and avg_centroid > 1800:
            return "adult", 0.5
        elif avg_zcr < 0.05 and avg_centroid < 1500:
            return "senior", 0.5
        else:
            return "adult", 0.4

    def cleanup(self) -> None:
        """Release model resources."""
        self._gender_classifier = None
        self._model_loaded = False
        logger.info("Speaker attribute models released")


# Module-level cached instance
_cached_service: Optional[SpeakerAttributeService] = None


def get_cached_attribute_service() -> SpeakerAttributeService:
    """Get or create a cached SpeakerAttributeService instance."""
    global _cached_service
    if _cached_service is None:
        _cached_service = SpeakerAttributeService()
    return _cached_service
