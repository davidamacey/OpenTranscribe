from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from app.api.endpoints.auth import get_current_user
from app.api.endpoints.files.crud import set_file_urls
from app.db.base import get_db
from app.models.media import Collection
from app.models.media import CollectionMember
from app.models.media import MediaFile
from app.models.user import User
from app.schemas.media import Collection as CollectionSchema
from app.schemas.media import CollectionCreate
from app.schemas.media import CollectionMemberAdd
from app.schemas.media import CollectionMemberRemove
from app.schemas.media import CollectionResponse
from app.schemas.media import CollectionUpdate
from app.schemas.media import CollectionWithCount
from app.schemas.media import MediaFile as MediaFileSchema
from app.utils.uuid_helpers import get_collection_by_uuid_with_permission
from app.utils.uuid_helpers import get_file_by_uuid
from app.utils.uuid_helpers import validate_uuids

router = APIRouter()


@router.get("/", response_model=list[CollectionWithCount])
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

    # Then fetch full collection objects with user relationship
    collections_objs = (
        db.query(Collection)
        .options(joinedload(Collection.user))
        .filter(Collection.id.in_(collection_ids))
        .all()
    )

    collections = []
    for collection in collections_objs:
        # Use model_validate with the collection object
        collection_with_count = CollectionWithCount.model_validate(collection)
        # Set the media_count from our counts dict
        collection_with_count.media_count = counts_dict.get(collection.id, 0)
        collections.append(collection_with_count)

    return collections


@router.post("/", response_model=CollectionSchema)
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

    db_collection = Collection(**collection.dict(), user_id=current_user.id)
    db.add(db_collection)
    db.commit()
    db.refresh(db_collection)

    return db_collection


@router.get("/{collection_uuid}", response_model=CollectionResponse)
async def get_collection(
    collection_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific collection with its media files"""
    collection = get_collection_by_uuid_with_permission(db, collection_uuid, current_user.id)

    # Reload with joined data
    collection = (
        db.query(Collection)
        .filter(Collection.id == collection.id)
        .options(joinedload(Collection.collection_members).joinedload(CollectionMember.media_file))
        .first()
    )

    # Extract media files from collection members
    media_files = [member.media_file for member in collection.collection_members]

    # Create response with media files
    collection_dict = collection.__dict__.copy()
    collection_dict["media_files"] = media_files

    return CollectionResponse(**collection_dict)


@router.put("/{collection_uuid}", response_model=CollectionSchema)
async def update_collection(
    collection_uuid: str,
    collection_update: CollectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a collection"""
    collection = get_collection_by_uuid_with_permission(db, collection_uuid, current_user.id)
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
    for field, value in update_data.items():
        setattr(collection, field, value)

    db.commit()
    db.refresh(collection)

    return collection


@router.delete("/{collection_uuid}")
async def delete_collection(
    collection_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a collection"""
    collection = get_collection_by_uuid_with_permission(db, collection_uuid, current_user.id)

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
    collection = get_collection_by_uuid_with_permission(db, collection_uuid, current_user.id)
    collection_id = collection.id

    # Convert UUIDs to IDs for media files
    media_file_uuids = validate_uuids(media_data.media_file_ids)
    media_file_ids = []
    for file_uuid in media_file_uuids:
        file = get_file_by_uuid(db, file_uuid)
        if file.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail=f"Not authorized to access file {file_uuid}",
            )
        media_file_ids.append(file.id)

    # Verify all media files exist and belong to user (already done above, but keep query for consistency)
    media_files = (
        db.query(MediaFile)
        .filter(
            MediaFile.id.in_(media_file_ids),
            MediaFile.user_id == current_user.id,
        )
        .all()
    )

    if len(media_files) != len(media_file_ids):
        raise HTTPException(
            status_code=404,
            detail="One or more media files not found or don't belong to you",
        )

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
    collection = get_collection_by_uuid_with_permission(db, collection_uuid, current_user.id)
    collection_id = collection.id

    # Convert UUIDs to IDs for media files
    media_file_uuids = validate_uuids(media_data.media_file_ids)
    media_file_ids = []
    for file_uuid in media_file_uuids:
        file = get_file_by_uuid(db, file_uuid)
        media_file_ids.append(file.id)

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


@router.get("/{collection_uuid}/media", response_model=list[MediaFileSchema])
async def get_collection_media(
    collection_uuid: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get media files in a collection"""
    # Verify collection exists and belongs to user
    collection = get_collection_by_uuid_with_permission(db, collection_uuid, current_user.id)
    collection_id = collection.id

    # Get media files
    media_files = (
        db.query(MediaFile)
        .join(CollectionMember)
        .filter(CollectionMember.collection_id == collection_id)
        .order_by(CollectionMember.added_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Set file URLs for each media file (including thumbnail URLs)
    for media_file in media_files:
        set_file_urls(media_file)

    return media_files
