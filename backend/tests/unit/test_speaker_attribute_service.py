"""
Unit tests for SpeakerAttributeService.

Tests cover service initialization, segment selection, probability aggregation,
short-segment skipping, and inference output format. All ML model calls are
mocked so tests run on CPU without downloading the actual HuggingFace model.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import numpy as np
import pytest

from app.services.speaker_attribute_service import GENDER_ID2LABEL
from app.services.speaker_attribute_service import SpeakerAttributeService
from app.services.speaker_attribute_service import get_cached_attribute_service

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    """Return an un-loaded SpeakerAttributeService instance."""
    return SpeakerAttributeService()


@pytest.fixture
def loaded_service():
    """Return a SpeakerAttributeService with mocked model already loaded."""
    svc = SpeakerAttributeService()
    svc._model_loaded = True
    svc._model = MagicMock()
    svc._feature_extractor = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# 1. Service initialization
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestServiceInitialization:
    """Test that the service initialises with the correct default state."""

    def test_model_not_loaded_at_init(self, service):
        """_model_loaded starts as False before any call to load_models()."""
        assert service._model_loaded is False

    def test_model_attribute_is_none_at_init(self, service):
        """_model starts as None."""
        assert service._model is None

    def test_feature_extractor_is_none_at_init(self, service):
        """_feature_extractor starts as None."""
        assert service._feature_extractor is None

    def test_cleanup_resets_loaded_state(self, loaded_service):
        """cleanup() sets _model_loaded back to False and clears references."""
        loaded_service.cleanup()
        assert loaded_service._model_loaded is False
        assert loaded_service._model is None
        assert loaded_service._feature_extractor is None

    def test_load_models_sets_loaded_flag(self, service):
        """load_models() sets _model_loaded=True on success."""
        mock_fe = MagicMock()
        mock_fe.from_pretrained.return_value = MagicMock()

        mock_model_instance = MagicMock()
        mock_model_cls = MagicMock()
        mock_model_cls.from_pretrained.return_value = mock_model_instance

        mock_transformers = MagicMock()
        mock_transformers.Wav2Vec2FeatureExtractor = mock_fe
        mock_transformers.Wav2Vec2ForSequenceClassification = mock_model_cls

        # load_models() does `from transformers import ...` locally, so we patch
        # the module in sys.modules so those local imports resolve to our mocks.
        with patch.dict("sys.modules", {"transformers": mock_transformers}):
            service.load_models()

        assert service._model_loaded is True

    def test_load_models_idempotent(self, loaded_service):
        """Calling load_models() when already loaded is a no-op (no error)."""
        # Should return immediately without touching transformers
        with patch("builtins.__import__", side_effect=ImportError("should not be called")):
            # The guard `if self._model_loaded: return` prevents any import
            loaded_service.load_models()
        assert loaded_service._model_loaded is True

    def test_get_cached_service_returns_same_instance(self):
        """get_cached_attribute_service() returns the same object on repeated calls."""
        import app.services.speaker_attribute_service as mod

        # Reset cached instance for a clean test
        original = mod._cached_service
        mod._cached_service = None
        try:
            svc1 = get_cached_attribute_service()
            svc2 = get_cached_attribute_service()
            assert svc1 is svc2
        finally:
            mod._cached_service = original


# ---------------------------------------------------------------------------
# 2. Segment selection (top-5 longest)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSegmentSelection:
    """Test that predict_attributes picks the top-5 longest segments."""

    def _make_segments(self, durations: list[float], speaker: str = "SPEAKER_00") -> list[dict]:
        """Build fake segments with the given durations."""
        segs = []
        t = 0.0
        for dur in durations:
            segs.append({"speaker": speaker, "start": t, "end": t + dur})
            t += dur + 0.1
        return segs

    def test_only_top5_segments_used(self, loaded_service):
        """When >5 segments exist, only the 5 longest are processed."""
        # 7 segments; three 0.5-s segments are shortest and should be ignored
        durations = [5.0, 4.0, 3.0, 2.0, 1.5, 0.5, 0.5]
        segs = self._make_segments(durations)
        speaker_mapping = {"SPEAKER_00": 1}

        inference_calls = []

        def fake_run_inference(clip):
            inference_calls.append(len(clip))
            return "female", 0.9

        loaded_service._run_inference = fake_run_inference

        # Provide a fake full_audio large enough to cover all segments
        total_samples = int(sum(durations) * 16000) + 16000 * 5
        fake_audio = np.zeros(total_samples, dtype=np.float32)

        with patch.object(
            SpeakerAttributeService,
            "_load_audio_ffmpeg",
            return_value=fake_audio,
        ):
            loaded_service.predict_attributes(
                audio_path="/fake/audio.wav",
                segments=segs,
                speaker_mapping=speaker_mapping,
            )

        # At most 5 inference calls per speaker
        assert len(inference_calls) <= 5

    def test_segments_under_1s_are_skipped(self, loaded_service):
        """Clips shorter than 1 second (< sample_rate samples) are skipped."""
        # Only one 0.5-s segment — too short
        segs = [{"speaker": "SPEAKER_00", "start": 0.0, "end": 0.5}]
        speaker_mapping = {"SPEAKER_00": 1}

        inference_calls = []

        def fake_run_inference(clip):
            inference_calls.append(clip)
            return "female", 0.9

        loaded_service._run_inference = fake_run_inference

        fake_audio = np.zeros(8000, dtype=np.float32)  # 0.5 s of zeros at 16kHz

        with patch.object(
            SpeakerAttributeService,
            "_load_audio_ffmpeg",
            return_value=fake_audio,
        ):
            results = loaded_service.predict_attributes(
                audio_path="/fake/audio.wav",
                segments=segs,
                speaker_mapping=speaker_mapping,
            )

        # Short segment should be skipped → no result for this speaker
        assert inference_calls == []
        assert "SPEAKER_00" not in results

    def test_speaker_not_in_mapping_is_skipped(self, loaded_service):
        """Speakers absent from speaker_mapping are ignored entirely."""
        segs = [{"speaker": "SPEAKER_99", "start": 0.0, "end": 3.0}]
        speaker_mapping = {"SPEAKER_00": 1}  # SPEAKER_99 not in mapping

        inference_calls = []

        def fake_run_inference(clip):
            inference_calls.append(clip)
            return "female", 0.9

        loaded_service._run_inference = fake_run_inference
        fake_audio = np.zeros(16000 * 5, dtype=np.float32)

        with patch.object(
            SpeakerAttributeService,
            "_load_audio_ffmpeg",
            return_value=fake_audio,
        ):
            results = loaded_service.predict_attributes(
                audio_path="/fake/audio.wav",
                segments=segs,
                speaker_mapping=speaker_mapping,
            )

        assert "SPEAKER_99" not in results
        assert inference_calls == []


# ---------------------------------------------------------------------------
# 3. Probability aggregation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProbabilityAggregation:
    """Test gender aggregation across multiple audio clips."""

    def _run_with_inference_results(
        self,
        loaded_service,
        inference_results: list[tuple[str, float]],
        num_segments: int | None = None,
    ) -> dict[str, Any]:
        """Run predict_attributes with a pre-set sequence of inference results."""
        if num_segments is None:
            num_segments = len(inference_results)

        call_index = 0

        def fake_run_inference(clip):
            nonlocal call_index
            result = inference_results[call_index % len(inference_results)]
            call_index += 1
            return result

        loaded_service._run_inference = fake_run_inference

        # Build segments that are each 2s long (well above the 1s minimum)
        segs = [
            {"speaker": "SPEAKER_00", "start": i * 2.0, "end": i * 2.0 + 2.0}
            for i in range(num_segments)
        ]
        speaker_mapping = {"SPEAKER_00": 1}
        total_samples = int(num_segments * 2 * 16000) + 16000
        fake_audio = np.zeros(total_samples, dtype=np.float32)

        with patch.object(
            SpeakerAttributeService,
            "_load_audio_ffmpeg",
            return_value=fake_audio,
        ):
            result: dict[str, Any] = loaded_service.predict_attributes(
                audio_path="/fake/audio.wav",
                segments=segs,
                speaker_mapping=speaker_mapping,
            )
            return result

    def test_majority_female_wins(self, loaded_service):
        """Two female clips (0.9, 0.85) and one male clip (0.6) → predicted 'female'."""
        results = self._run_with_inference_results(
            loaded_service,
            inference_results=[("female", 0.9), ("female", 0.85), ("male", 0.6)],
        )
        assert "SPEAKER_00" in results
        assert results["SPEAKER_00"]["predicted_gender"] == "female"

    def test_all_clips_agree_on_male(self, loaded_service):
        """Three male clips → predicted 'male'."""
        results = self._run_with_inference_results(
            loaded_service,
            inference_results=[("male", 0.95), ("male", 0.92), ("male", 0.88)],
        )
        assert results["SPEAKER_00"]["predicted_gender"] == "male"

    def test_confidence_is_average_of_winning_clips(self, loaded_service):
        """Reported confidence is the accumulated probability divided by valid_clips."""
        results = self._run_with_inference_results(
            loaded_service,
            inference_results=[("female", 0.9), ("female", 0.8)],
        )
        # Expected confidence = (0.9 + 0.8) / 2 = 0.85
        reported_conf = results["SPEAKER_00"]["attribute_confidence"]["gender"]
        assert abs(reported_conf - 0.85) < 0.01

    def test_single_clip_confidence_equals_its_confidence(self, loaded_service):
        """With a single valid clip, reported confidence equals that clip's confidence."""
        results = self._run_with_inference_results(
            loaded_service,
            inference_results=[("male", 0.77)],
        )
        reported_conf = results["SPEAKER_00"]["attribute_confidence"]["gender"]
        assert abs(reported_conf - 0.77) < 0.01

    def test_mixed_results_struct(self, loaded_service):
        """Result dict has expected keys."""
        results = self._run_with_inference_results(
            loaded_service,
            inference_results=[("female", 0.9)],
        )
        r = results["SPEAKER_00"]
        assert "predicted_gender" in r
        assert "predicted_age_range" in r
        assert "attribute_confidence" in r
        assert "gender" in r["attribute_confidence"]

    def test_age_range_is_none(self, loaded_service):
        """predicted_age_range is None (not implemented yet)."""
        results = self._run_with_inference_results(
            loaded_service,
            inference_results=[("female", 0.9)],
        )
        assert results["SPEAKER_00"]["predicted_age_range"] is None

    def test_ffmpeg_failure_returns_empty(self, loaded_service):
        """If audio loading fails, predict_attributes returns {}."""
        segs = [{"speaker": "SPEAKER_00", "start": 0.0, "end": 3.0}]
        speaker_mapping = {"SPEAKER_00": 1}

        with patch.object(
            SpeakerAttributeService,
            "_load_audio_ffmpeg",
            side_effect=RuntimeError("ffmpeg not found"),
        ):
            results = loaded_service.predict_attributes(
                audio_path="/fake/audio.wav",
                segments=segs,
                speaker_mapping=speaker_mapping,
            )

        assert results == {}


# ---------------------------------------------------------------------------
# 4. _run_inference mock — format verification
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunInference:
    """Test that _run_inference returns (gender_str, confidence_float) correctly."""

    def test_run_inference_returns_tuple(self, loaded_service):
        """_run_inference returns a (str, float) tuple."""
        import torch

        # Build a minimal softmax output: female=0.8, male=0.2
        mock_logits = torch.tensor([[2.0, 0.5]])  # higher logit → female (index 0)

        mock_output = MagicMock()
        mock_output.logits = mock_logits
        loaded_service._model.return_value = mock_output

        mock_inputs = MagicMock()
        loaded_service._feature_extractor.return_value = mock_inputs
        # Make the model callable via **mock_inputs (unpack)
        loaded_service._model.__call__ = MagicMock(return_value=mock_output)
        # feature_extractor returns a dict-like object
        loaded_service._feature_extractor.return_value = {"input_values": torch.zeros(1, 16000)}

        audio = np.zeros(16000, dtype=np.float32)
        gender, confidence = loaded_service._run_inference(audio)

        assert isinstance(gender, str)
        assert gender in ("female", "male")
        assert isinstance(confidence, float)
        assert 0.0 <= confidence <= 1.0

    def test_run_inference_female_label(self, loaded_service):
        """When logits favour index 0 → gender='female' (GENDER_ID2LABEL mapping)."""
        import torch

        mock_logits = torch.tensor([[5.0, 0.1]])  # index 0 strongly wins
        mock_output = MagicMock()
        mock_output.logits = mock_logits
        loaded_service._model.return_value = mock_output
        loaded_service._feature_extractor.return_value = {"input_values": torch.zeros(1, 16000)}

        audio = np.zeros(16000, dtype=np.float32)
        gender, confidence = loaded_service._run_inference(audio)

        assert gender == GENDER_ID2LABEL[0]  # "female"
        assert confidence > 0.5

    def test_run_inference_male_label(self, loaded_service):
        """When logits favour index 1 → gender='male' (GENDER_ID2LABEL mapping)."""
        import torch

        mock_logits = torch.tensor([[0.1, 5.0]])  # index 1 strongly wins
        mock_output = MagicMock()
        mock_output.logits = mock_logits
        loaded_service._model.return_value = mock_output
        loaded_service._feature_extractor.return_value = {"input_values": torch.zeros(1, 16000)}

        audio = np.zeros(16000, dtype=np.float32)
        gender, confidence = loaded_service._run_inference(audio)

        assert gender == GENDER_ID2LABEL[1]  # "male"
        assert confidence > 0.5


# ---------------------------------------------------------------------------
# 5. GENDER_ID2LABEL constant
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenderIdToLabel:
    """Test the GENDER_ID2LABEL mapping constant."""

    def test_index_0_is_female(self):
        assert GENDER_ID2LABEL[0] == "female"

    def test_index_1_is_male(self):
        assert GENDER_ID2LABEL[1] == "male"

    def test_only_two_labels(self):
        assert len(GENDER_ID2LABEL) == 2
