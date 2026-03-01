from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.orm import defer
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import selectinload

from app.api.endpoints.auth import get_current_user
from app.api.endpoints.files.crud import set_file_urls
from app.api.endpoints.files.filtering import apply_all_filters
from app.db.base import get_db
from app.models.media import Collection
from app.models.media import CollectionMember
from app.models.media import MediaFile
from app.models.media import Speaker
from app.models.prompt import SummaryPrompt
from app.models.user import User
from app.schemas.media import Collection as CollectionSchema
from app.schemas.media import CollectionCreate
from app.schemas.media import CollectionMemberAdd
from app.schemas.media import CollectionMemberRemove
from app.schemas.media import CollectionResponse
from app.schemas.media import CollectionUpdate
from app.schemas.media import CollectionWithCount
from app.schemas.media import PaginatedMediaFileResponse
from app.services.formatting_service import FormattingService
from app.utils.uuid_helpers import get_collection_by_uuid_with_permission
from app.utils.uuid_helpers import validate_uuids

router = APIRouter()


def _resolve_prompt_uuid(db: Session, prompt_uuid: str | None, user_id: int) -> int | None:
    """Resolve a prompt UUID to its internal ID, validating access."""
    if prompt_uuid is None:
        return None

    prompt = (
        db.query(SummaryPrompt)
        .filter(
            SummaryPrompt.uuid == prompt_uuid,
            SummaryPrompt.is_active,
            or_(SummaryPrompt.is_system_default, SummaryPrompt.user_id == user_id),
        )
        .first()
    )

    if not prompt:
        raise HTTPException(
            status_code=404,
            detail="Summary prompt not found or not accessible",
        )

    return int(prompt.id)


def _get_prompt_info(collection: Collection) -> tuple:
    """Get prompt UUID and name from a collection's default_summary_prompt relationship."""
    prompt = collection.default_summary_prompt
    if prompt:
        return (prompt.uuid, prompt.name)
    return (None, None)


@router.get("", response_model=list[CollectionWithCount])
async def list_collections(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all collections for the current user with media count"""
    # First get collection IDs and counts
    counts_query = (
        db.query(Collection.id, func.count(CollectionMember.id).label("media_count"))
        .filter(Collection.user_id == current_user.id)
        .outerjoin(CollectionMember)
        .group_by(Collection.id)
        .offset(skip)
        .limit(limit)
    ).all()

    # Extract collection IDs
    collection_ids = [c[0] for c in counts_query]
    counts_dict = {c[0]: c[1] or 0 for c in counts_query}

    # Then fetch full collection objects with user and prompt relationships
    collections_objs = (
        db.query(Collection)
        .options(
            joinedload(Collection.user),
            joinedload(Collection.default_summary_prompt),
        )
        .filter(Collection.id.in_(collection_ids))
        .all()
    )

    collections = []
    for collection in collections_objs:
        # Use model_validate with the collection object
        collection_with_count = CollectionWithCount.model_validate(collection)
        # Set the media_count from our counts dict
        collection_with_count.media_count = counts_dict.get(collection.id, 0)
        # Set prompt info
        prompt_uuid, prompt_name = _get_prompt_info(collection)
        collection_with_count.default_prompt_id = prompt_uuid
        collection_with_count.default_prompt_name = prompt_name
        collections.append(collection_with_count)

    return collections


@router.post("", response_model=CollectionSchema)
async def create_collection(
    collection: CollectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new collection"""
    # Check if collection with same name exists for user
    existing = (
        db.query(Collection)
        .filter(Collection.user_id == current_user.id, Collection.name == collection.name)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Collection with name '{collection.name}' already exists",
        )

    # Resolve prompt UUID to internal ID if provided
    create_data = collection.dict(exclude={"default_prompt_id"})
    prompt_internal_id = None
    if collection.default_prompt_id:
        prompt_internal_id = _resolve_prompt_uuid(
            db, str(collection.default_prompt_id), int(current_user.id)
        )

    db_collection = Collection(
        **create_data,
        user_id=current_user.id,
        default_summary_prompt_id=prompt_internal_id,
    )
    db.add(db_collection)
    db.commit()
    db.refresh(db_collection)

    # Eagerly load prompt relationship for response
    if db_collection.default_summary_prompt_id:
        db.refresh(db_collection, ["default_summary_prompt"])

    result = CollectionSchema.model_validate(db_collection)
    prompt_uuid, prompt_name = _get_prompt_info(db_collection)
    result.default_prompt_id = prompt_uuid
    result.default_prompt_name = prompt_name
    return result


@router.get("/{collection_uuid}", response_model=CollectionResponse)
async def get_collection(
    collection_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific collection with its media files"""
    collection = get_collection_by_uuid_with_permission(db, collection_uuid, int(current_user.id))

    # Reload with joined data
    reloaded_collection = (
        db.query(Collection)
        .filter(Collection.id == collection.id)
        .options(
            joinedload(Collection.collection_members).joinedload(CollectionMember.media_file),
            joinedload(Collection.default_summary_prompt),
        )
        .first()
    )

    if reloaded_collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    collection = reloaded_collection

    # Extract media files from collection members
    media_files = [member.media_file for member in collection.collection_members]

    # Build response with prompt info
    result = CollectionResponse.model_validate(collection)
    result.media_files = media_files
    prompt_uuid, prompt_name = _get_prompt_info(collection)
    result.default_prompt_id = prompt_uuid
    result.default_prompt_name = prompt_name

    return result


@router.put("/{collection_uuid}", response_model=CollectionSchema)
async def update_collection(
    collection_uuid: str,
    collection_update: CollectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a collection"""
    collection = get_collection_by_uuid_with_permission(db, collection_uuid, int(current_user.id))
    collection_id = collection.id

    # Check if new name conflicts with existing collection
    if collection_update.name and collection_update.name != collection.name:
        existing = (
            db.query(Collection)
            .filter(
                Collection.user_id == current_user.id,
                Collection.name == collection_update.name,
                Collection.id != collection_id,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Collection with name '{collection_update.name}' already exists",
            )

    # Update fields
    update_data = collection_update.dict(exclude_unset=True)

    # Handle prompt UUID resolution separately
    if "default_prompt_id" in update_data:
        prompt_uuid = update_data.pop("default_prompt_id")
        if prompt_uuid is None:
            # Explicitly clearing the prompt
            collection.default_summary_prompt_id = None  # type: ignore[assignment]
        else:
            prompt_internal_id = _resolve_prompt_uuid(db, str(prompt_uuid), int(current_user.id))
            collection.default_summary_prompt_id = prompt_internal_id  # type: ignore[assignment]

    for field, value in update_data.items():
        setattr(collection, field, value)

    db.commit()
    db.refresh(collection)

    # Eagerly load prompt relationship for response
    if collection.default_summary_prompt_id:
        db.refresh(collection, ["default_summary_prompt"])

    result = CollectionSchema.model_validate(collection)
    prompt_uuid_val, prompt_name = _get_prompt_info(collection)
    result.default_prompt_id = prompt_uuid_val
    result.default_prompt_name = prompt_name
    return result


@router.delete("/{collection_uuid}")
async def delete_collection(
    collection_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a collection"""
    collection = get_collection_by_uuid_with_permission(db, collection_uuid, int(current_user.id))

    db.delete(collection)
    db.commit()

    return {"message": "Collection deleted successfully"}


@router.post("/{collection_uuid}/media", response_model=dict)
async def add_media_to_collection(
    collection_uuid: str,
    media_data: CollectionMemberAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add media files to a collection"""
    # Verify collection exists and belongs to user
    collection = get_collection_by_uuid_with_permission(db, collection_uuid, int(current_user.id))
    collection_id = collection.id

    # Bulk resolve UUIDs to IDs in a single query (avoids N+1)
    media_file_uuids = validate_uuids([str(uuid) for uuid in media_data.media_file_ids])

    media_files = (
        db.query(MediaFile)
        .filter(
            MediaFile.uuid.in_(media_file_uuids),
            MediaFile.user_id == current_user.id,
        )
        .all()
    )

    if len(media_files) != len(media_file_uuids):
        # Determine which UUIDs are missing or unauthorized
        found_uuids = {str(f.uuid) for f in media_files}
        missing = [u for u in media_file_uuids if u not in found_uuids]
        raise HTTPException(
            status_code=404,
            detail=f"Media files not found or not authorized: {missing}",
        )

    media_file_ids = [f.id for f in media_files]

    # Get existing members to avoid duplicates
    existing_members = (
        db.query(CollectionMember.media_file_id)
        .filter(
            CollectionMember.collection_id == collection_id,
            CollectionMember.media_file_id.in_(media_file_ids),
        )
        .all()
    )

    existing_ids = {member[0] for member in existing_members}
    new_ids = set(media_file_ids) - existing_ids

    # Add new members
    added_count = 0
    for media_file_id in new_ids:
        member = CollectionMember(collection_id=collection_id, media_file_id=media_file_id)
        db.add(member)
        added_count += 1

    db.commit()

    return {
        "message": f"Added {added_count} media files to collection",
        "added": added_count,
        "already_existed": len(existing_ids),
    }


@router.delete("/{collection_uuid}/media", response_model=dict)
async def remove_media_from_collection(
    collection_uuid: str,
    media_data: CollectionMemberRemove,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove media files from a collection"""
    # Verify collection exists and belongs to user
    collection = get_collection_by_uuid_with_permission(db, collection_uuid, int(current_user.id))
    collection_id = collection.id

    # Bulk resolve UUIDs to IDs in a single query (avoids N+1)
    media_file_uuids = validate_uuids([str(uuid) for uuid in media_data.media_file_ids])

    media_files = db.query(MediaFile).filter(MediaFile.uuid.in_(media_file_uuids)).all()
    media_file_ids = [f.id for f in media_files]

    # Remove members
    removed_count = (
        db.query(CollectionMember)
        .filter(
            CollectionMember.collection_id == collection_id,
            CollectionMember.media_file_id.in_(media_file_ids),
        )
        .delete(synchronize_session=False)
    )

    db.commit()

    return {
        "message": f"Removed {removed_count} media files from collection",
        "removed": removed_count,
    }


@router.get("/{collection_uuid}/media", response_model=PaginatedMediaFileResponse)
async def get_collection_media(
    collection_uuid: str,
    # Pagination parameters
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    # Filters
    search: Optional[str] = None,
    tag: Optional[list[str]] = Query(None),
    speaker: Optional[list[str]] = Query(None),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    min_duration: Optional[float] = None,
    max_duration: Optional[float] = None,
    min_file_size: Optional[int] = None,
    max_file_size: Optional[int] = None,
    file_type: Optional[list[str]] = Query(None),
    status: Optional[list[str]] = Query(None),
    transcript_search: Optional[str] = None,
    # Sort parameters
    sort_by: str = Query(
        "upload_time",
        description="Field to sort by: upload_time, completed_at, filename, duration, file_size",
    ),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    # Dependencies
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get media files in a collection with filtering, sorting, and pagination."""
    # Verify collection exists and belongs to user
    collection = get_collection_by_uuid_with_permission(db, collection_uuid, int(current_user.id))
    collection_id = collection.id

    # Eager-loading strategy matching the main list endpoint
    list_options = [
        joinedload(MediaFile.user),
        selectinload(MediaFile.speakers).load_only(
            Speaker.uuid,  # type: ignore[arg-type]
            Speaker.name,  # type: ignore[arg-type]
            Speaker.display_name,  # type: ignore[arg-type]
        ),
        defer(MediaFile.metadata_raw),  # type: ignore[arg-type]
        defer(MediaFile.waveform_data),  # type: ignore[arg-type]
    ]

    # Build base query scoped to this collection
    base_query = (
        db.query(MediaFile)
        .options(*list_options)
        .join(CollectionMember, CollectionMember.media_file_id == MediaFile.id)
        .filter(CollectionMember.collection_id == collection_id)
    )

    # Non-admin users can only see their own files
    if current_user.role != "admin":
        base_query = base_query.filter(MediaFile.user_id == current_user.id)

    # Prepare filters dictionary
    filters = {
        "search": search,
        "tag": tag,
        "speaker": speaker,
        "from_date": from_date,
        "to_date": to_date,
        "min_duration": min_duration,
        "max_duration": max_duration,
        "min_file_size": min_file_size,
        "max_file_size": max_file_size,
        "file_type": file_type,
        "status": status,
        "transcript_search": transcript_search,
        "user_id": int(current_user.id) if current_user.role != "admin" else None,
    }

    # Apply all filters
    filtered_query = apply_all_filters(base_query, filters)

    # Sorting field mapping
    sort_field_mapping = {
        "upload_time": MediaFile.upload_time,
        "completed_at": MediaFile.completed_at,
        "filename": MediaFile.filename,
        "duration": MediaFile.duration,
        "file_size": MediaFile.file_size,
    }
    sort_field = sort_field_mapping.get(sort_by, MediaFile.upload_time)

    # Get total count before sorting/pagination
    total_count = (filtered_query.with_entities(func.count(MediaFile.id)).scalar()) or 0

    # Apply sort order
    if sort_order.lower() == "asc":
        filtered_query = filtered_query.order_by(sort_field.asc())  # type: ignore[attr-defined]
    else:
        filtered_query = filtered_query.order_by(sort_field.desc())  # type: ignore[attr-defined]

    # Apply pagination
    offset = (page - 1) * page_size
    result = filtered_query.offset(offset).limit(page_size).all()

    # Format each file with URLs and formatted fields
    formatted_files = []
    for file in result:
        set_file_urls(file)
        formatted_file = FormattingService.format_media_file(file, file.speakers)
        formatted_files.append(formatted_file)

    # Calculate pagination metadata
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
    has_more = page < total_pages

    return PaginatedMediaFileResponse(
        items=formatted_files,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_more=has_more,
    )
