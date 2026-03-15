"""Tests for transcription postprocess: enrichment task list and background dispatch."""

from unittest.mock import patch

# Patch paths — these are imported at the top of postprocess.py
_POSTPROCESS = "app.tasks.transcription.postprocess"
_INDEX_TRANSCRIPT = f"{_POSTPROCESS}._index_transcript"
_SEND_WS = f"{_POSTPROCESS}.send_ws_event"
_DISPATCH_ATTRS = f"{_POSTPROCESS}._dispatch_speaker_attributes"
_DISPATCH_CLUSTERING = f"{_POSTPROCESS}._dispatch_speaker_clustering"

# Lazy import inside enrich_and_dispatch
_TRIGGER_SUMMARIZATION = "app.tasks.transcription.core.trigger_automatic_summarization"


class TestBuildEnrichmentTaskList:
    """Tests for _build_enrichment_task_list()."""

    def test_none_returns_all_tasks(self):
        from app.tasks.transcription.postprocess import _build_enrichment_task_list

        result = _build_enrichment_task_list(None)
        assert result == [
            "search_indexing",
            "speaker_attributes",
            "speaker_clustering",
            "summarization",
        ]

    def test_empty_list_returns_all_tasks(self):
        from app.tasks.transcription.postprocess import _build_enrichment_task_list

        result = _build_enrichment_task_list([])
        assert result == [
            "search_indexing",
            "speaker_attributes",
            "speaker_clustering",
            "summarization",
        ]

    def test_speaker_llm_excludes_attributes(self):
        from app.tasks.transcription.postprocess import _build_enrichment_task_list

        result = _build_enrichment_task_list(["speaker_llm"])
        assert "speaker_attributes" not in result
        assert "speaker_clustering" in result
        assert "summarization" in result

    def test_speaker_clustering_excludes_clustering(self):
        from app.tasks.transcription.postprocess import _build_enrichment_task_list

        result = _build_enrichment_task_list(["speaker_clustering"])
        assert "speaker_clustering" not in result
        assert "speaker_attributes" in result
        assert "summarization" in result

    def test_summarization_excludes_summarization(self):
        from app.tasks.transcription.postprocess import _build_enrichment_task_list

        result = _build_enrichment_task_list(["summarization"])
        assert "summarization" not in result
        assert "speaker_attributes" in result
        assert "speaker_clustering" in result

    def test_all_exclusions(self):
        from app.tasks.transcription.postprocess import _build_enrichment_task_list

        result = _build_enrichment_task_list(["speaker_llm", "speaker_clustering", "summarization"])
        assert result == ["search_indexing"]

    def test_search_indexing_always_present(self):
        from app.tasks.transcription.postprocess import _build_enrichment_task_list

        # search_indexing cannot be excluded
        for input_val in [None, [], ["speaker_llm"], ["speaker_clustering", "summarization"]]:
            result = _build_enrichment_task_list(input_val)
            assert result[0] == "search_indexing"

    def test_unrelated_tasks_no_effect(self):
        from app.tasks.transcription.postprocess import _build_enrichment_task_list

        result = _build_enrichment_task_list(["analytics", "topic_extraction"])
        assert result == [
            "search_indexing",
            "speaker_attributes",
            "speaker_clustering",
            "summarization",
        ]


class TestEnrichAndDispatch:
    """Tests for enrich_and_dispatch() Celery task."""

    @patch(_DISPATCH_CLUSTERING)
    @patch(_DISPATCH_ATTRS)
    @patch(_TRIGGER_SUMMARIZATION)
    @patch(_SEND_WS)
    @patch(_INDEX_TRANSCRIPT)
    def test_calls_all_downstream_tasks(
        self,
        mock_index,
        mock_ws,
        mock_summarize,
        mock_attrs,
        mock_cluster,
    ):
        from app.tasks.transcription.postprocess import enrich_and_dispatch

        enrich_and_dispatch(
            file_id=1,
            file_uuid="uuid-1",
            user_id=1,
            downstream_tasks=None,
        )

        mock_index.assert_called_once_with(1, "uuid-1", 1)
        mock_summarize.assert_called_once_with(1, "uuid-1", tasks_to_run=None)
        mock_attrs.assert_called_once_with("uuid-1", 1, None)
        mock_cluster.assert_called_once_with("uuid-1", 1, None)

    @patch(_DISPATCH_CLUSTERING)
    @patch(_DISPATCH_ATTRS)
    @patch(_TRIGGER_SUMMARIZATION)
    @patch(_SEND_WS)
    @patch(_INDEX_TRANSCRIPT)
    def test_sends_search_indexing_ws_event(
        self,
        mock_index,
        mock_ws,
        mock_summarize,
        mock_attrs,
        mock_cluster,
    ):
        from app.tasks.transcription.postprocess import enrich_and_dispatch

        enrich_and_dispatch(
            file_id=1,
            file_uuid="uuid-1",
            user_id=7,
            downstream_tasks=None,
        )

        mock_ws.assert_called_once_with(
            7,
            "enrichment_task_complete",
            {"file_id": "uuid-1", "task": "search_indexing"},
        )

    @patch(_DISPATCH_CLUSTERING)
    @patch(_DISPATCH_ATTRS)
    @patch(_TRIGGER_SUMMARIZATION)
    @patch(_SEND_WS)
    @patch(_INDEX_TRANSCRIPT)
    def test_indexing_failure_doesnt_block_others(
        self,
        mock_index,
        mock_ws,
        mock_summarize,
        mock_attrs,
        mock_cluster,
    ):
        from app.tasks.transcription.postprocess import enrich_and_dispatch

        mock_index.side_effect = RuntimeError("OpenSearch down")

        enrich_and_dispatch(
            file_id=1,
            file_uuid="uuid-1",
            user_id=1,
            downstream_tasks=None,
        )

        # WebSocket event NOT sent (indexing failed)
        mock_ws.assert_not_called()
        # But all other tasks still dispatched
        mock_summarize.assert_called_once()
        mock_attrs.assert_called_once()
        mock_cluster.assert_called_once()

    @patch(_DISPATCH_CLUSTERING)
    @patch(_DISPATCH_ATTRS)
    @patch(_TRIGGER_SUMMARIZATION)
    @patch(_SEND_WS)
    @patch(_INDEX_TRANSCRIPT)
    def test_summarization_failure_doesnt_block_others(
        self,
        mock_index,
        mock_ws,
        mock_summarize,
        mock_attrs,
        mock_cluster,
    ):
        from app.tasks.transcription.postprocess import enrich_and_dispatch

        mock_summarize.side_effect = RuntimeError("LLM unavailable")

        enrich_and_dispatch(
            file_id=1,
            file_uuid="uuid-1",
            user_id=1,
            downstream_tasks=None,
        )

        mock_index.assert_called_once()
        mock_attrs.assert_called_once()
        mock_cluster.assert_called_once()

    @patch(_DISPATCH_CLUSTERING)
    @patch(_DISPATCH_ATTRS)
    @patch(_TRIGGER_SUMMARIZATION)
    @patch(_SEND_WS)
    @patch(_INDEX_TRANSCRIPT)
    def test_speaker_attr_failure_doesnt_block_clustering(
        self,
        mock_index,
        mock_ws,
        mock_summarize,
        mock_attrs,
        mock_cluster,
    ):
        from app.tasks.transcription.postprocess import enrich_and_dispatch

        mock_attrs.side_effect = RuntimeError("Speaker service down")

        enrich_and_dispatch(
            file_id=1,
            file_uuid="uuid-1",
            user_id=1,
            downstream_tasks=None,
        )

        mock_cluster.assert_called_once()

    @patch(_DISPATCH_CLUSTERING)
    @patch(_DISPATCH_ATTRS)
    @patch(_TRIGGER_SUMMARIZATION)
    @patch(_SEND_WS)
    @patch(_INDEX_TRANSCRIPT)
    def test_passes_downstream_tasks_through(
        self,
        mock_index,
        mock_ws,
        mock_summarize,
        mock_attrs,
        mock_cluster,
    ):
        from app.tasks.transcription.postprocess import enrich_and_dispatch

        downstream = ["summarization"]
        enrich_and_dispatch(
            file_id=1,
            file_uuid="uuid-1",
            user_id=1,
            downstream_tasks=downstream,
        )

        mock_summarize.assert_called_once_with(1, "uuid-1", tasks_to_run=downstream)
        mock_attrs.assert_called_once_with("uuid-1", 1, downstream)
        mock_cluster.assert_called_once_with("uuid-1", 1, downstream)

    @patch(_DISPATCH_CLUSTERING)
    @patch(_DISPATCH_ATTRS)
    @patch(_TRIGGER_SUMMARIZATION)
    @patch(_SEND_WS)
    @patch(_INDEX_TRANSCRIPT)
    def test_passes_file_params_correctly(
        self,
        mock_index,
        mock_ws,
        mock_summarize,
        mock_attrs,
        mock_cluster,
    ):
        from app.tasks.transcription.postprocess import enrich_and_dispatch

        enrich_and_dispatch(
            file_id=42,
            file_uuid="abc-def-123",
            user_id=7,
            downstream_tasks=None,
        )

        mock_index.assert_called_once_with(42, "abc-def-123", 7)
        mock_summarize.assert_called_once_with(42, "abc-def-123", tasks_to_run=None)
        mock_attrs.assert_called_once_with("abc-def-123", 7, None)
        mock_cluster.assert_called_once_with("abc-def-123", 7, None)
