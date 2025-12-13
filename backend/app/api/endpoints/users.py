import logging

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.api.endpoints.auth import get_current_admin_user
from app.core.security import get_password_hash
from app.db.base import get_db
from app.models.user import User
from app.schemas.user import User as UserSchema
from app.schemas.user import UserCreate
from app.schemas.user import UserUpdate
from app.utils.uuid_helpers import get_user_by_uuid

logger = logging.getLogger(__name__)

router = APIRouter()


def create_user(user_data: UserCreate, db: Session) -> User:
    """
    Create a new user

    This function is called from both the registration endpoint
    and the admin user creation endpoint
    """
    # Check if email already exists
    db_user = db.query(User).filter(User.email == user_data.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Create new user
    new_user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        is_active=True,
        is_superuser=False,  # Default to non-superuser
        role="user",  # Default role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.get("/", response_model=list[UserSchema])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    """
    List all users (admin only)
    """
    users = db.query(User).all()
    return users


@router.get("/me", response_model=UserSchema)
def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """
    Get current user info
    """
    return current_user


@router.put("/me", response_model=UserSchema)
def update_current_user(
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Update current user info
    """
    # Check if email is being changed and is already taken
    if user_update.email and user_update.email != current_user.email:
        existing_user = db.query(User).filter(User.email == user_update.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # This functionality was referring to a username field that doesn't exist in the model
    # Removed to align with the actual User model fields

    # Update fields
    update_data = user_update.model_dump(exclude_unset=True)

    # Hash password if it's provided
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)

    return current_user


@router.get("/{user_uuid}", response_model=UserSchema)
def get_user(
    user_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Get user by UUID (admin only)
    """
    # Uses helper that validates UUID format and returns 400 for invalid UUIDs
    return get_user_by_uuid(db, user_uuid)


@router.put("/{user_uuid}", response_model=UserSchema)
def update_user(
    user_uuid: str,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Update user by UUID (admin only)
    """
    # Uses helper that validates UUID format and returns 400 for invalid UUIDs
    user = get_user_by_uuid(db, user_uuid)

    # Update fields
    update_data = user_update.model_dump(exclude_unset=True)

    # Hash password if it's provided
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))

    # Remove current_password from update_data as it's not a model field
    update_data.pop("current_password", None)

    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    return user


@router.delete("/{user_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Delete user by UUID (admin only)
    """
    # Uses helper that validates UUID format and returns 400 for invalid UUIDs
    user = get_user_by_uuid(db, user_uuid)

    # Prevent deleting self
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete own user account",
        )

    db.delete(user)
    db.commit()

    return None
