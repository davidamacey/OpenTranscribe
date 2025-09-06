from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Float
from sqlalchemy import Integer
from sqlalchemy import cast
from sqlalchemy import func
from sqlalchemy.orm import Query
from sqlalchemy.orm import Session

from app.models.media import FileTag
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.media import Tag
from app.models.media import TranscriptSegment


def apply_search_filter(query: Query, search: Optional[str]) -> Query:
    """
    Apply search filter for filename and title.

    Args:
        query: Base query
        search: Search term

    Returns:
        Filtered query
    """
    if search:
        query = query.filter(
            sa.or_(
                MediaFile.filename.ilike(f"%{search}%"),
                MediaFile.title.ilike(f"%{search}%") if MediaFile.title else False
            )
        )
    return query


def apply_tag_filter(query: Query, tag: Optional[list[str]]) -> Query:
    """
    Apply tag filter - supports multiple tags.

    Args:
        query: Base query
        tag: List of tag names

    Returns:
        Filtered query
    """
    if tag:
        for t in tag:
            query = query.join(FileTag, FileTag.media_file_id == MediaFile.id)\
                        .join(Tag, Tag.id == FileTag.tag_id)\
                        .filter(Tag.name == t)
    return query


def apply_speaker_filter(query: Query, speaker: Optional[list[str]]) -> Query:
    """
    Apply speaker filter using display name or original name.

    Args:
        query: Base query
        speaker: List of speaker names

    Returns:
        Filtered query
    """
    if speaker and len(speaker) > 0:
        speaker_or_conditions = []
        for s in speaker:
            speaker_or_conditions.append(
                sa.or_(Speaker.display_name == s, Speaker.name == s)
            )

        if speaker_or_conditions:
            query = query.join(TranscriptSegment, TranscriptSegment.media_file_id == MediaFile.id)\
                         .join(Speaker, Speaker.id == TranscriptSegment.speaker_id)\
                         .filter(sa.or_(*speaker_or_conditions)).distinct()
    return query


def apply_date_filters(query: Query, from_date: Optional[datetime],
                      to_date: Optional[datetime]) -> Query:
    """
    Apply date range filters.

    Args:
        query: Base query
        from_date: Start date
        to_date: End date

    Returns:
        Filtered query
    """
    if from_date:
        query = query.filter(MediaFile.upload_time >= from_date)

    if to_date:
        query = query.filter(MediaFile.upload_time <= to_date)

    return query


def apply_duration_filters(query: Query, min_duration: Optional[float],
                          max_duration: Optional[float]) -> Query:
    """
    Apply duration range filters.

    Args:
        query: Base query
        min_duration: Minimum duration in seconds
        max_duration: Maximum duration in seconds

    Returns:
        Filtered query
    """
    if min_duration is not None:
        query = query.filter(cast(MediaFile.duration, Float) >= min_duration)

    if max_duration is not None:
        query = query.filter(cast(MediaFile.duration, Float) <= max_duration)

    return query


def apply_file_size_filters(query: Query, min_file_size: Optional[int],
                           max_file_size: Optional[int]) -> Query:
    """
    Apply file size range filters (MB to bytes conversion).

    Args:
        query: Base query
        min_file_size: Minimum file size in MB
        max_file_size: Maximum file size in MB

    Returns:
        Filtered query
    """
    if min_file_size is not None:
        query = query.filter(MediaFile.file_size >= min_file_size * 1024 * 1024)

    if max_file_size is not None:
        query = query.filter(MediaFile.file_size <= max_file_size * 1024 * 1024)

    return query


def apply_file_type_filter(query: Query, file_type: Optional[list[str]]) -> Query:
    """
    Apply file type filter (audio/video).

    Args:
        query: Base query
        file_type: List of file types ('audio', 'video')

    Returns:
        Filtered query
    """
    if file_type:
        type_conditions = []
        for ft in file_type:
            if ft == 'audio':
                type_conditions.append(MediaFile.content_type.like('audio/%'))
            elif ft == 'video':
                type_conditions.append(MediaFile.content_type.like('video/%'))
        if type_conditions:
            query = query.filter(sa.or_(*type_conditions))

    return query


def apply_status_filter(query: Query, status: Optional[list[str]]) -> Query:
    """
    Apply status filter.

    Args:
        query: Base query
        status: List of status values

    Returns:
        Filtered query
    """
    if status:
        status_conditions = []
        for s in status:
            status_conditions.append(MediaFile.status == s)
        if status_conditions:
            query = query.filter(sa.or_(*status_conditions))

    return query


def apply_transcript_search_filter(query: Query, transcript_search: Optional[str]) -> Query:
    """
    Apply transcript content search filter.

    Args:
        query: Base query
        transcript_search: Search term for transcript content

    Returns:
        Filtered query
    """
    if transcript_search:
        query = query.join(TranscriptSegment, TranscriptSegment.media_file_id == MediaFile.id)\
                     .filter(TranscriptSegment.text.ilike(f"%{transcript_search}%"))\
                     .distinct()

    return query


def apply_all_filters(query: Query, filters: dict) -> Query:
    """
    Apply all filters to the query.

    Args:
        query: Base query
        filters: Dictionary of filter parameters

    Returns:
        Filtered query
    """
    query = apply_search_filter(query, filters.get('search'))
    query = apply_tag_filter(query, filters.get('tag'))
    query = apply_speaker_filter(query, filters.get('speaker'))
    query = apply_date_filters(query, filters.get('from_date'), filters.get('to_date'))
    query = apply_duration_filters(query, filters.get('min_duration'), filters.get('max_duration'))
    query = apply_file_size_filters(query, filters.get('min_file_size'), filters.get('max_file_size'))
    query = apply_file_type_filter(query, filters.get('file_type'))
    query = apply_status_filter(query, filters.get('status'))
    query = apply_transcript_search_filter(query, filters.get('transcript_search'))

    return query


def get_metadata_filters(db: Session, user_id: int) -> dict:
    """
    Get available metadata filters for the user's files.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        Dictionary of available filter options
    """
    # Query for unique formats
    formats_query = db.query(MediaFile.metadata_important['format'].astext.distinct())\
                    .filter(MediaFile.user_id == user_id)\
                    .filter(MediaFile.metadata_important['format'].astext != 'null')
    formats = [fmt[0] for fmt in formats_query.all() if fmt[0]]

    # Query for unique codecs
    codecs_query = db.query(MediaFile.metadata_important['codec'].astext.distinct())\
                   .filter(MediaFile.user_id == user_id)\
                   .filter(MediaFile.metadata_important['codec'].astext != 'null')
    codecs = [codec[0] for codec in codecs_query.all() if codec[0]]

    # Get min/max duration
    duration_range = db.query(
        func.min(cast(MediaFile.duration, Float)),
        func.max(cast(MediaFile.duration, Float))
    ).filter(MediaFile.user_id == user_id).first()

    min_duration = duration_range[0] if duration_range[0] is not None else 0
    max_duration = duration_range[1] if duration_range[1] is not None else 0

    # Get resolution ranges
    width_range = db.query(
        func.min(cast(MediaFile.metadata_important['width'].astext, Integer)),
        func.max(cast(MediaFile.metadata_important['width'].astext, Integer))
    ).filter(MediaFile.user_id == user_id).first()

    height_range = db.query(
        func.min(cast(MediaFile.metadata_important['height'].astext, Integer)),
        func.max(cast(MediaFile.metadata_important['height'].astext, Integer))
    ).filter(MediaFile.user_id == user_id).first()

    min_width = width_range[0] if width_range[0] is not None else 0
    max_width = width_range[1] if width_range[1] is not None else 0
    min_height = height_range[0] if height_range[0] is not None else 0
    max_height = height_range[1] if height_range[1] is not None else 0

    return {
        "formats": formats,
        "codecs": codecs,
        "duration": {
            "min": min_duration,
            "max": max_duration
        },
        "resolution": {
            "width": {
                "min": min_width,
                "max": max_width
            },
            "height": {
                "min": min_height,
                "max": max_height
            }
        }
    }
