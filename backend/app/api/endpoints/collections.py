
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

router = APIRouter()


@router.get("/", response_model=list[CollectionWithCount])
async def list_collections(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all collections for the current user with media count"""
    collections_query = (
        db.query(Collection, func.count(CollectionMember.id).label("media_count"))
        .filter(Collection.user_id == current_user.id)
        .outerjoin(CollectionMember)
        .group_by(Collection.id)
        .offset(skip)
        .limit(limit)
    )

    collections = []
    for collection, media_count in collections_query:
        collection_dict = collection.__dict__.copy()
        collection_dict["media_count"] = media_count or 0
        collections.append(CollectionWithCount(**collection_dict))

    return collections


@router.post("/", response_model=CollectionSchema)
async def create_collection(
    collection: CollectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new collection"""
    # Check if collection with same name exists for user
    existing = db.query(Collection).filter(
        Collection.user_id == current_user.id,
        Collection.name == collection.name
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Collection with name '{collection.name}' already exists"
        )

    db_collection = Collection(
        **collection.dict(),
        user_id=current_user.id
    )
    db.add(db_collection)
    db.commit()
    db.refresh(db_collection)

    return db_collection


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific collection with its media files"""
    collection = (
        db.query(Collection)
        .filter(
            Collection.id == collection_id,
            Collection.user_id == current_user.id
        )
        .options(
            joinedload(Collection.collection_members)
            .joinedload(CollectionMember.media_file)
        )
        .first()
    )

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Extract media files from collection members
    media_files = [
        member.media_file for member in collection.collection_members
    ]

    # Create response with media files
    collection_dict = collection.__dict__.copy()
    collection_dict["media_files"] = media_files

    return CollectionResponse(**collection_dict)


@router.put("/{collection_id}", response_model=CollectionSchema)
async def update_collection(
    collection_id: int,
    collection_update: CollectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a collection"""
    collection = db.query(Collection).filter(
        Collection.id == collection_id,
        Collection.user_id == current_user.id
    ).first()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Check if new name conflicts with existing collection
    if collection_update.name and collection_update.name != collection.name:
        existing = db.query(Collection).filter(
            Collection.user_id == current_user.id,
            Collection.name == collection_update.name,
            Collection.id != collection_id
        ).first()

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Collection with name '{collection_update.name}' already exists"
            )

    # Update fields
    update_data = collection_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(collection, field, value)

    db.commit()
    db.refresh(collection)

    return collection


@router.delete("/{collection_id}")
async def delete_collection(
    collection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a collection"""
    collection = db.query(Collection).filter(
        Collection.id == collection_id,
        Collection.user_id == current_user.id
    ).first()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    db.delete(collection)
    db.commit()

    return {"message": "Collection deleted successfully"}


@router.post("/{collection_id}/media", response_model=dict)
async def add_media_to_collection(
    collection_id: int,
    media_data: CollectionMemberAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add media files to a collection"""
    # Verify collection exists and belongs to user
    collection = db.query(Collection).filter(
        Collection.id == collection_id,
        Collection.user_id == current_user.id
    ).first()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Verify all media files exist and belong to user
    media_files = db.query(MediaFile).filter(
        MediaFile.id.in_(media_data.media_file_ids),
        MediaFile.user_id == current_user.id
    ).all()

    if len(media_files) != len(media_data.media_file_ids):
        raise HTTPException(
            status_code=404,
            detail="One or more media files not found or don't belong to you"
        )

    # Get existing members to avoid duplicates
    existing_members = db.query(CollectionMember.media_file_id).filter(
        CollectionMember.collection_id == collection_id,
        CollectionMember.media_file_id.in_(media_data.media_file_ids)
    ).all()

    existing_ids = {member[0] for member in existing_members}
    new_ids = set(media_data.media_file_ids) - existing_ids

    # Add new members
    added_count = 0
    for media_file_id in new_ids:
        member = CollectionMember(
            collection_id=collection_id,
            media_file_id=media_file_id
        )
        db.add(member)
        added_count += 1

    db.commit()

    return {
        "message": f"Added {added_count} media files to collection",
        "added": added_count,
        "already_existed": len(existing_ids)
    }


@router.delete("/{collection_id}/media", response_model=dict)
async def remove_media_from_collection(
    collection_id: int,
    media_data: CollectionMemberRemove,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove media files from a collection"""
    # Verify collection exists and belongs to user
    collection = db.query(Collection).filter(
        Collection.id == collection_id,
        Collection.user_id == current_user.id
    ).first()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Remove members
    removed_count = db.query(CollectionMember).filter(
        CollectionMember.collection_id == collection_id,
        CollectionMember.media_file_id.in_(media_data.media_file_ids)
    ).delete(synchronize_session=False)

    db.commit()

    return {
        "message": f"Removed {removed_count} media files from collection",
        "removed": removed_count
    }


@router.get("/{collection_id}/media", response_model=list[MediaFileSchema])
async def get_collection_media(
    collection_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get media files in a collection"""
    # Verify collection exists and belongs to user
    collection = db.query(Collection).filter(
        Collection.id == collection_id,
        Collection.user_id == current_user.id
    ).first()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

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
