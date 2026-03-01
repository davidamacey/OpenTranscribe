"""Tests for the v4 embedding migration tasks and helpers."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# Patch path for get_opensearch_client — it's imported inside function bodies
# from app.services.opensearch_service, so we patch at the source.
_OS_CLIENT_PATCH = "app.services.opensearch_service.get_opensearch_client"


class TestGetAlreadyMigratedFileIds:
    """Tests for _get_already_migrated_file_ids skip logic."""

    @patch(_OS_CLIENT_PATCH)
    def test_returns_empty_set_when_no_client(self, mock_get_client):
        from app.tasks.embedding_migration_v4 import _get_already_migrated_file_ids

        mock_get_client.return_value = None
        assert _get_already_migrated_file_ids() == set()

    @patch(_OS_CLIENT_PATCH)
    def test_returns_empty_set_when_v4_index_missing(self, mock_get_client):
        from app.tasks.embedding_migration_v4 import _get_already_migrated_file_ids

        mock_client = MagicMock()
        mock_client.indices.exists.return_value = False
        mock_get_client.return_value = mock_client
        assert _get_already_migrated_file_ids() == set()

    @patch(_OS_CLIENT_PATCH)
    def test_returns_file_ids_from_aggregation(self, mock_get_client):
        from app.tasks.embedding_migration_v4 import _get_already_migrated_file_ids

        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        mock_client.search.return_value = {
            "aggregations": {
                "file_ids": {
                    "buckets": [
                        {"key": 10, "doc_count": 3},
                        {"key": 25, "doc_count": 1},
                        {"key": 42, "doc_count": 5},
                    ]
                }
            }
        }
        mock_get_client.return_value = mock_client

        result = _get_already_migrated_file_ids()
        assert result == {10, 25, 42}

    @patch(_OS_CLIENT_PATCH)
    def test_returns_empty_on_search_error(self, mock_get_client):
        from app.tasks.embedding_migration_v4 import _get_already_migrated_file_ids

        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        mock_client.search.side_effect = Exception("search failed")
        mock_get_client.return_value = mock_client

        result = _get_already_migrated_file_ids()
        assert result == set()


class TestBulkWriteV4Embeddings:
    """Tests for _bulk_write_v4_embeddings."""

    @patch(_OS_CLIENT_PATCH)
    def test_empty_docs_returns_zero(self, mock_get_client):
        from app.tasks.embedding_migration_v4 import _bulk_write_v4_embeddings

        assert _bulk_write_v4_embeddings([]) == 0
        mock_get_client.assert_not_called()

    @patch(_OS_CLIENT_PATCH)
    def test_returns_zero_when_no_client(self, mock_get_client):
        from app.tasks.embedding_migration_v4 import _bulk_write_v4_embeddings

        mock_get_client.return_value = None
        result = _bulk_write_v4_embeddings([{"_id": "abc", "name": "test"}])
        assert result == 0

    @patch("app.tasks.embedding_migration_v4.settings")
    @patch(_OS_CLIENT_PATCH)
    def test_bulk_writes_documents(self, mock_get_client, mock_settings):
        from app.tasks.embedding_migration_v4 import _bulk_write_v4_embeddings

        mock_settings.OPENSEARCH_SPEAKER_INDEX = "speakers"
        mock_client = MagicMock()
        mock_client.bulk.return_value = {"errors": False, "items": []}
        mock_get_client.return_value = mock_client

        docs = [
            {"_id": "uuid-1", "speaker_id": 1, "name": "Alice", "embedding": [0.1] * 256},
            {"_id": "uuid-2", "speaker_id": 2, "name": "Bob", "embedding": [0.2] * 256},
        ]

        result = _bulk_write_v4_embeddings(docs)
        assert result == 2
        mock_client.bulk.assert_called_once()

        # Verify bulk body structure
        bulk_body = mock_client.bulk.call_args.kwargs["body"]
        assert len(bulk_body) == 4  # 2 action + 2 doc
        assert bulk_body[0] == {"index": {"_index": "speakers_v4", "_id": "uuid-1"}}
        assert bulk_body[2] == {"index": {"_index": "speakers_v4", "_id": "uuid-2"}}

    @patch("app.tasks.embedding_migration_v4.settings")
    @patch(_OS_CLIENT_PATCH)
    def test_logs_bulk_errors(self, mock_get_client, mock_settings):
        from app.tasks.embedding_migration_v4 import _bulk_write_v4_embeddings

        mock_settings.OPENSEARCH_SPEAKER_INDEX = "speakers"
        mock_client = MagicMock()
        mock_client.bulk.return_value = {
            "errors": True,
            "items": [
                {"index": {"error": {"type": "mapper_parsing_exception", "reason": "bad data"}}}
            ],
        }
        mock_get_client.return_value = mock_client

        # Should still return count (errors are logged, not raised)
        result = _bulk_write_v4_embeddings([{"_id": "x", "data": "bad"}])
        assert result == 1


class TestBuildSpeakerSegments:
    """Tests for _build_speaker_segments."""

    def test_builds_mapping_from_segments(self):
        from app.tasks.embedding_migration_v4 import _build_speaker_segments

        seg1 = MagicMock(speaker_id=1, start_time=0.0, end_time=5.0)
        seg2 = MagicMock(speaker_id=1, start_time=5.0, end_time=10.0)
        seg3 = MagicMock(speaker_id=2, start_time=2.0, end_time=8.0)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [seg1, seg2, seg3]

        result = _build_speaker_segments(mock_db, media_file_id=42)

        assert 1 in result
        assert 2 in result
        assert len(result[1]) == 2
        assert len(result[2]) == 1
        assert result[1][0] == {"start": 0.0, "end": 5.0}

    def test_returns_empty_for_no_segments(self):
        from app.tasks.embedding_migration_v4 import _build_speaker_segments

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = _build_speaker_segments(mock_db, media_file_id=999)
        assert result == {}


class TestPrepareFileForGpu:
    """Tests for _prepare_file_for_gpu I/O preparation."""

    @patch("app.tasks.embedding_migration_v4._build_speaker_segments")
    @patch("app.tasks.embedding_migration_v4.session_scope")
    def test_returns_none_when_no_speakers(self, mock_scope, mock_build_segs):
        from app.tasks.embedding_migration_v4 import _prepare_file_for_gpu

        mock_db = MagicMock()
        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

        mock_media_file = MagicMock(id=1, user_id=1, storage_path="test.wav")
        mock_get_file = MagicMock(return_value=mock_media_file)
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = _prepare_file_for_gpu("test-uuid", MagicMock(), mock_get_file, MagicMock())
        assert result is None

    @patch("app.tasks.embedding_migration_v4._build_speaker_segments")
    @patch("app.tasks.embedding_migration_v4.session_scope")
    def test_raises_when_file_not_found(self, mock_scope, mock_build_segs):
        from app.tasks.embedding_migration_v4 import _prepare_file_for_gpu

        mock_db = MagicMock()
        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

        mock_get_file = MagicMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            _prepare_file_for_gpu("missing-uuid", MagicMock(), mock_get_file, MagicMock())


class TestExtractSpeakerEmbeddingFromPrepared:
    """Tests for _extract_speaker_embedding_from_prepared."""

    def _make_prepared(self, speaker_segments=None):
        from app.tasks.embedding_migration_v4 import PreparedFile

        return PreparedFile(
            file_uuid="test-uuid",
            audio_source="http://minio:9000/test/audio.mp4?presigned=1",
            speakers=[],
            speaker_segments=speaker_segments or {},
            media_file_id=1,
            media_file_user_id=1,
            speaker_profiles={},
        )

    def test_returns_none_when_speaker_not_in_segments(self):
        from app.tasks.embedding_migration_v4 import SpeakerSnapshot
        from app.tasks.embedding_migration_v4 import _extract_speaker_embedding_from_prepared

        speaker = SpeakerSnapshot(id=99, uuid="sp-99", name="X", profile_id=None)
        prepared = self._make_prepared({1: [{"start": 0, "end": 5}]})

        result = _extract_speaker_embedding_from_prepared(speaker, prepared, MagicMock())
        assert result is None

    def test_returns_none_when_segments_empty(self):
        from app.tasks.embedding_migration_v4 import SpeakerSnapshot
        from app.tasks.embedding_migration_v4 import _extract_speaker_embedding_from_prepared

        speaker = SpeakerSnapshot(id=1, uuid="sp-1", name="A", profile_id=None)
        prepared = self._make_prepared({1: []})

        result = _extract_speaker_embedding_from_prepared(speaker, prepared, MagicMock())
        assert result is None

    def test_skips_short_segments(self):
        from app.tasks.embedding_migration_v4 import SpeakerSnapshot
        from app.tasks.embedding_migration_v4 import _extract_speaker_embedding_from_prepared

        speaker = SpeakerSnapshot(id=1, uuid="sp-uuid", name="Alice", profile_id=None)
        prepared = self._make_prepared({1: [{"start": 0, "end": 0.3}]})
        mock_service = MagicMock()

        result = _extract_speaker_embedding_from_prepared(speaker, prepared, mock_service)
        assert result is None
        mock_service.extract_embedding_from_segment.assert_not_called()

    def test_returns_doc_with_aggregated_embedding(self):
        import numpy as np

        from app.tasks.embedding_migration_v4 import SpeakerSnapshot
        from app.tasks.embedding_migration_v4 import _extract_speaker_embedding_from_prepared

        speaker = SpeakerSnapshot(id=1, uuid="sp-uuid", name="Alice", profile_id=None)
        prepared = self._make_prepared({1: [{"start": 0, "end": 5.0}, {"start": 5, "end": 12.0}]})
        prepared.speaker_profiles = {1: None}

        mock_embedding = np.random.randn(256)
        mock_service = MagicMock()
        mock_service.extract_embedding_from_segment.return_value = mock_embedding
        mock_service.aggregate_embeddings.return_value = mock_embedding

        result = _extract_speaker_embedding_from_prepared(speaker, prepared, mock_service)

        assert result is not None
        assert result["_id"] == "sp-uuid"
        assert result["speaker_id"] == 1
        assert result["name"] == "Alice"
        assert result["media_file_id"] == 1
        assert result["segment_count"] == 2
        assert len(result["embedding"]) == 256


class TestGetMigrationStatus:
    """Tests for get_migration_status."""

    @patch("app.tasks.embedding_migration_v4.migration_lock")
    @patch("app.tasks.embedding_migration_v4.EmbeddingModeService")
    @patch(_OS_CLIENT_PATCH)
    def test_returns_error_when_no_client(self, mock_get_client, mock_mode, mock_lock):
        from app.tasks.embedding_migration_v4 import get_migration_status

        mock_get_client.return_value = None
        result = get_migration_status()
        assert result["status"] == "error"

    @patch("app.tasks.embedding_migration_v4.migration_lock")
    @patch("app.tasks.embedding_migration_v4.EmbeddingModeService")
    @patch(_OS_CLIENT_PATCH)
    def test_includes_transcription_paused_flag(self, mock_get_client, mock_mode, mock_lock):
        from app.tasks.embedding_migration_v4 import get_migration_status

        mock_client = MagicMock()
        mock_client.indices.exists.return_value = False
        mock_client.count.return_value = {"count": 0}
        mock_get_client.return_value = mock_client
        mock_mode.detect_mode.return_value = "v3"
        mock_lock.is_active.return_value = True

        result = get_migration_status()
        assert result["transcription_paused"] is True
        assert result["migration_needed"] is True


class TestGpuExtractAndWrite:
    """Tests for _gpu_extract_and_write parallel pipeline.

    The pipeline: parallel ffmpeg seeks → sequential GPU inference → bulk write.
    No temp dirs are created — audio is streamed via presigned URLs.
    """

    @staticmethod
    def _make_prepared(speakers, speaker_segments):
        from app.tasks.embedding_migration_v4 import PreparedFile

        return PreparedFile(
            file_uuid="test-uuid",
            audio_source="http://minio:9000/test/audio.mp4?presigned=1",
            speakers=speakers,
            speaker_segments=speaker_segments,
            media_file_id=1,
            media_file_user_id=1,
            speaker_profiles={},
        )

    @patch("app.tasks.embedding_migration_v4._bulk_write_v4_embeddings")
    def test_returns_zero_when_no_segments(self, mock_bulk):
        from app.tasks.embedding_migration_v4 import SpeakerSnapshot
        from app.tasks.embedding_migration_v4 import _gpu_extract_and_write

        speaker = SpeakerSnapshot(id=1, uuid="sp-1", name="Alice", profile_id=None)
        prepared = self._make_prepared([speaker], {})

        result = _gpu_extract_and_write(prepared, MagicMock())
        assert result == 0
        mock_bulk.assert_not_called()

    @patch("app.tasks.embedding_migration_v4._bulk_write_v4_embeddings")
    @patch("app.services.speaker_embedding_service.SpeakerEmbeddingService._load_audio_segment")
    def test_extracts_and_bulk_writes(self, mock_load_seg, mock_bulk):
        import numpy as np
        import torch

        from app.tasks.embedding_migration_v4 import SpeakerSnapshot
        from app.tasks.embedding_migration_v4 import _gpu_extract_and_write

        speaker = SpeakerSnapshot(id=1, uuid="sp-1", name="Alice", profile_id=None)
        segments = {1: [{"start": 0.0, "end": 5.0}, {"start": 6.0, "end": 12.0}]}
        prepared = self._make_prepared([speaker], segments)

        # Mock _load_audio_segment to return a dummy waveform
        mock_load_seg.return_value = torch.zeros(1, 16000)

        # Mock embedding service methods
        mock_service = MagicMock()
        mock_embedding = np.random.randn(256)
        mock_service.extract_embedding_from_waveform.return_value = mock_embedding
        mock_service.aggregate_embeddings.return_value = mock_embedding
        mock_bulk.return_value = 1

        result = _gpu_extract_and_write(prepared, mock_service)

        assert result == 1
        mock_bulk.assert_called_once()
        docs = mock_bulk.call_args[0][0]
        assert len(docs) == 1
        assert docs[0]["speaker_id"] == 1
        assert docs[0]["_id"] == "sp-1"

    @patch("app.tasks.embedding_migration_v4._bulk_write_v4_embeddings")
    @patch("app.services.speaker_embedding_service.SpeakerEmbeddingService._load_audio_segment")
    def test_skips_short_segments(self, mock_load_seg, mock_bulk):
        from app.tasks.embedding_migration_v4 import SpeakerSnapshot
        from app.tasks.embedding_migration_v4 import _gpu_extract_and_write

        speaker = SpeakerSnapshot(id=1, uuid="sp-1", name="A", profile_id=None)
        # All segments under 0.5s threshold
        segments = {1: [{"start": 0.0, "end": 0.3}, {"start": 1.0, "end": 1.4}]}
        prepared = self._make_prepared([speaker], segments)

        result = _gpu_extract_and_write(prepared, MagicMock())
        assert result == 0
        mock_load_seg.assert_not_called()
