import logging
import os

from fastapi import HTTPException
from fastapi import status
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.media import Analytics
from app.models.media import Collection
from app.models.media import CollectionMember
from app.models.media import FileStatus
from app.models.media import FileTag
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import Tag
from app.models.media import TranscriptSegment
from app.models.user import User
from app.schemas.media import MediaFileDetail
from app.schemas.media import MediaFileUpdate
from app.schemas.media import TranscriptSegmentUpdate
from app.services.formatting_service import FormattingService
from app.services.minio_service import delete_file
from app.services.opensearch_service import update_transcript_title
from app.services.speaker_status_service import SpeakerStatusService
from app.utils.uuid_helpers import get_file_by_uuid_with_permission

logger = logging.getLogger(__name__)


def get_media_file_by_uuid(
    db: Session, file_uuid: str, user_id: int, is_admin: bool = False
) -> MediaFile:
    """
    Get a media file by UUID and user ID.

    Args:
        db: Database session
        file_uuid: File UUID
        user_id: User ID
        is_admin: Whether the current user is an admin (can access any file)

    Returns:
        MediaFile object

    Raises:
        HTTPException: If file not found or no permission
    """
    # Use UUID helper with admin bypass for permission check
    if is_admin:
        from app.utils.uuid_helpers import get_file_by_uuid

        return get_file_by_uuid(db, file_uuid)
    else:
        return get_file_by_uuid_with_permission(db, file_uuid, user_id)


def get_media_file_by_id(
    db: Session, file_id: int, user_id: int, is_admin: bool = False
) -> MediaFile:
    """
    Get a media file by ID and user ID (legacy - internal use only).

    Args:
        db: Database session
        file_id: File ID
        user_id: User ID
        is_admin: Whether the current user is an admin (can access any file)

    Returns:
        MediaFile object

    Raises:
        HTTPException: If file not found
    """
    # Admin users can access any file, regular users only their own
    query = db.query(MediaFile).filter(MediaFile.id == file_id)
    if not is_admin:
        query = query.filter(MediaFile.user_id == user_id)

    db_file = query.first()

    if not db_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")

    return db_file


def get_file_tags(db: Session, file_id: int) -> list[str]:
    """
    Get tags for a media file.

    Args:
        db: Database session
        file_id: File ID

    Returns:
        List of tag names
    """
    tags = []
    try:
        # Check if tag table exists first
        inspector = inspect(db.bind)
        if "tag" in inspector.get_table_names() and "file_tag" in inspector.get_table_names():
            tags = db.query(Tag.name).join(FileTag).filter(FileTag.media_file_id == file_id).all()
        else:
            logger.warning("Tag tables don't exist yet, skipping tag retrieval")
    except Exception as tag_error:
        logger.error(f"Error getting tags: {tag_error}")
        db.rollback()  # Important to roll back the failed transaction

    return [tag[0] for tag in tags]


def get_file_collections(db: Session, file_id: int, user_id: int) -> list[dict]:
    """
    Get collections that contain a media file.

    Args:
        db: Database session
        file_id: File ID
        user_id: User ID

    Returns:
        List of collection dictionaries
    """
    collections = []
    try:
        # Check if collection tables exist first
        inspector = inspect(db.bind)
        if (
            "collection" in inspector.get_table_names()
            and "collection_member" in inspector.get_table_names()
        ):
            collection_objs = (
                db.query(Collection)
                .join(CollectionMember)
                .filter(
                    CollectionMember.media_file_id == file_id,
                    Collection.user_id == user_id,
                )
                .all()
            )

            # Convert to dictionaries
            collections = [
                {
                    "uuid": str(col.uuid),
                    "name": col.name,
                    "description": col.description,
                    "is_public": col.is_public,
                    "created_at": col.created_at.isoformat() if col.created_at else None,
                    "updated_at": col.updated_at.isoformat() if col.updated_at else None,
                }
                for col in collection_objs
            ]
        else:
            logger.warning("Collection tables don't exist yet, skipping collection retrieval")
    except Exception as collection_error:
        logger.error(f"Error getting collections: {collection_error}")
        db.rollback()  # Important to roll back the failed transaction

    return collections


def set_file_urls(db_file: MediaFile) -> None:
    """
    Set download, preview, and thumbnail URLs for a media file.

    Args:
        db_file: MediaFile object to update
    """
    if db_file.storage_path:
        # Skip S3 operations in test environment
        if os.environ.get("SKIP_S3", "False").lower() == "true":
            db_file.download_url = f"/api/files/{db_file.uuid}/download"
            db_file.preview_url = f"/api/files/{db_file.uuid}/video"
            if db_file.thumbnail_path:
                db_file.thumbnail_url = f"/api/files/{db_file.uuid}/thumbnail"
            return

        # Set URLs for frontend to use (using UUID)
        db_file.download_url = f"/api/files/{db_file.uuid}/download"  # Download endpoint

        # Video files use our video endpoint for optimized streaming
        if db_file.content_type.startswith("video/"):
            db_file.preview_url = f"/api/files/{db_file.uuid}/video"
        else:
            # Audio files can use the download endpoint
            db_file.preview_url = f"/api/files/{db_file.uuid}/download"

        # Set thumbnail URL if thumbnail exists
        if db_file.thumbnail_path:
            db_file.thumbnail_url = f"/api/files/{db_file.uuid}/thumbnail"


def _get_or_compute_analytics(db: Session, file_id: int, file_status: str) -> Analytics | None:
    """
    Get analytics for a file, computing them on-demand if needed.

    Args:
        db: Database session
        file_id: File ID
        file_status: Current status of the file

    Returns:
        Analytics object or None
    """
    analytics = db.query(Analytics).filter(Analytics.media_file_id == file_id).first()

    if analytics or file_status != "completed":
        return analytics

    # Compute analytics on-demand for completed files
    from app.services.analytics_service import AnalyticsService

    logger.info(f"Computing missing analytics on-demand for file {file_id}")
    success = AnalyticsService.compute_and_save_analytics(db, file_id)
    if success:
        analytics = db.query(Analytics).filter(Analytics.media_file_id == file_id).first()

    return analytics


def _get_transcript_segments(
    db: Session, file_id: int, segment_limit: int | None, segment_offset: int
) -> tuple[list[TranscriptSegment], int]:
    """
    Get transcript segments with pagination and compute total count.

    Args:
        db: Database session
        file_id: File ID
        segment_limit: Maximum number of segments to return
        segment_offset: Offset for pagination

    Returns:
        Tuple of (list of transcript segments, total count)
    """
    from sqlalchemy import func
    from sqlalchemy.orm import joinedload

    total_segments = (
        db.query(func.count(TranscriptSegment.id))
        .filter(TranscriptSegment.media_file_id == file_id)
        .scalar()
    )

    segment_query = (
        db.query(TranscriptSegment)
        .options(joinedload(TranscriptSegment.speaker))
        .filter(TranscriptSegment.media_file_id == file_id)
        .order_by(TranscriptSegment.start_time)
    )

    if segment_offset > 0:
        segment_query = segment_query.offset(segment_offset)
    if segment_limit is not None:
        segment_query = segment_query.limit(segment_limit)

    return segment_query.all(), total_segments


def _add_error_info_to_response(response: MediaFileDetail, db_file: MediaFile) -> None:
    """
    Add error categorization information to response for failed files.

    Args:
        response: MediaFileDetail response to update
        db_file: MediaFile object
    """
    if db_file.status != FileStatus.ERROR or not hasattr(db_file, "last_error_message"):
        return

    from app.services.error_categorization_service import ErrorCategorizationService

    error_info = ErrorCategorizationService.get_error_info(db_file.last_error_message)
    response.error_category = error_info["category"]
    response.error_suggestions = error_info["suggestions"]
    response.is_retryable = error_info["is_retryable"]


def _format_transcript_segments(
    transcript_segments: list[TranscriptSegment], speakers: list[Speaker]
) -> list[dict]:
    """
    Format transcript segments with speaker labels and timestamps.

    Args:
        transcript_segments: List of transcript segments
        speakers: List of speakers for name mapping

    Returns:
        List of formatted segment dictionaries
    """
    speaker_mapping = {
        speaker.name: FormattingService.format_speaker_name(speaker) for speaker in speakers
    }

    return [
        FormattingService.format_transcript_segment(segment, speaker_mapping)
        for segment in transcript_segments
    ]


def _build_media_file_response(
    db_file: MediaFile,
    tags: list[str],
    collections: list[dict],
    speakers: list[Speaker],
    analytics: Analytics | None,
    transcript_segments: list[TranscriptSegment],
    total_segments: int,
    segment_limit: int | None,
    segment_offset: int,
) -> MediaFileDetail:
    """
    Build the MediaFileDetail response with all formatted fields.

    Args:
        db_file: MediaFile object
        tags: List of tag names
        collections: List of collection dictionaries
        speakers: List of speakers
        analytics: Analytics object or None
        transcript_segments: List of transcript segments
        total_segments: Total segment count for pagination
        segment_limit: Segment pagination limit
        segment_offset: Segment pagination offset

    Returns:
        MediaFileDetail response object
    """
    response = MediaFileDetail.model_validate(db_file)
    response.tags = tags
    response.collections = collections
    response.speakers = speakers

    # Convert analytics to schema if it exists
    if analytics:
        from app.schemas.media import Analytics as AnalyticsSchema

        response.analytics = AnalyticsSchema.model_validate(analytics)
    else:
        response.analytics = None

    # Add formatted fields
    response.formatted_duration = FormattingService.format_duration(db_file.duration)
    response.formatted_upload_date = FormattingService.format_upload_date(db_file.upload_time)
    response.formatted_file_age = FormattingService.format_file_age(db_file.upload_time)
    response.formatted_file_size = FormattingService.format_bytes_detailed(db_file.file_size)
    response.display_status = FormattingService.format_status(db_file.status)
    response.status_badge_class = FormattingService.get_status_badge_class(db_file.status.value)
    response.speaker_summary = FormattingService.create_speaker_summary(speakers)

    # Add error info if applicable
    _add_error_info_to_response(response, db_file)

    # Format and add transcript segments
    response.transcript_segments = _format_transcript_segments(transcript_segments, speakers)

    # Add pagination metadata
    response.total_segments = total_segments
    response.segment_limit = segment_limit
    response.segment_offset = segment_offset

    return response


def get_media_file_detail(
    db: Session,
    file_uuid: str,
    current_user: User,
    segment_limit: int = None,
    segment_offset: int = 0,
) -> MediaFileDetail:
    """
    Get detailed media file information including tags, analytics, and formatted fields.

    Args:
        db: Database session
        file_uuid: File UUID
        current_user: Current user
        segment_limit: Maximum number of transcript segments to return (None = all)
        segment_offset: Offset for transcript segment pagination (default 0)

    Returns:
        MediaFileDetail object with all computed and formatted data
    """
    try:
        # Get the file by uuid and user id (admin can access any file)
        is_admin = current_user.role == "admin"
        db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
        file_id = db_file.id

        # Get related data
        tags = get_file_tags(db, file_id)
        collections = get_file_collections(db, file_id, current_user.id)

        # Get speakers and add computed status
        speakers = db.query(Speaker).filter(Speaker.media_file_id == file_id).all()
        for speaker in speakers:
            SpeakerStatusService.add_computed_status(speaker)

        # Get analytics (compute on-demand if needed)
        analytics = _get_or_compute_analytics(db, file_id, db_file.status)

        # Get transcript segments with pagination
        transcript_segments, total_segments = _get_transcript_segments(
            db, file_id, segment_limit, segment_offset
        )

        # Add computed status to speakers in segments
        for segment in transcript_segments:
            if segment.speaker:
                SpeakerStatusService.add_computed_status(segment.speaker)

        # Set URLs
        set_file_urls(db_file)

        # Build the response
        response = _build_media_file_response(
            db_file=db_file,
            tags=tags,
            collections=collections,
            speakers=speakers,
            analytics=analytics,
            transcript_segments=transcript_segments,
            total_segments=total_segments,
            segment_limit=segment_limit,
            segment_offset=segment_offset,
        )

        db.commit()
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_media_file_detail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving media file: {str(e)}",
        ) from e


def update_media_file(
    db: Session, file_uuid: str, media_file_update: MediaFileUpdate, current_user: User
) -> MediaFile:
    """
    Update a media file's metadata.

    Args:
        db: Database session
        file_uuid: File UUID
        media_file_update: Update data
        current_user: Current user

    Returns:
        Updated MediaFile object
    """
    is_admin = current_user.role == "admin"
    db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
    file_id = db_file.id  # Get internal ID for OpenSearch update

    # Track if title was updated for OpenSearch reindexing
    update_data = media_file_update.model_dump(exclude_unset=True)
    title_updated = "title" in update_data and update_data["title"] != db_file.title

    # Update fields
    for field, value in update_data.items():
        setattr(db_file, field, value)

    db.commit()
    db.refresh(db_file)

    # Update OpenSearch index if title was changed
    if title_updated:
        try:
            new_title = db_file.title or db_file.filename
            update_transcript_title(db_file.uuid, new_title)  # Use UUID not integer ID
        except Exception as e:
            logger.warning(f"Failed to update OpenSearch title for file {file_id}: {e}")

    return db_file


def _cleanup_opensearch_data(db: Session, file_id: int, file_uuid: str) -> None:
    """Clean up OpenSearch data for a file being deleted."""
    try:
        # Get all speakers for this file before deletion
        speakers = db.query(Speaker).filter(Speaker.media_file_id == file_id).all()
        speaker_uuids = [str(speaker.uuid) for speaker in speakers]  # Use UUIDs for OpenSearch

        if speaker_uuids:
            # Delete speaker embeddings from OpenSearch
            from app.services.opensearch_service import opensearch_client
            from app.services.opensearch_service import settings

            if opensearch_client:
                deleted_count = 0
                for speaker_uuid in speaker_uuids:
                    try:
                        opensearch_client.delete(
                            index=settings.OPENSEARCH_SPEAKER_INDEX,
                            id=speaker_uuid,  # Use UUID
                        )
                        deleted_count += 1
                    except Exception as e:
                        logger.warning(
                            f"Error deleting speaker {speaker_uuid} from OpenSearch: {e}"
                        )

                logger.info(
                    f"Deleted {deleted_count}/{len(speaker_uuids)} speaker embeddings from OpenSearch for file {file_id}"
                )
            else:
                logger.warning("OpenSearch client not available for cleanup")

        # Delete transcript from OpenSearch (using file UUID as document ID)
        try:
            from app.services.opensearch_service import opensearch_client
            from app.services.opensearch_service import settings

            if opensearch_client:
                opensearch_client.delete(
                    index=settings.OPENSEARCH_TRANSCRIPT_INDEX,
                    id=str(file_uuid),  # Use UUID as document ID
                )
                logger.info(f"Deleted transcript for file {file_uuid} from OpenSearch")
        except Exception as e:
            logger.warning(f"Error deleting transcript from OpenSearch: {e}")

    except Exception as e:
        logger.warning(f"Error cleaning up OpenSearch data for file {file_id}: {e}")
        # Don't fail deletion if OpenSearch cleanup fails


def delete_media_file(db: Session, file_uuid: str, current_user: User, force: bool = False) -> None:
    """
    Delete a media file and all associated data with safety checks.

    Args:
        db: Database session
        file_uuid: File UUID
        current_user: Current user
        force: Force deletion even if processing is active (admin only)
    """
    from app.utils.task_utils import cancel_active_task
    from app.utils.task_utils import is_file_safe_to_delete

    is_admin = current_user.role == "admin"
    db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
    file_id = db_file.id  # Get internal ID for task operations

    # Check if file is safe to delete
    is_safe, reason = is_file_safe_to_delete(db, file_id)

    if not is_safe and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "FILE_NOT_SAFE_TO_DELETE",
                "message": f"Cannot delete file: {reason}",
                "file_id": str(db_file.uuid),  # Use UUID for frontend
                "active_task_id": db_file.active_task_id,
                "status": db_file.status,
                "options": {
                    "cancel_and_delete": is_admin,
                    "wait_for_completion": True,
                    "force_delete": is_admin and db_file.force_delete_eligible,
                },
            },
        )

    # If force deletion and file has active task, cancel it first
    if force and db_file.active_task_id:
        logger.info(
            f"Force deleting file {file_id}, cancelling active task {db_file.active_task_id}"
        )
        cancel_active_task(db, file_id)
        # Refresh the file object
        db.refresh(db_file)

    # Delete from MinIO (if exists)
    storage_deleted = False
    try:
        delete_file(db_file.storage_path)
        storage_deleted = True
        logger.info(f"Successfully deleted file from storage: {db_file.storage_path}")
    except Exception as e:
        logger.warning(f"Error deleting file from storage: {e}")
        # Don't fail the entire operation if storage deletion fails

    # Delete associated data from OpenSearch before deleting from database
    _cleanup_opensearch_data(db, file_id, str(db_file.uuid))

    try:
        # Delete from database (cascade will handle related records)
        db.delete(db_file)
        db.commit()
        logger.info(f"Successfully deleted file {file_id} from database")
    except Exception as e:
        logger.error(f"Failed to delete file {file_id} from database: {e}")
        db.rollback()

        # If we deleted from storage but DB deletion failed, that's a problem
        if storage_deleted:
            logger.error(f"File {file_id} deleted from storage but not from database - orphaned!")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file from database: {str(e)}",
        ) from e


def update_single_transcript_segment(
    db: Session,
    file_uuid: str,
    segment_uuid: str,
    segment_update: TranscriptSegmentUpdate,
    current_user: User,
) -> TranscriptSegment:
    """
    Update a single transcript segment for a media file.

    Args:
        db: Database session
        file_uuid: File UUID
        segment_uuid: Segment UUID
        segment_update: Segment update data
        current_user: Current user

    Returns:
        Updated TranscriptSegment object
    """
    # Verify user owns the file or is admin
    is_admin = current_user.role == "admin"
    db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)
    file_id = db_file.id  # Get internal ID for segment query

    # Find the specific segment by UUID
    segment = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.uuid == segment_uuid,
            TranscriptSegment.media_file_id == file_id,
        )
        .first()
    )

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transcript segment not found"
        )

    # Update fields
    for field, value in segment_update.model_dump(exclude_unset=True).items():
        setattr(segment, field, value)

    db.commit()
    db.refresh(segment)

    return segment


def get_stream_url_info(db: Session, file_uuid: str, current_user: User) -> dict:
    """
    Get streaming URL information for a media file.

    Args:
        db: Database session
        file_uuid: File UUID
        current_user: Current user

    Returns:
        Dictionary with URL and content type information
    """
    is_admin = current_user.role == "admin"
    db_file = get_media_file_by_uuid(db, file_uuid, current_user.id, is_admin=is_admin)

    # Skip S3 operations in test environment
    if os.environ.get("SKIP_S3", "False").lower() == "true":
        logger.info("Returning mock URL in test environment")
        return {
            "url": f"/api/files/{db_file.uuid}/content",
            "content_type": db_file.content_type,
        }

    # Return the URL to our video endpoint
    return {
        "url": f"/api/files/{db_file.uuid}/video",  # Video endpoint
        "content_type": db_file.content_type,
        "requires_auth": False,  # No auth required for video endpoint
    }
