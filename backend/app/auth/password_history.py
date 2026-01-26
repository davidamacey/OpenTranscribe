"""
Password history service for FedRAMP IA-5 compliance.

Provides functions to:
- Store new passwords in history
- Check if a password has been used recently
- Manage password history cleanup
"""

import logging

from sqlalchemy.orm import Session

from app.auth.password_policy import password_policy
from app.core.config import settings
from app.core.security import verify_password
from app.models.password_history import PasswordHistory

logger = logging.getLogger(__name__)


def add_password_to_history(db: Session, user_id: int, password_hash: str) -> PasswordHistory:
    """
    Add a password hash to the user's password history.

    This should be called after a successful password change or user registration.
    Old entries beyond the history count limit are automatically cleaned up.

    Args:
        db: Database session
        user_id: The user's ID
        password_hash: The hashed password to store

    Returns:
        The created PasswordHistory record
    """
    # Create new history entry
    history_entry = PasswordHistory(
        user_id=user_id,
        password_hash=password_hash,
    )
    db.add(history_entry)
    db.flush()  # Get the ID without committing

    # Clean up old entries beyond the configured limit
    _cleanup_old_history(db, user_id)

    logger.debug(f"Added password to history for user {user_id}")
    return history_entry


def check_password_against_history(
    db: Session,
    user_id: int,
    plain_password: str,
) -> bool:
    """
    Check if a password has been used recently by the user.

    Retrieves the user's password history and checks if the new password
    matches any of the stored hashes (up to PASSWORD_HISTORY_COUNT).

    Args:
        db: Database session
        user_id: The user's ID
        plain_password: The plaintext password to check

    Returns:
        True if the password is OK (not in history), False if recently used
    """
    if not password_policy.enabled or password_policy.history_count <= 0:
        return True

    # Get password history for the user (ordered by created_at desc via relationship)
    history_entries = (
        db.query(PasswordHistory)
        .filter(PasswordHistory.user_id == user_id)
        .order_by(PasswordHistory.created_at.desc())
        .limit(password_policy.history_count)
        .all()
    )

    # Extract just the hashes
    password_hashes = [str(entry.password_hash) for entry in history_entries]

    # Use the password policy's check function
    return password_policy.check_password_history(  # nosec B106
        new_password_hash="",  # Not used - placeholder for API compatibility
        password_history=password_hashes,
        verify_func=verify_password,
        plain_password=plain_password,
    )


def get_user_password_history(
    db: Session, user_id: int, limit: int | None = None
) -> list[PasswordHistory]:
    """
    Get the password history for a user.

    Args:
        db: Database session
        user_id: The user's ID
        limit: Maximum number of entries to return (default: PASSWORD_HISTORY_COUNT)

    Returns:
        List of PasswordHistory records, most recent first
    """
    if limit is None:
        limit = settings.PASSWORD_HISTORY_COUNT

    return (  # type: ignore[no-any-return]
        db.query(PasswordHistory)
        .filter(PasswordHistory.user_id == user_id)
        .order_by(PasswordHistory.created_at.desc())
        .limit(limit)
        .all()
    )


def _cleanup_old_history(db: Session, user_id: int) -> int:
    """
    Remove password history entries beyond the configured limit.

    Args:
        db: Database session
        user_id: The user's ID

    Returns:
        Number of entries deleted
    """
    if password_policy.history_count <= 0:
        return 0

    # Get IDs of entries to keep (most recent N)
    keep_entries = (
        db.query(PasswordHistory.id)
        .filter(PasswordHistory.user_id == user_id)
        .order_by(PasswordHistory.created_at.desc())
        .limit(password_policy.history_count)
        .all()
    )
    keep_ids = [entry.id for entry in keep_entries]

    if not keep_ids:
        return 0

    # Delete entries not in the keep list
    deleted = (
        db.query(PasswordHistory)
        .filter(
            PasswordHistory.user_id == user_id,
            ~PasswordHistory.id.in_(keep_ids),
        )
        .delete(synchronize_session=False)
    )

    if deleted > 0:
        logger.debug(f"Cleaned up {deleted} old password history entries for user {user_id}")

    return deleted  # type: ignore[no-any-return]
