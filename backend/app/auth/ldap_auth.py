"""
LDAP/Active Directory authentication module.

Handles authentication against Active Directory using LDAPS.
"""

import logging
import re
from typing import Optional
from typing import TypedDict

from ldap3 import ALL
from ldap3 import AUTO_BIND_TLS_BEFORE_BIND
from ldap3 import Connection
from ldap3 import Server
from ldap3.core.exceptions import LDAPBindError
from ldap3.core.exceptions import LDAPException
from sqlalchemy.exc import IntegrityError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Auth type constants - use these instead of magic strings
AUTH_TYPE_LOCAL = "local"
AUTH_TYPE_LDAP = "ldap"

# Placeholder for LDAP users who authenticate via directory, not local password
# This is intentionally empty - LDAP users don't have local passwords
LDAP_NO_PASSWORD = ""  # nosec B105


class LdapUserData(TypedDict):
    """Type definition for LDAP user data returned by ldap_authenticate."""

    username: str
    email: str
    full_name: str
    is_admin: bool


def _escape_ldap_filter(value: str) -> str:
    """Escape special characters in LDAP filter values to prevent injection.

    LDAP special characters that need escaping: ( ) * \\ NUL

    Args:
        value: The string to escape

    Returns:
        Escaped string safe for use in LDAP filters
    """
    return (
        value.replace("\\", "\\5c")
        .replace("*", "\\2a")
        .replace("(", "\\28")
        .replace(")", "\\29")
        .replace("\x00", "\\00")
    )


def _is_valid_email(email: str) -> bool:
    """Validate email format.

    Args:
        email: The email address to validate

    Returns:
        True if email format is valid, False otherwise
    """
    if not email:
        return False
    # Simple email regex - must have @ and domain with at least one dot
    pattern = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    return bool(re.match(pattern, email))


def _get_ldap_server() -> Server:
    """Create and return an LDAP server object.

    Returns:
        Server: Configured LDAP server object
    """
    return Server(
        settings.LDAP_SERVER,
        port=settings.LDAP_PORT,
        use_ssl=settings.LDAP_USE_SSL,
        get_info=ALL,
        connect_timeout=settings.LDAP_TIMEOUT,
    )


def _close_connection(conn: Optional[Connection], name: str) -> None:
    """Safely close an LDAP connection.

    Args:
        conn: The connection to close (may be None)
        name: Connection name for logging
    """
    if conn is None:
        return
    try:
        if conn.bound:
            conn.unbind()
    except Exception:
        logger.debug(f"Error closing {name} connection (ignored)")


def _bind_service_account(server: Server) -> Optional[Connection]:
    """Bind to LDAP server using service account.

    Args:
        server: LDAP server object

    Returns:
        Connection if successful, None otherwise
    """
    try:
        conn = Connection(
            server,
            user=settings.LDAP_BIND_DN,
            password=settings.LDAP_BIND_PASSWORD,
            auto_bind=AUTO_BIND_TLS_BEFORE_BIND if settings.LDAP_USE_SSL else True,
        )
        logger.debug("LDAP service account bind successful")
        return conn
    except LDAPBindError:
        logger.error(
            "Failed to bind to LDAP server with service account. "
            "Check LDAP_BIND_DN and LDAP_BIND_PASSWORD configuration."
        )
        return None


def _search_ldap_user(bind_conn: Connection, username: str, ldap_username: str):
    """Search for user in LDAP by username or email.

    Args:
        bind_conn: Authenticated service account connection
        username: Original username (may be email)
        ldap_username: Extracted username without domain

    Returns:
        First matching entry or None
    """
    attributes = [
        settings.LDAP_USERNAME_ATTR,
        settings.LDAP_EMAIL_ATTR,
        settings.LDAP_NAME_ATTR,
    ]

    # Search by username attribute first
    search_filter = settings.LDAP_USER_SEARCH_FILTER.format(
        username=_escape_ldap_filter(ldap_username)
    )
    bind_conn.search(
        search_base=settings.LDAP_SEARCH_BASE,
        search_filter=search_filter,
        attributes=attributes,
    )

    if bind_conn.entries:
        return bind_conn.entries[0]

    # Fallback: search by email
    logger.debug(
        f"User not found by {settings.LDAP_USERNAME_ATTR}={ldap_username}, " "trying email search"
    )
    email_search_filter = f"({settings.LDAP_EMAIL_ATTR}={_escape_ldap_filter(username)})"
    bind_conn.search(
        search_base=settings.LDAP_SEARCH_BASE,
        search_filter=email_search_filter,
        attributes=attributes,
    )

    return bind_conn.entries[0] if bind_conn.entries else None


def _extract_user_attributes(user_entry, ldap_username: str) -> Optional[dict]:
    """Extract and validate user attributes from LDAP entry.

    Args:
        user_entry: LDAP entry object
        ldap_username: Fallback username if not in entry

    Returns:
        Dict with username, email, full_name or None if validation fails
    """
    # Extract username
    attr_value = (
        getattr(user_entry, settings.LDAP_USERNAME_ATTR, None)
        if hasattr(user_entry, settings.LDAP_USERNAME_ATTR)
        else None
    )
    username_value = str(attr_value) if attr_value is not None else ldap_username

    # Extract email
    email_value = (
        user_entry[settings.LDAP_EMAIL_ATTR].value
        if settings.LDAP_EMAIL_ATTR in user_entry
        else None
    )
    user_email = str(email_value) if email_value is not None else ""

    # Extract full name
    name_value = (
        user_entry[settings.LDAP_NAME_ATTR].value if settings.LDAP_NAME_ATTR in user_entry else None
    )
    user_full_name = str(name_value) if name_value is not None else ""

    # Validate email
    if not _is_valid_email(user_email):
        logger.warning(
            f"User {username_value} has no valid email attribute in LDAP " f"(got: {user_email!r})"
        )
        return None

    return {
        "username": username_value,
        "email": user_email,
        "full_name": user_full_name,
    }


def _verify_user_credentials(server: Server, user_dn: str, password: str) -> Optional[Connection]:
    """Verify user credentials by binding as the user.

    Args:
        server: LDAP server object
        user_dn: User's distinguished name
        password: User's password

    Returns:
        Connection if successful, None otherwise
    """
    try:
        conn = Connection(
            server,
            user=user_dn,
            password=password,
            auto_bind=AUTO_BIND_TLS_BEFORE_BIND if settings.LDAP_USE_SSL else True,
        )
        return conn
    except LDAPBindError:
        return None


def _is_ldap_admin(username: str) -> bool:
    """Check if username is in LDAP admin users list.

    Args:
        username: Username to check

    Returns:
        True if user is an admin
    """
    if not settings.LDAP_ADMIN_USERS:
        return False
    admin_users = settings.LDAP_ADMIN_USERS.split(",")
    return username.strip().lower() in [u.strip().lower() for u in admin_users]


def ldap_authenticate(username: str, password: str) -> Optional[LdapUserData]:
    """Authenticate a user against Active Directory.

    This function:
    1. Connects to AD using a service account
    2. Searches for the user by sAMAccountName (or email if username contains @)
    3. Attempts to bind as the user to verify credentials
    4. Extracts user attributes (email, full name)

    Args:
        username: The username (sAMAccountName) or email to authenticate
        password: The user's password

    Returns:
        LdapUserData dict with username, email, full_name, is_admin
        None: If authentication fails
    """
    if not settings.LDAP_ENABLED:
        logger.warning("LDAP authentication attempted but LDAP is not enabled")
        return None

    # Validate inputs early - prevent empty credential attacks
    if not username or not password:
        logger.warning("LDAP authentication attempted with empty username or password")
        return None

    logger.debug(f"LDAP authenticate called for: {username}")
    ldap_username = username.split("@")[0] if "@" in username else username

    bind_conn: Optional[Connection] = None
    user_conn: Optional[Connection] = None

    try:
        server = _get_ldap_server()

        # Step 1: Bind with service account
        bind_conn = _bind_service_account(server)
        if not bind_conn:
            return None

        # Step 2: Search for user
        user_entry = _search_ldap_user(bind_conn, username, ldap_username)
        if not user_entry:
            logger.warning(f"User not found in LDAP: {username}")
            return None

        logger.debug(f"Found user in LDAP: {user_entry.entry_dn}")

        # Step 3: Extract and validate attributes
        attrs = _extract_user_attributes(user_entry, ldap_username)
        if not attrs:
            return None

        # Step 4: Verify credentials
        user_conn = _verify_user_credentials(server, user_entry.entry_dn, password)
        if not user_conn:
            logger.warning(f"LDAP password verification failed for user: {attrs['username']}")
            return None

        logger.info(f"LDAP authentication successful for user: {attrs['username']}")

        # Step 5: Determine admin status
        return LdapUserData(
            username=attrs["username"],
            email=attrs["email"],
            full_name=attrs["full_name"],
            is_admin=_is_ldap_admin(attrs["username"]),
        )

    except LDAPException as e:
        logger.error(f"LDAP authentication error for {username}: {type(e).__name__}")
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error during LDAP authentication for {username}: {type(e).__name__}"
        )
        return None
    finally:
        _close_connection(user_conn, "user")
        _close_connection(bind_conn, "service")


def _create_ldap_user(db, username: str, email: str, ldap_data: LdapUserData):
    """Create a new user from LDAP data.

    Args:
        db: Database session
        username: LDAP username
        email: User email
        ldap_data: LDAP user data

    Returns:
        Created User object

    Raises:
        ValueError: If user cannot be created or found after race condition
    """
    from app.models.user import User

    logger.info(f"Creating new user from LDAP: {username} ({email})")
    user = User(
        email=email,
        full_name=ldap_data["full_name"] or email.split("@")[0],
        hashed_password=LDAP_NO_PASSWORD,
        auth_type=AUTH_TYPE_LDAP,
        ldap_uid=username,
        role="admin" if ldap_data["is_admin"] else "user",
        is_active=True,
        is_superuser=ldap_data["is_admin"],
    )
    db.add(user)

    try:
        db.commit()
        return user
    except IntegrityError:
        # Race condition: user was created by concurrent request
        db.rollback()
        logger.info(f"User {username} was created by concurrent request, fetching existing user")
        user = db.query(User).filter(User.ldap_uid == username).first()
        if not user:
            user = db.query(User).filter(User.email == email).first()
        if not user:
            raise ValueError(f"Failed to create or find LDAP user: {username}") from None
        return user


def _update_ldap_user(db, user, username: str, email: str, ldap_data: LdapUserData):
    """Update an existing LDAP user's data.

    Args:
        db: Database session
        user: Existing User object
        username: LDAP username
        email: User email
        ldap_data: LDAP user data

    Returns:
        Updated User object
    """
    logger.info(f"Updating existing LDAP user: {username} ({email})")
    user.email = email
    user.full_name = ldap_data["full_name"] or user.full_name
    user.ldap_uid = username
    user.auth_type = AUTH_TYPE_LDAP

    # Update admin role based on current LDAP_ADMIN_USERS list
    if ldap_data["is_admin"]:
        if user.role != "admin":
            logger.info(f"Promoting LDAP user {username} to admin")
        user.role = "admin"
        user.is_superuser = True
    elif user.role == "admin":
        # Demote if user was admin but is no longer in LDAP_ADMIN_USERS
        logger.info(f"Demoting LDAP user {username} from admin (removed from LDAP_ADMIN_USERS)")
        user.role = "user"
        user.is_superuser = False

    db.commit()
    return user


def sync_ldap_user_to_db(db, ldap_data: LdapUserData):
    """Create or update a user in the database from LDAP data.

    Handles:
    - Creating new users on first LDAP login
    - Updating existing LDAP users
    - Protecting existing local users from being converted to LDAP
    - Admin role promotion and demotion based on LDAP_ADMIN_USERS
    - Race conditions when multiple concurrent logins occur

    Args:
        db: Database session
        ldap_data: Dictionary with LDAP user data (username, email, full_name, is_admin)

    Returns:
        User: The created or updated User object

    Raises:
        ValueError: If user cannot be created or found after race condition
    """
    from app.models.user import User

    username = ldap_data["username"]
    email = ldap_data["email"]

    # Check if user exists by ldap_uid first (most specific)
    user = db.query(User).filter(User.ldap_uid == username).first()
    if not user:
        user = db.query(User).filter(User.email == email).first()

    if not user:
        user = _create_ldap_user(db, username, email, ldap_data)
    elif user.auth_type == AUTH_TYPE_LOCAL:
        # Don't convert existing local users to LDAP
        logger.warning(
            f"User {email} exists as local user, not converting to LDAP. "
            "User can still authenticate via LDAP but auth_type remains 'local'."
        )
    else:
        user = _update_ldap_user(db, user, username, email, ldap_data)

    db.refresh(user)
    return user
