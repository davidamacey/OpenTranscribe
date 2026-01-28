"""Celery task for search indexing after transcription completion."""
import logging
import time
from typing import Any

from app.core.celery import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="index_transcript_search",
    queue="cpu",
    max_retries=3,
    default_retry_delay=30,
)
def index_transcript_search_task(  # noqa: C901
    self,
    file_id: int,
    file_uuid: str,
    user_id: int,
) -> dict[str, Any]:
    """Index a transcript in OpenSearch as a tracked Celery task.

    Creates a Task database record for visibility in the file status modal.
    Loads transcript segments from PostgreSQL and indexes them with embeddings.

    Args:
        file_id: Media file integer ID.
        file_uuid: Media file UUID string.
        user_id: Owner user ID.

    Returns:
        Dict with indexing stats and timing.
    """
    from app.db.session_utils import get_refreshed_object
    from app.db.session_utils import session_scope
    from app.models.media import MediaFile
    from app.models.media import Speaker
    from app.models.media import TranscriptSegment
    from app.services.search.indexing_service import TranscriptIndexingService
    from app.utils.task_utils import create_task_record
    from app.utils.task_utils import update_task_status

    task_id = self.request.id
    logger.info(f"Search indexing task {task_id} started for file {file_uuid}")

    # Create a tracked Task record
    with session_scope() as db:
        create_task_record(db, task_id, user_id, file_id, "search_indexing")
        update_task_status(db, task_id, "in_progress", progress=0.1)

    total_start = time.time()

    try:
        # Load transcript segments from PostgreSQL
        with session_scope() as db:
            update_task_status(db, task_id, "in_progress", progress=0.2)

            media_file = get_refreshed_object(db, MediaFile, file_id)
            if not media_file:
                raise ValueError(f"Media file {file_id} not found")

            segments = (
                db.query(TranscriptSegment)
                .filter(TranscriptSegment.media_file_id == file_id)
                .order_by(TranscriptSegment.start_time)
                .all()
            )

            if not segments:
                logger.warning(f"No segments found for file {file_uuid}, skipping indexing")
                update_task_status(db, task_id, "completed", progress=1.0, completed=True)
                return {"status": "skipped", "reason": "no_segments"}

            # Batch-fetch speakers
            speaker_ids = {seg.speaker_id for seg in segments if seg.speaker_id}
            speakers_map: dict[int, str] = {}
            if speaker_ids:
                speaker_rows = db.query(Speaker).filter(Speaker.id.in_(speaker_ids)).all()
                speakers_map = {s.id: s.display_name or s.name or "Unknown" for s in speaker_rows}

            # Convert to dicts
            segment_dicts = []
            for seg in segments:
                speaker_name = (
                    speakers_map.get(seg.speaker_id, "Unknown") if seg.speaker_id else "Unknown"
                )
                segment_dicts.append(
                    {
                        "start": float(seg.start_time),
                        "end": float(seg.end_time),
                        "text": seg.text or "",
                        "speaker": speaker_name,
                    }
                )

            # Extract metadata
            title = media_file.title or media_file.filename or f"File {file_id}"
            speaker_names = list(
                set(str(s["speaker"]) for s in segment_dicts if s["speaker"] != "Unknown")
            )
            tag_names = []
            if hasattr(media_file, "tags") and media_file.tags:
                tag_names = [t.name for t in media_file.tags]
            upload_time = (
                (media_file.creation_date or media_file.upload_time).isoformat()
                if media_file and (media_file.creation_date or media_file.upload_time)
                else None
            )
            language = media_file.language or "en"
            content_type = media_file.content_type or ""
            duration = media_file.duration
            file_size = media_file.file_size
            collection_ids = []
            if hasattr(media_file, "collections") and media_file.collections:
                collection_ids = [c.id for c in media_file.collections]

        # Index in OpenSearch
        with session_scope() as db:
            update_task_status(db, task_id, "in_progress", progress=0.4)

        indexing_service = TranscriptIndexingService()
        result = indexing_service.index_transcript_chunks(
            file_id=file_id,
            file_uuid=file_uuid,
            user_id=user_id,
            segments=segment_dicts,
            title=title,
            speakers=speaker_names,
            tags=tag_names,
            upload_time=upload_time,
            language=language,
            content_type=content_type,
            duration=duration,
            file_size=file_size,
            collection_ids=collection_ids,
        )

        total_ms = round((time.time() - total_start) * 1000)

        # Build timing result
        if isinstance(result, dict):
            timing = result
        else:
            timing = {"chunk_count": result, "total_ms": total_ms}

        # Mark task as completed
        with session_scope() as db:
            update_task_status(db, task_id, "completed", progress=1.0, completed=True)

        # Send notification
        _send_indexing_notification(user_id, file_id, timing)

        logger.info(
            f"Search indexing completed for file {file_uuid}: "
            f"{timing.get('chunk_count', 0)} chunks in {total_ms}ms"
        )
        return {"status": "success", "file_id": file_id, **timing}

    except Exception as exc:
        logger.error(f"Search indexing failed for file {file_uuid}: {exc}")

        # Mark task as failed
        try:
            with session_scope() as db:
                update_task_status(db, task_id, "failed", error_message=str(exc))
        except Exception:
            logger.error(f"Failed to update task status for {task_id}")

        # Retry with exponential backoff for transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30 * (2**self.request.retries)) from exc

        return {"status": "failed", "file_id": file_id, "error": str(exc)}


def _send_indexing_notification(user_id: int, file_id: int, timing: dict[str, Any]) -> None:
    """Send search indexing completion notification via WebSocket."""
    try:
        import asyncio

        from app.api.websockets import send_notification

        data = {
            "file_id": file_id,
            "timing": timing,
        }
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(send_notification(user_id, "search_indexing_complete", data))
            else:
                loop.run_until_complete(
                    send_notification(user_id, "search_indexing_complete", data)
                )
        except RuntimeError:
            asyncio.run(send_notification(user_id, "search_indexing_complete", data))
    except Exception as e:
        logger.debug(f"Failed to send search indexing notification: {e}")
