"""Tests for segment post-processing: resegmentation and merging."""

from app.utils.segment_postprocess import merge_consecutive_segments
from app.utils.segment_postprocess import resegment_by_speaker


class TestResegmentBySpeaker:
    def test_empty_input(self):
        assert resegment_by_speaker([]) == []

    def test_single_speaker_passthrough(self):
        seg = {
            "start": 0.0,
            "end": 2.0,
            "text": "hello world",
            "speaker": "SPEAKER_00",
            "words": [
                {"word": "hello", "start": 0.0, "end": 0.5, "speaker": "SPEAKER_00"},
                {"word": " world", "start": 0.5, "end": 1.0, "speaker": "SPEAKER_00"},
            ],
        }
        result = resegment_by_speaker([seg])
        assert len(result) == 1
        assert result[0] is seg  # unchanged, same object

    def test_no_words_passthrough(self):
        seg = {"start": 0.0, "end": 2.0, "text": "hello", "speaker": "SPEAKER_00"}
        result = resegment_by_speaker([seg])
        assert len(result) == 1
        assert result[0] is seg

    def test_mixed_speakers_split(self):
        seg = {
            "start": 0.0,
            "end": 3.0,
            "text": "I agree let's move on",
            "speaker": "SPEAKER_00",
            "confidence": 0.9,
            "words": [
                {"word": "I", "start": 0.0, "end": 0.3, "speaker": "SPEAKER_00"},
                {"word": " agree", "start": 0.3, "end": 0.8, "speaker": "SPEAKER_00"},
                {"word": " let's", "start": 1.0, "end": 1.5, "speaker": "SPEAKER_01"},
                {"word": " move", "start": 1.5, "end": 2.0, "speaker": "SPEAKER_01"},
                {"word": " on", "start": 2.0, "end": 2.5, "speaker": "SPEAKER_01"},
            ],
        }
        result = resegment_by_speaker([seg])
        assert len(result) == 2
        assert result[0]["speaker"] == "SPEAKER_00"
        assert result[0]["text"] == "I agree"
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 0.8
        assert len(result[0]["words"]) == 2
        assert result[1]["speaker"] == "SPEAKER_01"
        assert result[1]["text"] == "let's move on"
        assert result[1]["start"] == 1.0
        assert result[1]["end"] == 2.5
        assert len(result[1]["words"]) == 3

    def test_three_speaker_changes(self):
        seg = {
            "start": 0.0,
            "end": 3.0,
            "text": "a b c",
            "speaker": "SPEAKER_00",
            "confidence": 0.8,
            "words": [
                {"word": "a", "start": 0.0, "end": 0.5, "speaker": "SPEAKER_00"},
                {"word": " b", "start": 1.0, "end": 1.5, "speaker": "SPEAKER_01"},
                {"word": " c", "start": 2.0, "end": 2.5, "speaker": "SPEAKER_00"},
            ],
        }
        result = resegment_by_speaker([seg])
        assert len(result) == 3
        assert [r["speaker"] for r in result] == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00"]


class TestMergeConsecutiveSegments:
    def test_empty_input(self):
        assert merge_consecutive_segments([]) == []

    def test_single_segment(self):
        seg = {"start": 0.0, "end": 1.0, "text": "hello", "speaker": "SPEAKER_00", "words": []}
        result = merge_consecutive_segments([seg])
        assert len(result) == 1
        assert result[0]["text"] == "hello"

    def test_merge_same_speaker(self):
        segs = [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "hello",
                "speaker": "SPEAKER_00",
                "words": [{"word": "hello", "start": 0.0, "end": 1.0}],
            },
            {
                "start": 1.0,
                "end": 2.0,
                "text": "world",
                "speaker": "SPEAKER_00",
                "words": [{"word": "world", "start": 1.0, "end": 2.0}],
            },
        ]
        result = merge_consecutive_segments(segs)
        assert len(result) == 1
        assert result[0]["text"] == "hello world"
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 2.0
        assert len(result[0]["words"]) == 2

    def test_no_merge_different_speakers(self):
        segs = [
            {"start": 0.0, "end": 1.0, "text": "hello", "speaker": "SPEAKER_00"},
            {"start": 1.0, "end": 2.0, "text": "world", "speaker": "SPEAKER_01"},
        ]
        result = merge_consecutive_segments(segs)
        assert len(result) == 2

    def test_no_merge_none_speaker(self):
        segs = [
            {"start": 0.0, "end": 1.0, "text": "a", "speaker": None},
            {"start": 1.0, "end": 2.0, "text": "b", "speaker": None},
        ]
        result = merge_consecutive_segments(segs)
        assert len(result) == 2  # None speakers should not merge

    def test_mixed_merge_pattern(self):
        segs = [
            {"start": 0.0, "end": 1.0, "text": "a", "speaker": "SPEAKER_00"},
            {"start": 1.0, "end": 2.0, "text": "b", "speaker": "SPEAKER_00"},
            {"start": 2.0, "end": 3.0, "text": "c", "speaker": "SPEAKER_01"},
            {"start": 3.0, "end": 4.0, "text": "d", "speaker": "SPEAKER_01"},
            {"start": 4.0, "end": 5.0, "text": "e", "speaker": "SPEAKER_00"},
        ]
        result = merge_consecutive_segments(segs)
        assert len(result) == 3
        assert result[0]["text"] == "a b"
        assert result[1]["text"] == "c d"
        assert result[2]["text"] == "e"


class TestPipelineIntegration:
    """Test resegment + merge together as they're used in the pipeline."""

    def test_resegment_then_merge(self):
        """Mixed-speaker segment followed by same-speaker segment should merge after resegment."""
        segs = [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "yes no",
                "speaker": "SPEAKER_00",
                "confidence": 0.9,
                "words": [
                    {"word": "yes", "start": 0.0, "end": 0.5, "speaker": "SPEAKER_00"},
                    {"word": " no", "start": 1.0, "end": 1.5, "speaker": "SPEAKER_01"},
                ],
            },
            {
                "start": 2.0,
                "end": 3.0,
                "text": "maybe",
                "speaker": "SPEAKER_01",
                "confidence": 0.9,
                "words": [
                    {"word": "maybe", "start": 2.0, "end": 2.5, "speaker": "SPEAKER_01"},
                ],
            },
        ]
        result = merge_consecutive_segments(resegment_by_speaker(segs))
        assert len(result) == 2
        assert result[0]["speaker"] == "SPEAKER_00"
        assert result[0]["text"] == "yes"
        assert result[1]["speaker"] == "SPEAKER_01"
        assert result[1]["text"] == "no maybe"
