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

from app.auth.constants import AUTH_TYPE_LDAP
from app.auth.constants import AUTH_TYPE_LOCAL
from app.auth.constants import EXTERNAL_AUTH_NO_PASSWORD
from app.core.config import settings

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility
LDAP_NO_PASSWORD = EXTERNAL_AUTH_NO_PASSWORD


class LdapUserData(TypedDict):
    """Type definition for LDAP user data returned by ldap_authenticate."""

    username: str
    email: str
    full_name: str
    is_admin: bool
    groups: list[str]


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
    # Only add group attribute if configured (some LDAP servers don't have memberOf)
    if settings.LDAP_GROUP_ATTR:
        attributes.append(settings.LDAP_GROUP_ATTR)

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
        f"User not found by {settings.LDAP_USERNAME_ATTR}={ldap_username}, trying email search"
    )
    email_search_filter = f"({settings.LDAP_EMAIL_ATTR}={_escape_ldap_filter(username)})"
    bind_conn.search(
        search_base=settings.LDAP_SEARCH_BASE,
        search_filter=email_search_filter,
        attributes=attributes,
    )

    return bind_conn.entries[0] if bind_conn.entries else None


def _get_user_groups(user_entry) -> list[str]:
    """Extract group DNs from LDAP user entry.

    Args:
        user_entry: LDAP entry object

    Returns:
        List of group DNs the user is a member of
    """
    group_attr = settings.LDAP_GROUP_ATTR
    if group_attr not in user_entry:
        return []

    group_value = user_entry[group_attr].value
    if group_value is None:
        return []

    # Handle both single value and multi-value attributes
    if isinstance(group_value, list):
        return [str(g) for g in group_value]
    return [str(group_value)]


def _is_member_of_groups(user_groups: list[str], required_groups: list[str]) -> bool:
    """Check if user is a member of any of the required groups.

    Args:
        user_groups: List of group DNs the user belongs to
        required_groups: List of group DNs to check membership against

    Returns:
        True if user is a member of at least one required group
    """
    if not required_groups:
        return True

    # Normalize DNs for case-insensitive comparison
    user_groups_lower = [g.lower().strip() for g in user_groups]
    required_groups_lower = [g.lower().strip() for g in required_groups]

    return any(required_group in user_groups_lower for required_group in required_groups_lower)


def _get_required_user_groups() -> list[str]:
    """Parse LDAP_USER_GROUPS setting into a list of required group DNs.

    Returns:
        List of required group DNs (empty if no restrictions configured)
    """
    if not settings.LDAP_USER_GROUPS:
        return []
    return [g.strip() for g in settings.LDAP_USER_GROUPS.split(",") if g.strip()]


def _check_group_access(user_groups: list[str]) -> bool:
    """Verify user has required group membership for access.

    If LDAP_USER_GROUPS is configured, user must be a member of at least
    one of those groups to access the application.

    Args:
        user_groups: List of group DNs the user belongs to

    Returns:
        True if user has access (in required groups or no groups required)
    """
    required_groups = _get_required_user_groups()
    if not required_groups:
        return True

    has_access = _is_member_of_groups(user_groups, required_groups)
    if not has_access:
        logger.warning(
            "User denied access - not a member of any required groups. "
            f"User groups: {user_groups}, Required: {required_groups}"
        )
    return has_access


def _check_group_access_with_recursion(
    bind_conn: Connection, user_dn: str, user_groups: list[str], username: str
) -> bool:
    """Check group-based access with optional recursive membership lookup.

    This function consolidates all group access checking logic:
    1. Returns True if no LDAP_USER_GROUPS configured
    2. Checks direct group membership first
    3. If not found and LDAP_RECURSIVE_GROUPS enabled, checks recursive membership
    4. Logs warning if access denied

    Args:
        bind_conn: Authenticated service account connection
        user_dn: User's distinguished name
        user_groups: List of group DNs the user belongs to (from direct membership)
        username: Username for logging

    Returns:
        True if user has access, False otherwise
    """
    required_groups = _get_required_user_groups()
    if not required_groups:
        return True

    # Check direct membership first
    if _is_member_of_groups(user_groups, required_groups):
        return True

    # Check recursive membership if enabled
    if settings.LDAP_RECURSIVE_GROUPS:
        if _search_recursive_group_membership(bind_conn, user_dn, required_groups):
            return True
        logger.warning(
            f"User {username} denied access - not a member of required groups "
            "(recursive check enabled)"
        )
        return False

    # Direct check failed and recursive not enabled
    logger.warning(
        f"User {username} denied access - not a member of any required groups. "
        f"User groups: {user_groups}, Required: {required_groups}"
    )
    return False


def _search_recursive_group_membership(
    bind_conn: Connection, user_dn: str, group_dns: list[str]
) -> bool:
    """Check recursive group membership using LDAP_MATCHING_RULE_IN_CHAIN.

    This uses the Active Directory OID 1.2.840.113556.1.4.1941 to search
    nested/recursive group membership.

    Args:
        bind_conn: Authenticated service account connection
        user_dn: User's distinguished name
        group_dns: List of group DNs to check membership

    Returns:
        True if user is a member of any group (including nested)
    """
    # LDAP_MATCHING_RULE_IN_CHAIN OID for recursive group membership
    matching_rule_in_chain = "1.2.840.113556.1.4.1941"

    for group_dn in group_dns:
        try:
            bind_conn.search(
                search_base=group_dn,
                search_filter="(objectClass=*)",
                search_scope="BASE",
                attributes=["distinguishedName"],
            )

            if bind_conn.entries:
                # Now check if user is a member (recursively)
                recursive_filter = (
                    f"(&(distinguishedName={_escape_ldap_filter(group_dn)})"
                    f"(member:{matching_rule_in_chain}:={_escape_ldap_filter(user_dn)}))"
                )
                bind_conn.search(
                    search_base=group_dn,
                    search_filter=recursive_filter,
                    search_scope="BASE",
                )
                if bind_conn.entries:
                    logger.debug(f"User {user_dn} is a recursive member of group {group_dn}")
                    return True
        except LDAPException as e:
            logger.debug(f"Error checking recursive group membership for {group_dn}: {e}")
            continue

    return False


def _extract_user_attributes(user_entry, ldap_username: str) -> Optional[dict]:
    """Extract and validate user attributes from LDAP entry.

    Args:
        user_entry: LDAP entry object
        ldap_username: Fallback username if not in entry

    Returns:
        Dict with username, email, full_name, groups or None if validation fails
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

    # Extract group memberships
    user_groups = _get_user_groups(user_entry)

    # Validate email
    if not _is_valid_email(user_email):
        logger.warning(
            f"User {username_value} has no valid email attribute in LDAP (got: {user_email!r})"
        )
        return None

    return {
        "username": username_value,
        "email": user_email,
        "full_name": user_full_name,
        "groups": user_groups,
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


def _is_ldap_admin(
    username: str,
    user_groups: list[str],
    bind_conn: Optional[Connection] = None,
    user_dn: Optional[str] = None,
) -> bool:
    """Check if user is an admin via LDAP_ADMIN_USERS or LDAP_ADMIN_GROUPS.

    Admin status is granted if the user is in either:
    1. LDAP_ADMIN_USERS list (comma-separated usernames)
    2. Any group in LDAP_ADMIN_GROUPS list (comma-separated group DNs)

    Args:
        username: Username to check
        user_groups: List of group DNs the user belongs to
        bind_conn: Optional LDAP connection for recursive group checks
        user_dn: Optional user DN for recursive group checks

    Returns:
        True if user is an admin
    """
    # Check LDAP_ADMIN_USERS first (original behavior)
    if settings.LDAP_ADMIN_USERS:
        admin_users = settings.LDAP_ADMIN_USERS.split(",")
        if username.strip().lower() in [u.strip().lower() for u in admin_users]:
            logger.debug(f"User {username} is admin via LDAP_ADMIN_USERS")
            return True

    # Check LDAP_ADMIN_GROUPS
    if settings.LDAP_ADMIN_GROUPS:
        admin_groups = [g.strip() for g in settings.LDAP_ADMIN_GROUPS.split(",") if g.strip()]

        # Direct group membership check
        if _is_member_of_groups(user_groups, admin_groups):
            logger.debug(f"User {username} is admin via LDAP_ADMIN_GROUPS (direct membership)")
            return True

        # Recursive group check if enabled and connection available
        if (
            settings.LDAP_RECURSIVE_GROUPS
            and bind_conn
            and user_dn
            and _search_recursive_group_membership(bind_conn, user_dn, admin_groups)
        ):
            logger.debug(f"User {username} is admin via LDAP_ADMIN_GROUPS (recursive membership)")
            return True

    return False


def ldap_authenticate(username: str, password: str) -> Optional[LdapUserData]:
    """Authenticate a user against Active Directory.

    This function:
    1. Connects to AD using a service account
    2. Searches for the user by sAMAccountName (or email if username contains @)
    3. Attempts to bind as the user to verify credentials
    4. Extracts user attributes (email, full name, groups)
    5. Checks group-based access if LDAP_USER_GROUPS is configured
    6. Determines admin status from LDAP_ADMIN_USERS or LDAP_ADMIN_GROUPS

    Args:
        username: The username (sAMAccountName) or email to authenticate
        password: The user's password

    Returns:
        LdapUserData dict with username, email, full_name, is_admin, groups
        None: If authentication fails or user lacks required group membership
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

        user_dn = user_entry.entry_dn
        logger.debug(f"Found user in LDAP: {user_dn}")

        # Step 3: Extract and validate attributes
        attrs = _extract_user_attributes(user_entry, ldap_username)
        if not attrs:
            return None

        user_groups = attrs.get("groups", [])
        logger.debug(f"User {attrs['username']} belongs to {len(user_groups)} groups")

        # Step 4: Check group-based access requirements
        if not _check_group_access_with_recursion(
            bind_conn, user_dn, user_groups, attrs["username"]
        ):
            return None

        # Step 5: Verify credentials
        user_conn = _verify_user_credentials(server, user_dn, password)
        if not user_conn:
            logger.warning(f"LDAP password verification failed for user: {attrs['username']}")
            return None

        logger.info(f"LDAP authentication successful for user: {attrs['username']}")

        # Step 6: Determine admin status (from LDAP_ADMIN_USERS or LDAP_ADMIN_GROUPS)
        is_admin = _is_ldap_admin(
            attrs["username"],
            user_groups,
            bind_conn=bind_conn,
            user_dn=user_dn,
        )

        return LdapUserData(
            username=attrs["username"],
            email=attrs["email"],
            full_name=attrs["full_name"],
            is_admin=is_admin,
            groups=user_groups,
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

    # Log email changes at WARNING level for audit purposes
    if email and email != user.email:
        logger.warning(
            f"SECURITY: User email changed during LDAP login. "
            f"ldap_uid={username}, old_email={user.email}, new_email={email}"
        )
    user.email = email
    user.full_name = ldap_data["full_name"] or user.full_name
    user.ldap_uid = username
    user.auth_type = AUTH_TYPE_LDAP

    # Update admin role based on current LDAP_ADMIN_USERS/LDAP_ADMIN_GROUPS
    if ldap_data["is_admin"]:
        if user.role != "admin":
            logger.info(f"Promoting LDAP user {username} to admin")
        user.role = "admin"
        user.is_superuser = True
    elif user.role == "admin":
        # Demote if user was admin but is no longer in admin users/groups
        logger.info(
            f"Demoting LDAP user {username} from admin "
            "(removed from LDAP_ADMIN_USERS/LDAP_ADMIN_GROUPS)"
        )
        user.role = "user"
        user.is_superuser = False

    db.commit()
    return user


def _convert_local_user_to_ldap(db, user, username: str, email: str, ldap_data: LdapUserData):
    """Convert an existing local user to LDAP authentication.

    This is called when a user with auth_type='local' authenticates
    via LDAP. The user is converted to LDAP auth, which means:
    - auth_type is set to 'ldap'
    - hashed_password is cleared (LDAP users don't have local passwords)
    - ldap_uid is set from LDAP
    - Admin role is updated based on LDAP_ADMIN_USERS/LDAP_ADMIN_GROUPS

    Args:
        db: Database session
        user: Existing User object with auth_type='local'
        username: LDAP username
        email: User email from LDAP
        ldap_data: LDAP user data

    Returns:
        Updated User object
    """
    logger.info(f"Converting local user {user.email} to LDAP auth: {username}")

    # Convert to LDAP authentication
    user.auth_type = AUTH_TYPE_LDAP
    user.ldap_uid = username
    user.hashed_password = LDAP_NO_PASSWORD  # Clear local password

    # Log email changes at WARNING level for audit purposes
    if email and email != user.email:
        logger.warning(
            f"SECURITY: User email changed during LDAP conversion. "
            f"ldap_uid={username}, old_email={user.email}, new_email={email}"
        )
    user.email = email
    user.full_name = ldap_data["full_name"] or user.full_name

    # Update admin role based on LDAP_ADMIN_USERS/LDAP_ADMIN_GROUPS
    if ldap_data["is_admin"]:
        if user.role != "admin":
            logger.info(f"Promoting converted LDAP user {username} to admin")
        user.role = "admin"
        user.is_superuser = True
    elif user.role == "admin":
        # Demote if user was admin locally but not in admin users/groups
        logger.info(
            f"Demoting converted LDAP user {username} from admin "
            "(not in LDAP_ADMIN_USERS/LDAP_ADMIN_GROUPS)"
        )
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
        # Convert local users to LDAP auth when they authenticate via LDAP
        # This ensures they use LDAP going forward and cannot change their password
        # (since LDAP users don't have local passwords)
        logger.warning(
            f"SECURITY: Converting local user {email} to LDAP auth. "
            "User will now authenticate exclusively via LDAP. "
            "Local password will be cleared."
        )
        user = _convert_local_user_to_ldap(db, user, username, email, ldap_data)
    else:
        user = _update_ldap_user(db, user, username, email, ldap_data)

    db.refresh(user)
    return user
