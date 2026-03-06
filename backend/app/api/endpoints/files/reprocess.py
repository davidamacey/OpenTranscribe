import logging

from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.models.media import FileStatus
from app.models.media import MediaFile
from app.models.user import User
from app.services import system_settings_service
from app.tasks.transcription import transcribe_audio_task

logger = logging.getLogger(__name__)


def clear_existing_transcription_data(db: Session, media_file: MediaFile) -> None:
    """
    Clear existing transcription data for reprocessing.

    Args:
        db: Database session
        media_file: MediaFile to clear data for
    """
    try:
        # Clear transcript-related fields that exist on the MediaFile model
        media_file.summary_data = None  # type: ignore[assignment]
        media_file.summary_opensearch_id = None  # type: ignore[assignment]  # Clear OpenSearch summary ID for regeneration
        media_file.summary_status = "pending"  # type: ignore[assignment]  # Reset summary status for regeneration
        media_file.translated_text = None  # type: ignore[assignment]
        media_file.waveform_data = None  # type: ignore[assignment]  # Clear waveform data for regeneration

        # Clear existing transcript segments
        from app.models.media import Analytics
        from app.models.media import Speaker
        from app.models.media import TranscriptSegment

        # Delete existing transcript segments (this will cascade and handle relationships)
        existing_segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.media_file_id == media_file.id)
            .all()
        )
        for segment in existing_segments:
            db.delete(segment)

        # Clear any existing speaker data
        existing_speakers = db.query(Speaker).filter(Speaker.media_file_id == media_file.id).all()
        for speaker in existing_speakers:
            db.delete(speaker)

        # Clear any existing analytics data
        existing_analytics = (
            db.query(Analytics).filter(Analytics.media_file_id == media_file.id).first()
        )
        if existing_analytics:
            db.delete(existing_analytics)

        db.commit()
        logger.info(f"Cleared existing transcription data for file {media_file.id}")

    except Exception as e:
        logger.error(f"Error clearing transcription data for file {media_file.id}: {e}")
        db.rollback()
        raise


def start_reprocessing_task(
    file_uuid: str,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    num_speakers: int | None = None,
    user_id: int | None = None,
    db=None,
) -> None:
    """
    Start the background reprocessing task.

    Routes the task to the appropriate queue based on the user's active ASR provider
    configuration: cloud providers use the 'cloud-asr' queue while the local GPU
    provider uses the 'gpu' queue.

    Args:
        file_uuid: UUID of the media file to reprocess
        min_speakers: Optional minimum number of speakers for diarization
        max_speakers: Optional maximum number of speakers for diarization
        num_speakers: Optional fixed number of speakers for diarization
        user_id: Optional user ID used to resolve the active ASR provider
        db: Optional database session used to resolve the active ASR provider
    """
    import os

    if os.environ.get("SKIP_CELERY", "False").lower() != "true":
        # Determine which queue to use based on the user's active ASR config
        task_queue = "gpu"
        if user_id is not None and db is not None:
            try:
                from app.services.asr.factory import ASRProviderFactory

                provider = ASRProviderFactory.create_for_user(user_id, db)
                if provider.provider_name != "local":
                    task_queue = "cloud-asr"
                    logger.info(
                        f"Routing reprocess transcription for file {file_uuid} to 'cloud-asr' "
                        f"queue (provider: {provider.provider_name})"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to resolve ASR provider for user {user_id}, "
                    f"defaulting to 'gpu' queue: {e}"
                )

        # Use the same transcription task with speaker parameters - it will handle reprocessing
        transcribe_audio_task.apply_async(
            args=[file_uuid],
            kwargs={
                "min_speakers": min_speakers,
                "max_speakers": max_speakers,
                "num_speakers": num_speakers,
            },
            queue=task_queue,
        )
    else:
        logger.info("Skipping Celery task in test environment")


async def process_file_reprocess(
    file_uuid: str,
    db: Session,
    current_user: User,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    num_speakers: int | None = None,
) -> MediaFile:
    """
    Process file reprocessing request with enhanced error handling.

    Args:
        file_uuid: UUID of the file to reprocess
        db: Database session
        current_user: Current user
        min_speakers: Optional minimum number of speakers for diarization
        max_speakers: Optional maximum number of speakers for diarization
        num_speakers: Optional fixed number of speakers for diarization

    Returns:
        Updated MediaFile object

    Raises:
        HTTPException: If file not found or user doesn't have permission
    """
    from app.utils.task_utils import cancel_active_task
    from app.utils.task_utils import reset_file_for_retry
    from app.utils.uuid_helpers import get_file_by_uuid
    from app.utils.uuid_helpers import get_file_by_uuid_with_permission

    try:
        # Get the file (allow admin to reprocess any file)
        is_admin = current_user.role == "admin"
        if is_admin:
            media_file = get_file_by_uuid(db, file_uuid)
        else:
            media_file = get_file_by_uuid_with_permission(db, file_uuid, int(current_user.id))

        file_id = int(media_file.id)  # Get internal ID for task operations

        # Check if file is currently processing
        if media_file.status == FileStatus.PROCESSING and media_file.active_task_id:
            # Cancel active task first
            logger.info(
                f"Cancelling active task {media_file.active_task_id} before reprocessing file {file_id}"
            )
            cancel_active_task(db, int(file_id))

        # Check if file exists in storage
        if not media_file.storage_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File storage path not found. Cannot reprocess.",
            )

        # Check retry limits based on system settings (unless admin)
        if not is_admin and not system_settings_service.should_retry_file(
            db, int(media_file.retry_count)
        ):
            config = system_settings_service.get_retry_config(db)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File has reached maximum retry attempts ({config['max_retries']}). Contact admin for help.",
            )

        logger.info(
            f"Starting reprocessing for file {file_uuid} (id: {file_id}) by user {current_user.email}"
        )

        # Use the enhanced retry logic
        success = reset_file_for_retry(db, int(file_id), reset_retry_count=False)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reset file for reprocessing",
            )

        # Refresh the file object
        db.refresh(media_file)

        # Start background reprocessing task with speaker parameters
        start_reprocessing_task(
            file_uuid,
            min_speakers,
            max_speakers,
            num_speakers,
            user_id=int(current_user.id),
            db=db,
        )

        logger.info(
            f"Reprocessing task started for file {file_uuid} (id: {file_id}, attempt {media_file.retry_count})"
        )

        return media_file

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error processing reprocess request for file {file_uuid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing reprocess request",
        ) from e
