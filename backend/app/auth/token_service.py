"""
Token service for refresh token management and token revocation.

Implements FedRAMP AC-12 compliant token management:
- Refresh token creation and validation
- Token revocation via Redis blacklist
- Session management through refresh token tracking

Security Features:
- Refresh tokens stored as SHA-256 hashes in database
- JTI-based revocation via Redis with TTL = remaining token lifetime
- Automatic cleanup of expired tokens
- Rate limiting on token refresh operations
"""

import hashlib
import logging
import uuid
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Optional

from jose import jwt
from sqlalchemy.orm import Session

from app.auth.session import InMemoryStore
from app.auth.session import get_redis_client
from app.core.config import settings
from app.models.refresh_token import RefreshToken

logger = logging.getLogger(__name__)

# Redis key prefix for revoked tokens (not a password)
REVOKED_TOKEN_PREFIX = "revoked:jti:"  # noqa: S105 # nosec B105


class TokenService:
    """
    Service for managing refresh tokens and token revocation.

    Provides methods for:
    - Creating refresh tokens with database persistence
    - Verifying refresh tokens
    - Revoking individual tokens or all user tokens
    - Checking token revocation status via Redis

    Uses Redis for fast token blacklist lookups with automatic TTL expiration.
    Falls back to in-memory storage when Redis is unavailable.
    """

    def __init__(self):
        """Initialize the token service."""
        self._store = None

    @property
    def store(self):
        """Lazy-load storage backend (Redis or in-memory fallback)."""
        if self._store is None:
            redis_client = get_redis_client()
            if redis_client:
                self._store = redis_client
            else:
                logger.warning(
                    "Redis unavailable for token revocation. "
                    "Using in-memory store (not recommended for production)."
                )
                self._store = InMemoryStore()
        return self._store

    @staticmethod
    def _hash_token(token: str) -> str:
        """
        Create SHA-256 hash of a token.

        Args:
            token: The token string to hash

        Returns:
            64-character hex string of the SHA-256 hash
        """
        return hashlib.sha256(token.encode()).hexdigest()

    def create_refresh_token(
        self,
        db: Session,
        user_id: int,
        user_uuid: str,
        role: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[str, RefreshToken]:
        """
        Create a new refresh token for a user.

        Creates a JWT refresh token with:
        - User UUID in 'sub' claim
        - User role in 'role' claim
        - Unique JTI for revocation tracking
        - Token type claim set to 'refresh'

        Stores token hash in database for validation and revocation.

        Args:
            db: Database session
            user_id: User's database ID
            user_uuid: User's UUID string
            role: User's role (for inclusion in token)
            user_agent: Optional user agent for session tracking
            ip_address: Optional IP address for session tracking

        Returns:
            Tuple of (token_string, RefreshToken model instance)
        """
        # Generate unique JTI
        jti = str(uuid.uuid4())

        # Calculate expiration
        now = datetime.now(timezone.utc)
        expires_delta = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        expires_at = now + expires_delta

        # Create token payload
        token_data = {
            "sub": user_uuid,
            "role": role,
            "jti": jti,
            "iat": now,
            "exp": expires_at,
            "type": "refresh",
        }

        # Encode token
        token = jwt.encode(
            token_data,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        # Hash token for storage
        token_hash = self._hash_token(token)

        # Create database record
        refresh_token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            jti=jti,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        db.add(refresh_token)
        db.commit()
        db.refresh(refresh_token)

        logger.info(
            f"Created refresh token for user {user_id} "
            f"(jti={jti[:8]}..., expires={expires_at.isoformat()})"
        )

        return token, refresh_token

    def verify_refresh_token(
        self, db: Session, token: str
    ) -> tuple[Optional[dict], Optional[RefreshToken]]:
        """
        Verify a refresh token and return its payload.

        Validation steps:
        1. Decode and verify JWT signature
        2. Check token type is 'refresh'
        3. Check token hash exists in database
        4. Check token is not revoked in database
        5. Check token is not on Redis blacklist
        6. Check token is not expired

        Args:
            db: Database session
            token: The refresh token string to verify

        Returns:
            Tuple of (payload_dict, RefreshToken model) if valid, (None, None) if invalid
        """
        try:
            # Decode token
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )

            # Verify token type
            if payload.get("type") != "refresh":
                logger.warning("Token verification failed: not a refresh token")
                return None, None

            jti = payload.get("jti")
            if not jti:
                logger.warning("Token verification failed: missing JTI")
                return None, None

            # Check Redis blacklist first (fast path)
            if self.is_token_revoked(jti):
                logger.warning(f"Token verification failed: JTI {jti[:8]}... is revoked")
                return None, None

            # Find token in database
            token_hash = self._hash_token(token)
            refresh_token = (
                db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
            )

            if not refresh_token:
                logger.warning("Token verification failed: token not found in database")
                return None, None

            # Check database revocation status
            if refresh_token.is_revoked:
                logger.warning(
                    f"Token verification failed: token revoked at "
                    f"{refresh_token.revoked_at.isoformat()}"
                )
                return None, None

            # Check expiration (should be caught by JWT decode, but double-check)
            if refresh_token.is_expired:
                logger.warning("Token verification failed: token expired")
                return None, None

            logger.debug(f"Refresh token verified successfully (jti={jti[:8]}...)")
            return payload, refresh_token

        except jwt.ExpiredSignatureError:
            logger.warning("Token verification failed: token expired")
            return None, None
        except jwt.JWTError as e:
            logger.warning(f"Token verification failed: JWT error - {e}")
            return None, None
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None, None

    def revoke_token(self, db: Session, jti: str, expires_at: Optional[datetime] = None) -> bool:
        """
        Revoke a token by adding its JTI to the Redis blacklist.

        Args:
            db: Database session
            jti: The JWT ID to revoke
            expires_at: Token expiration time (for TTL calculation)

        Returns:
            True if revoked successfully, False otherwise
        """
        try:
            # Calculate TTL (remaining token lifetime)
            if expires_at:
                now = datetime.now(timezone.utc)
                ttl_seconds = max(1, int((expires_at - now).total_seconds()))
            else:
                # Default to refresh token expiry if no expiration provided
                ttl_seconds = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60

            # Add to Redis blacklist
            key = f"{REVOKED_TOKEN_PREFIX}{jti}"
            self.store.set(key, "revoked", ex=ttl_seconds)

            # Update database record if exists
            refresh_token = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
            if refresh_token:
                refresh_token.revoked_at = datetime.now(timezone.utc)  # type: ignore[assignment]
                db.commit()

            logger.info(f"Revoked token (jti={jti[:8]}..., ttl={ttl_seconds}s)")
            return True

        except Exception as e:
            logger.error(f"Error revoking token: {e}")
            return False

    def revoke_all_user_tokens(self, db: Session, user_id: int) -> int:
        """
        Revoke all refresh tokens for a user.

        Used for:
        - Logout from all devices
        - Password change
        - Account security concerns

        Args:
            db: Database session
            user_id: User ID whose tokens should be revoked

        Returns:
            Number of tokens revoked
        """
        try:
            # Get all active refresh tokens for user
            tokens = (
                db.query(RefreshToken)
                .filter(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None),
                )
                .all()
            )

            now = datetime.now(timezone.utc)
            count = 0

            for token in tokens:
                # Add to Redis blacklist
                ttl_seconds = max(1, int((token.expires_at - now).total_seconds()))
                key = f"{REVOKED_TOKEN_PREFIX}{token.jti}"
                self.store.set(key, "revoked", ex=ttl_seconds)

                # Update database record
                token.revoked_at = now  # type: ignore[assignment]
                count += 1

            db.commit()
            logger.info(f"Revoked {count} tokens for user {user_id}")
            return count

        except Exception as e:
            logger.error(f"Error revoking user tokens: {e}")
            db.rollback()
            return 0

    def is_token_revoked(self, jti: str) -> bool:
        """
        Check if a token JTI is on the revocation blacklist.

        Args:
            jti: The JWT ID to check

        Returns:
            True if revoked, False if valid
        """
        if not settings.TOKEN_REVOCATION_ENABLED:
            return False

        key = f"{REVOKED_TOKEN_PREFIX}{jti}"
        result = self.store.get(key)
        return result is not None

    def cleanup_expired_tokens(self, db: Session) -> int:
        """
        Remove expired refresh tokens from database.

        Should be called periodically (e.g., via Celery beat) to clean up
        expired tokens that are no longer needed.

        Args:
            db: Database session

        Returns:
            Number of tokens deleted
        """
        try:
            now = datetime.now(timezone.utc)
            result = (
                db.query(RefreshToken)
                .filter(RefreshToken.expires_at < now)
                .delete(synchronize_session=False)
            )
            db.commit()
            logger.info(f"Cleaned up {result} expired refresh tokens")
            return result  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(f"Error cleaning up expired tokens: {e}")
            db.rollback()
            return 0

    def get_user_active_sessions(self, db: Session, user_id: int) -> list[dict]:
        """
        Get all active (non-revoked, non-expired) sessions for a user.

        Useful for displaying active sessions in user settings.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            List of session info dicts with created_at, user_agent, ip_address
        """
        now = datetime.now(timezone.utc)
        tokens = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .order_by(RefreshToken.created_at.desc())
            .all()
        )

        return [
            {
                "jti": token.jti,
                "created_at": token.created_at.isoformat(),
                "expires_at": token.expires_at.isoformat(),
                "user_agent": token.user_agent,
                "ip_address": token.ip_address,
            }
            for token in tokens
        ]

    def rotate_refresh_token(
        self,
        db: Session,
        old_token: str,
        old_token_record: RefreshToken,
        user_id: int,
        user_uuid: str,
        role: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[str, RefreshToken]:
        """
        Rotate a refresh token by revoking the old one and creating a new one.

        This implements OAuth 2.1 refresh token rotation best practice:
        - Revokes the old refresh token immediately
        - Creates a new refresh token with fresh expiration
        - Limits the impact of stolen refresh tokens

        Args:
            db: Database session
            old_token: The old refresh token string
            old_token_record: The RefreshToken model instance to revoke
            user_id: User's database ID
            user_uuid: User's UUID string
            role: User's role (for inclusion in token)
            user_agent: Optional user agent for session tracking
            ip_address: Optional IP address for session tracking

        Returns:
            Tuple of (new_token_string, new_RefreshToken model instance)
        """
        # Revoke the old token first
        old_jti = str(old_token_record.jti)
        old_expires = datetime(
            old_token_record.expires_at.year,
            old_token_record.expires_at.month,
            old_token_record.expires_at.day,
            old_token_record.expires_at.hour,
            old_token_record.expires_at.minute,
            old_token_record.expires_at.second,
            old_token_record.expires_at.microsecond,
            old_token_record.expires_at.tzinfo,
        )
        self.revoke_token(db, old_jti, old_expires)

        logger.info(f"Rotated out old refresh token for user {user_id} (old_jti={old_jti[:8]}...)")

        # Create new refresh token
        new_token, new_token_record = self.create_refresh_token(
            db=db,
            user_id=user_id,
            user_uuid=user_uuid,
            role=role,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        logger.info(
            f"Issued new refresh token for user {user_id} (new_jti={new_token_record.jti[:8]}...)"
        )

        return new_token, new_token_record


# Module-level singleton
token_service = TokenService()
