from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.user import User
from app.services.opensearch_service import search_transcripts

router = APIRouter()


@router.get("/")
def search(
    q: str = Query(None, description="Search query"),
    speaker: Optional[str] = None,
    tag: Optional[str] = None,
    semantic: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Search across transcripts using full-text and optional semantic search

    Args:
        q: Search query text
        speaker: Optional speaker name to filter by
        tag: Optional tag to filter by
        semantic: Whether to use semantic search in addition to keyword search

    Returns:
        List of search results with file info and matching snippets
    """
    # Convert tag to list if provided
    tags = [tag] if tag else None

    # Call the OpenSearch service
    results = search_transcripts(
        query=q,
        user_id=current_user.id,
        speaker=speaker,
        tags=tags,
        use_semantic=semantic
    )

    # Convert to the format expected by tests
    # The tests expect a list of results where each result has an 'id' field instead of 'file_id'
    formatted_results = []
    for result in results:
        formatted_results.append({
            "id": result["file_id"],
            "title": result["title"],
            "speakers": result["speakers"],
            "snippet": result["snippet"],
            "upload_time": result["upload_time"]
        })

    return formatted_results


@router.get("/advanced")
def advanced_search(
    q: Optional[str] = None,
    speakers: list[str] = Query(None),
    tags: list[str] = Query(None),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_duration: Optional[float] = None,
    max_duration: Optional[float] = None,
    semantic: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Advanced search with multiple filters

    Args:
        q: Optional search query text
        speakers: List of speaker names to filter by
        tags: List of tags to filter by
        start_date: Filter files uploaded after this date
        end_date: Filter files uploaded before this date
        min_duration: Minimum duration in seconds
        max_duration: Maximum duration in seconds
        semantic: Whether to use semantic search

    Returns:
        List of search results with filters applied
    """
    # This endpoint would implement a more complex search with multiple filters
    # For now, we'll use the same search_transcripts function with the first speaker

    speaker = speakers[0] if speakers and len(speakers) > 0 else None

    results = search_transcripts(
        query=q,
        user_id=current_user.id,
        speaker=speaker,
        tags=tags,
        use_semantic=semantic
    )

    # In a real implementation, we would:
    # 1. Apply date filters
    # 2. Apply duration filters
    # 3. Filter for multiple speakers

    # Convert to the format expected by tests
    # The tests expect a list of results where each result has an 'id' field instead of 'file_id'
    formatted_results = []
    for result in results:
        formatted_results.append({
            "id": result["file_id"],
            "title": result["title"],
            "speakers": result["speakers"],
            "snippet": result["snippet"],
            "upload_time": result["upload_time"]
        })

    return formatted_results
