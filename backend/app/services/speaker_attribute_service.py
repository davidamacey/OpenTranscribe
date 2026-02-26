"""
Speaker attribute detection service.

Uses prithivMLmods/Common-Voice-Gender-Detection for gender prediction from audio.
This model (~380MB, Apache 2.0) is fine-tuned from wav2vec2-base-960h and achieves
98.46% accuracy on gender classification (female/male).

Model card: https://huggingface.co/prithivMLmods/Common-Voice-Gender-Detection
"""

import logging
import subprocess
from typing import Any
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = "prithivMLmods/Common-Voice-Gender-Detection"

# Label mapping: model index → gender string
GENDER_ID2LABEL = {0: "female", 1: "male"}


class SpeakerAttributeService:
    """Predicts speaker gender from audio using wav2vec2 sequence classification."""

    def __init__(self) -> None:
        self._model: Optional[Any] = None
        self._feature_extractor: Optional[Any] = None
        self._model_loaded = False

    def load_models(self) -> None:
        """Lazy-load the gender model from HuggingFace (cached after first run)."""
        if self._model_loaded:
            return

        try:
            from transformers import Wav2Vec2FeatureExtractor
            from transformers import Wav2Vec2ForSequenceClassification

            self._feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(MODEL_NAME)
            self._model = Wav2Vec2ForSequenceClassification.from_pretrained(MODEL_NAME)
            self._model.eval()
            self._model_loaded = True
            logger.info(f"Gender model loaded: {MODEL_NAME}")

        except Exception as e:
            logger.error(f"Failed to load gender model: {e}")
            raise

    @staticmethod
    def _load_audio_ffmpeg(audio_path: str, target_sr: int = 16000) -> np.ndarray:
        """Load audio to float32 numpy array at target_sr via ffmpeg.

        Avoids torchaudio backend issues - ffmpeg is always available.
        Returns 1-D float32 array (mono, normalized).
        """
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
        return np.frombuffer(result.stdout, dtype=np.float32).copy()

    def _run_inference(self, audio_np: np.ndarray) -> tuple[str, float]:
        """Run model inference on a 1-D float32 audio array at 16kHz.

        Returns:
            (gender, confidence) where gender is "female" or "male".
        """
        import torch

        inputs = self._feature_extractor(  # type: ignore[misc]
            audio_np,
            sampling_rate=16000,
            return_tensors="pt",
            padding=True,
        )

        with torch.no_grad():
            logits = self._model(**inputs).logits  # type: ignore[misc]

        probs = torch.nn.functional.softmax(logits, dim=1).squeeze().cpu().numpy()
        predicted_id = int(np.argmax(probs))
        gender = GENDER_ID2LABEL.get(predicted_id, "male")
        confidence = float(probs[predicted_id])
        return gender, confidence

    def predict_attributes(
        self,
        audio_path: str,
        segments: list[dict[str, Any]],
        speaker_mapping: dict[str, int],
    ) -> dict[str, dict[str, Any]]:
        """Predict gender for each speaker.

        Args:
            audio_path: Path to the audio file.
            segments: Diarized segments with "speaker", "start", "end" keys.
            speaker_mapping: Maps speaker label to DB speaker id.

        Returns:
            Dict keyed by speaker label with predicted attributes.
        """
        self.load_models()

        try:
            full_audio = self._load_audio_ffmpeg(audio_path)
        except Exception as e:
            logger.error(f"Failed to load audio for attribute detection: {e}")
            return {}

        sample_rate = 16000

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
                # Pick top-5 longest segments for most representative sample
                sorted_segs = sorted(segs, key=lambda s: s["end"] - s["start"], reverse=True)
                selected = sorted_segs[:5]

                gender_probs_acc: dict[str, float] = {"male": 0.0, "female": 0.0}
                valid_clips = 0

                for seg in selected:
                    start = int(seg["start"] * sample_rate)
                    end = int(seg["end"] * sample_rate)

                    # Skip clips under 1s - too short for wav2vec2
                    if end - start < sample_rate:
                        continue

                    clip = full_audio[start:end]
                    if len(clip) == 0:
                        continue

                    gender, gender_conf = self._run_inference(clip)
                    gender_probs_acc[gender] = gender_probs_acc.get(gender, 0.0) + gender_conf
                    valid_clips += 1

                if valid_clips == 0:
                    logger.warning(f"No valid clips for speaker {speaker_label}")
                    continue

                # Final gender: highest accumulated probability across clips
                final_gender = max(gender_probs_acc, key=lambda k: gender_probs_acc[k])
                final_gender_conf = gender_probs_acc[final_gender] / valid_clips

                results[speaker_label] = {
                    "predicted_gender": final_gender,
                    "predicted_age_range": None,
                    "attribute_confidence": {
                        "gender": round(final_gender_conf, 3),
                    },
                }
                logger.info(
                    f"Speaker {speaker_label}: gender={final_gender} ({final_gender_conf:.2f})"
                )

            except Exception as e:
                logger.warning(f"Attribute prediction failed for {speaker_label}: {e}")
                continue

        return results

    def cleanup(self) -> None:
        """Release model resources."""
        self._model = None
        self._feature_extractor = None
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
