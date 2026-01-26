"""
Authentication type constants.

Centralizes all authentication type constants to avoid magic strings
and ensure consistency across the codebase.
"""

# Authentication type constants
AUTH_TYPE_LOCAL = "local"
AUTH_TYPE_LDAP = "ldap"
AUTH_TYPE_KEYCLOAK = "keycloak"
AUTH_TYPE_PKI = "pki"

# All valid auth types
VALID_AUTH_TYPES = [AUTH_TYPE_LOCAL, AUTH_TYPE_LDAP, AUTH_TYPE_KEYCLOAK, AUTH_TYPE_PKI]

# Placeholder for external auth users who authenticate via external provider
# These users don't have local passwords. Using a distinctive value that:
# 1. Cannot be a valid bcrypt hash (starts with $2b$)
# 2. Clearly indicates intentional external authentication
# 3. Will fail any password verification attempt
EXTERNAL_AUTH_NO_PASSWORD = "!EXTERNAL_AUTH_NO_LOCAL_PASSWORD!"  # noqa: S105 # nosec B105
