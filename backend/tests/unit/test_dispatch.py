"""Tests for transcription pipeline dispatch: error handling, batch dispatch, and helpers."""

from unittest.mock import MagicMock
from unittest.mock import patch

from app.models.media import FileStatus

# Patch paths — these are imported at the top of dispatch.py
_DISPATCH = "app.tasks.transcription.dispatch"
_SESSION_SCOPE = f"{_DISPATCH}.session_scope"
_UPDATE_FILE_STATUS = f"{_DISPATCH}.update_media_file_status"
_UPDATE_TASK_STATUS = f"{_DISPATCH}.update_task_status"
_CREATE_TASK_RECORD = f"{_DISPATCH}.create_task_record"
_RESOLVE_GPU_QUEUE = f"{_DISPATCH}._resolve_gpu_queue"

# Lazy imports inside on_pipeline_error — patch at source
_CLEANUP_TEMP = "app.services.minio_service.cleanup_temp_audio"
_GET_FILE_BY_UUID = "app.utils.uuid_helpers.get_file_by_uuid"
_SEND_ERROR = "app.tasks.transcription.notifications.send_error_notification"
_LOG_OOM = f"{_DISPATCH}._log_oom_diagnostics"


class TestGetPipelineErrorMessage:
    """Tests for _get_pipeline_error_message()."""

    def test_oom_returns_gpu_message(self):
        from app.tasks.transcription.dispatch import _get_pipeline_error_message

        result = _get_pipeline_error_message("CUDA out of memory", is_oom=True)
        assert "GPU ran out of memory" in result

    def test_non_oom_returns_generic_message(self):
        from app.tasks.transcription.dispatch import _get_pipeline_error_message

        result = _get_pipeline_error_message("some traceback", is_oom=False)
        assert result == "Transcription pipeline failed unexpectedly"

    def test_oom_flag_takes_precedence(self):
        from app.tasks.transcription.dispatch import _get_pipeline_error_message

        # Even with empty error message, is_oom flag drives the output
        result = _get_pipeline_error_message("", is_oom=True)
        assert "GPU ran out of memory" in result

    def test_oom_text_without_flag_returns_generic(self):
        from app.tasks.transcription.dispatch import _get_pipeline_error_message

        # Error text mentions OOM but flag is False — flag is what matters
        result = _get_pipeline_error_message("CUDA out of memory", is_oom=False)
        assert result == "Transcription pipeline failed unexpectedly"


def _make_session_scope_mock():
    """Helper: create a mock session_scope context manager returning a mock db."""
    mock_db = MagicMock()
    mock_scope = MagicMock()
    mock_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
    mock_scope.return_value.__exit__ = MagicMock(return_value=False)
    return mock_scope, mock_db


def _make_task_mock(status="in_progress", error_message=""):
    """Helper: create a mock Task object for DB queries."""
    mock_task = MagicMock()
    mock_task.status = status
    mock_task.error_message = error_message
    return mock_task


def _make_media_file_mock(status=FileStatus.PROCESSING, file_id=42, user_id=1):
    """Helper: create a mock MediaFile object."""
    mock_file = MagicMock()
    mock_file.status = status
    mock_file.id = file_id
    mock_file.user_id = user_id
    return mock_file


class TestOnPipelineError:
    """Tests for on_pipeline_error() Celery task."""

    @patch(_SEND_ERROR)
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_LOG_OOM)
    @patch(_GET_FILE_BY_UUID)
    @patch(_SESSION_SCOPE)
    @patch(_CLEANUP_TEMP)
    def test_cleanup_temp_audio_called(
        self,
        mock_cleanup,
        mock_scope,
        mock_get_file,
        mock_log_oom,
        mock_update_file,
        mock_update_task,
        mock_send_error,
    ):
        from app.tasks.transcription.dispatch import on_pipeline_error

        scope, mock_db = _make_session_scope_mock()
        mock_scope.side_effect = scope.side_effect
        mock_scope.return_value = scope.return_value
        mock_get_file.return_value = _make_media_file_mock()
        mock_db.query.return_value.filter.return_value.first.return_value = _make_task_mock()

        on_pipeline_error("file-uuid-1", "task-id-1")

        mock_cleanup.assert_called_once_with("file-uuid-1")

    @patch(_SEND_ERROR)
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_LOG_OOM)
    @patch(_GET_FILE_BY_UUID)
    @patch(_SESSION_SCOPE)
    @patch(_CLEANUP_TEMP)
    def test_oom_detected_from_cuda_message(
        self,
        mock_cleanup,
        mock_scope,
        mock_get_file,
        mock_log_oom,
        mock_update_file,
        mock_update_task,
        mock_send_error,
    ):
        from app.tasks.transcription.dispatch import on_pipeline_error

        scope, mock_db = _make_session_scope_mock()
        mock_scope.side_effect = scope.side_effect
        mock_scope.return_value = scope.return_value
        mock_get_file.return_value = _make_media_file_mock()
        task = _make_task_mock(error_message="CUDA out of memory in allocator")
        mock_db.query.return_value.filter.return_value.first.return_value = task

        on_pipeline_error("file-uuid-1", "task-id-1")

        mock_log_oom.assert_called_once()
        # Task error message should be the user-friendly OOM message
        mock_update_task.assert_called_once()
        error_msg = mock_update_task.call_args[1].get(
            "error_message",
            mock_update_task.call_args[0][3] if len(mock_update_task.call_args[0]) > 3 else "",
        )
        assert "GPU ran out of memory" in str(error_msg) or any(
            "GPU ran out of memory" in str(a)
            for a in mock_update_task.call_args[0] + tuple(mock_update_task.call_args[1].values())
        )

    @patch(_SEND_ERROR)
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_LOG_OOM)
    @patch(_GET_FILE_BY_UUID)
    @patch(_SESSION_SCOPE)
    @patch(_CLEANUP_TEMP)
    def test_oom_detected_from_oom_error(
        self,
        mock_cleanup,
        mock_scope,
        mock_get_file,
        mock_log_oom,
        mock_update_file,
        mock_update_task,
        mock_send_error,
    ):
        from app.tasks.transcription.dispatch import on_pipeline_error

        scope, mock_db = _make_session_scope_mock()
        mock_scope.side_effect = scope.side_effect
        mock_scope.return_value = scope.return_value
        mock_get_file.return_value = _make_media_file_mock()
        task = _make_task_mock(error_message="OutOfMemoryError: GPU")
        mock_db.query.return_value.filter.return_value.first.return_value = task

        on_pipeline_error("file-uuid-1", "task-id-1")

        mock_log_oom.assert_called_once()

    @patch(_SEND_ERROR)
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_LOG_OOM)
    @patch(_GET_FILE_BY_UUID)
    @patch(_SESSION_SCOPE)
    @patch(_CLEANUP_TEMP)
    def test_postprocess_only_keeps_completed(
        self,
        mock_cleanup,
        mock_scope,
        mock_get_file,
        mock_log_oom,
        mock_update_file,
        mock_update_task,
        mock_send_error,
    ):
        """When task.status == 'completed', postprocess failed after segments saved.
        File should stay COMPLETED — early return, no status changes."""
        from app.tasks.transcription.dispatch import on_pipeline_error

        scope, mock_db = _make_session_scope_mock()
        mock_scope.side_effect = scope.side_effect
        mock_scope.return_value = scope.return_value
        mock_get_file.return_value = _make_media_file_mock()
        task = _make_task_mock(status="completed", error_message="postprocess error")
        mock_db.query.return_value.filter.return_value.first.return_value = task

        on_pipeline_error("file-uuid-1", "task-id-1")

        # Should NOT update file or task status — early return
        mock_update_file.assert_not_called()
        mock_update_task.assert_not_called()
        mock_send_error.assert_not_called()

    @patch(_SEND_ERROR)
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_LOG_OOM)
    @patch(_GET_FILE_BY_UUID)
    @patch(_SESSION_SCOPE)
    @patch(_CLEANUP_TEMP)
    def test_marks_error_for_processing_file(
        self,
        mock_cleanup,
        mock_scope,
        mock_get_file,
        mock_log_oom,
        mock_update_file,
        mock_update_task,
        mock_send_error,
    ):
        from app.tasks.transcription.dispatch import on_pipeline_error

        scope, mock_db = _make_session_scope_mock()
        mock_scope.side_effect = scope.side_effect
        mock_scope.return_value = scope.return_value
        media_file = _make_media_file_mock(status=FileStatus.PROCESSING, file_id=42, user_id=1)
        mock_get_file.return_value = media_file
        task = _make_task_mock(status="in_progress")
        mock_db.query.return_value.filter.return_value.first.return_value = task

        on_pipeline_error("file-uuid-1", "task-id-1")

        mock_update_file.assert_called_once()
        assert mock_update_file.call_args[0][1] == 42  # file_id
        assert mock_update_file.call_args[0][2] == FileStatus.ERROR

    @patch(_SEND_ERROR)
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_LOG_OOM)
    @patch(_GET_FILE_BY_UUID)
    @patch(_SESSION_SCOPE)
    @patch(_CLEANUP_TEMP)
    def test_skips_already_errored_file(
        self,
        mock_cleanup,
        mock_scope,
        mock_get_file,
        mock_log_oom,
        mock_update_file,
        mock_update_task,
        mock_send_error,
    ):
        from app.tasks.transcription.dispatch import on_pipeline_error

        scope, mock_db = _make_session_scope_mock()
        mock_scope.side_effect = scope.side_effect
        mock_scope.return_value = scope.return_value
        media_file = _make_media_file_mock(status=FileStatus.ERROR)
        mock_get_file.return_value = media_file
        task = _make_task_mock(status="in_progress")
        mock_db.query.return_value.filter.return_value.first.return_value = task

        on_pipeline_error("file-uuid-1", "task-id-1")

        # File already ERROR — should NOT update file status
        mock_update_file.assert_not_called()

    @patch(_SEND_ERROR)
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_LOG_OOM)
    @patch(_GET_FILE_BY_UUID)
    @patch(_SESSION_SCOPE)
    @patch(_CLEANUP_TEMP)
    def test_skips_already_failed_task(
        self,
        mock_cleanup,
        mock_scope,
        mock_get_file,
        mock_log_oom,
        mock_update_file,
        mock_update_task,
        mock_send_error,
    ):
        from app.tasks.transcription.dispatch import on_pipeline_error

        scope, mock_db = _make_session_scope_mock()
        mock_scope.side_effect = scope.side_effect
        mock_scope.return_value = scope.return_value
        mock_get_file.return_value = _make_media_file_mock()
        task = _make_task_mock(status="failed")
        mock_db.query.return_value.filter.return_value.first.return_value = task

        on_pipeline_error("file-uuid-1", "task-id-1")

        # Task already failed — should NOT update task status
        mock_update_task.assert_not_called()

    @patch(_SEND_ERROR)
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_LOG_OOM)
    @patch(_GET_FILE_BY_UUID)
    @patch(_SESSION_SCOPE)
    @patch(_CLEANUP_TEMP)
    def test_sends_error_notification(
        self,
        mock_cleanup,
        mock_scope,
        mock_get_file,
        mock_log_oom,
        mock_update_file,
        mock_update_task,
        mock_send_error,
    ):
        from app.tasks.transcription.dispatch import on_pipeline_error

        scope, mock_db = _make_session_scope_mock()
        mock_scope.side_effect = scope.side_effect
        mock_scope.return_value = scope.return_value
        media_file = _make_media_file_mock(file_id=42, user_id=7)
        mock_get_file.return_value = media_file
        task = _make_task_mock(status="in_progress")
        mock_db.query.return_value.filter.return_value.first.return_value = task

        on_pipeline_error("file-uuid-1", "task-id-1")

        mock_send_error.assert_called_once_with(7, 42, "Transcription pipeline failed unexpectedly")

    @patch(_SEND_ERROR)
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_LOG_OOM)
    @patch(_GET_FILE_BY_UUID)
    @patch(_SESSION_SCOPE)
    @patch(_CLEANUP_TEMP)
    def test_handles_db_exception_gracefully(
        self,
        mock_cleanup,
        mock_scope,
        mock_get_file,
        mock_log_oom,
        mock_update_file,
        mock_update_task,
        mock_send_error,
    ):
        """If session_scope raises, the error is caught and logged — no crash."""
        from app.tasks.transcription.dispatch import on_pipeline_error

        mock_scope.return_value.__enter__ = MagicMock(side_effect=RuntimeError("DB down"))
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

        # Should not raise
        on_pipeline_error("file-uuid-1", "task-id-1")

        mock_update_file.assert_not_called()
        mock_update_task.assert_not_called()


class TestDispatchBatchTranscription:
    """Tests for dispatch_batch_transcription()."""

    def _setup_db_mock(self, mock_scope, file_uuids_to_ids):
        """Set up session_scope mock that returns MediaFile objects for known UUIDs."""
        mock_db = MagicMock()
        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

        def query_side_effect(*args):
            mock_query = MagicMock()

            def filter_side_effect(*filter_args):
                mock_filter = MagicMock()

                def first_side_effect():
                    # Check if any known UUID is being queried
                    for uuid_str, (fid, uid) in file_uuids_to_ids.items():
                        # The filter call uses MediaFile.uuid == file_uuid
                        if any(uuid_str in str(a) for a in filter_args):
                            mock_file = MagicMock()
                            mock_file.id = fid
                            mock_file.user_id = uid
                            return mock_file
                    return None

                mock_filter.first = first_side_effect
                return mock_filter

            mock_query.filter = filter_side_effect
            return mock_query

        mock_db.query = query_side_effect
        return mock_db

    @patch(f"{_DISPATCH}.group")
    @patch(f"{_DISPATCH}.chain")
    @patch(_RESOLVE_GPU_QUEUE, return_value="gpu")
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_CREATE_TASK_RECORD)
    @patch(_SESSION_SCOPE)
    def test_returns_dict_format(
        self,
        mock_scope,
        mock_create_task,
        mock_update_file,
        mock_update_task,
        mock_resolve,
        mock_chain,
        mock_group,
    ):
        from app.tasks.transcription.dispatch import dispatch_batch_transcription

        # Set up DB to find both files
        mock_db = MagicMock()
        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)
        mock_file = MagicMock()
        mock_file.id = 1
        mock_file.user_id = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file

        mock_chain_instance = MagicMock()
        mock_chain.return_value = mock_chain_instance
        mock_group_result = MagicMock()
        mock_group_result.id = "batch-123"
        mock_group.return_value.apply_async.return_value = mock_group_result

        result = dispatch_batch_transcription(["uuid-1", "uuid-2"], gpu_queue="gpu")

        assert isinstance(result, dict)
        assert "batch_id" in result
        assert "task_ids" in result
        assert result["batch_id"] == "batch-123"
        assert len(result["task_ids"]) == 2

    @patch(f"{_DISPATCH}.group")
    @patch(f"{_DISPATCH}.chain")
    @patch(_RESOLVE_GPU_QUEUE, return_value="gpu")
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_CREATE_TASK_RECORD)
    @patch(_SESSION_SCOPE)
    def test_missing_file_skipped(
        self,
        mock_scope,
        mock_create_task,
        mock_update_file,
        mock_update_task,
        mock_resolve,
        mock_chain,
        mock_group,
    ):
        from app.tasks.transcription.dispatch import dispatch_batch_transcription

        mock_db = MagicMock()
        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

        call_count = [0]

        def first_side_effect():
            call_count[0] += 1
            if call_count[0] == 2:  # Second file not found
                return None
            mock_file = MagicMock()
            mock_file.id = call_count[0]
            mock_file.user_id = 1
            return mock_file

        mock_db.query.return_value.filter.return_value.first = first_side_effect

        mock_chain.return_value = MagicMock()
        mock_group_result = MagicMock()
        mock_group_result.id = "batch-456"
        mock_group.return_value.apply_async.return_value = mock_group_result

        result = dispatch_batch_transcription(["uuid-1", "uuid-missing", "uuid-3"], gpu_queue="gpu")

        assert len(result["task_ids"]) == 2  # Only 2 of 3 succeeded

    @patch(f"{_DISPATCH}.group")
    @patch(f"{_DISPATCH}.chain")
    @patch(_RESOLVE_GPU_QUEUE, return_value="gpu")
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_CREATE_TASK_RECORD)
    @patch(_SESSION_SCOPE)
    def test_all_missing_returns_empty(
        self,
        mock_scope,
        mock_create_task,
        mock_update_file,
        mock_update_task,
        mock_resolve,
        mock_chain,
        mock_group,
    ):
        from app.tasks.transcription.dispatch import dispatch_batch_transcription

        mock_db = MagicMock()
        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = dispatch_batch_transcription(["uuid-1", "uuid-2"], gpu_queue="gpu")

        assert result == {"batch_id": None, "task_ids": []}
        mock_group.assert_not_called()

    @patch("app.core.redis.get_redis")
    @patch(f"{_DISPATCH}.group")
    @patch(f"{_DISPATCH}.chain")
    @patch(_RESOLVE_GPU_QUEUE, return_value="gpu")
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_CREATE_TASK_RECORD)
    @patch(_SESSION_SCOPE)
    def test_batch_metadata_stored_in_redis(
        self,
        mock_scope,
        mock_create_task,
        mock_update_file,
        mock_update_task,
        mock_resolve,
        mock_chain,
        mock_group,
        mock_get_redis,
    ):
        from app.tasks.transcription.dispatch import dispatch_batch_transcription

        mock_db = MagicMock()
        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)
        mock_file = MagicMock()
        mock_file.id = 1
        mock_file.user_id = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file

        mock_chain.return_value = MagicMock()
        mock_group_result = MagicMock()
        mock_group_result.id = "batch-789"
        mock_group.return_value.apply_async.return_value = mock_group_result

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        dispatch_batch_transcription(["uuid-1"], gpu_queue="gpu")

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "batch:batch-789"
        assert call_args[1]["ex"] == 86400  # 24h TTL

    @patch("app.core.redis.get_redis")
    @patch(f"{_DISPATCH}.group")
    @patch(f"{_DISPATCH}.chain")
    @patch(_RESOLVE_GPU_QUEUE, return_value="gpu")
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_CREATE_TASK_RECORD)
    @patch(_SESSION_SCOPE)
    def test_redis_failure_non_fatal(
        self,
        mock_scope,
        mock_create_task,
        mock_update_file,
        mock_update_task,
        mock_resolve,
        mock_chain,
        mock_group,
        mock_get_redis,
    ):
        from app.tasks.transcription.dispatch import dispatch_batch_transcription

        mock_db = MagicMock()
        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)
        mock_file = MagicMock()
        mock_file.id = 1
        mock_file.user_id = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file

        mock_chain.return_value = MagicMock()
        mock_group_result = MagicMock()
        mock_group_result.id = "batch-fail"
        mock_group.return_value.apply_async.return_value = mock_group_result

        mock_get_redis.side_effect = RuntimeError("Redis down")

        # Should not raise
        result = dispatch_batch_transcription(["uuid-1"], gpu_queue="gpu")

        assert result["batch_id"] == "batch-fail"
        assert len(result["task_ids"]) == 1

    @patch(f"{_DISPATCH}.group")
    @patch(f"{_DISPATCH}.chain")
    @patch(_RESOLVE_GPU_QUEUE, return_value="gpu")
    @patch(_UPDATE_TASK_STATUS)
    @patch(_UPDATE_FILE_STATUS)
    @patch(_CREATE_TASK_RECORD)
    @patch(_SESSION_SCOPE)
    def test_group_apply_async_called(
        self,
        mock_scope,
        mock_create_task,
        mock_update_file,
        mock_update_task,
        mock_resolve,
        mock_chain,
        mock_group,
    ):
        from app.tasks.transcription.dispatch import dispatch_batch_transcription

        mock_db = MagicMock()
        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)
        mock_file = MagicMock()
        mock_file.id = 1
        mock_file.user_id = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file

        mock_chain.return_value = MagicMock()
        mock_group_instance = MagicMock()
        mock_group_result = MagicMock()
        mock_group_result.id = "batch-async"
        mock_group_instance.apply_async.return_value = mock_group_result
        mock_group.return_value = mock_group_instance

        dispatch_batch_transcription(["uuid-1", "uuid-2"], gpu_queue="gpu")

        mock_group_instance.apply_async.assert_called_once()
