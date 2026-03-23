# Environment Variables for FIPS 140-3 and Super Admin

This document lists the environment variables to add to your `.env.example` file for FIPS 140-3 compliance and super admin features.

> **v0.4.0 Note**: Authentication configuration is now stored encrypted (AES-256-GCM) in the database and managed via the Super Admin UI. The environment variables below function as initial seed values only — once configuration is saved via the Admin UI, the database values take precedence. FIPS-related variables (`FIPS_MODE`, `FIPS_VERSION`, `PBKDF2_ITERATIONS*`) continue to be read from the environment as they configure the cryptographic subsystem itself, not the auth configuration.

## How to Add to .env.example

Add the following sections to your `.env.example` file in the appropriate locations:

### FIPS 140-3 Configuration (add after FIPS 140-2 section)

```bash
# ===== FIPS 140-3 Configuration (upgraded from FIPS 140-2) =====
# FIPS version: "140-2" for legacy compliance, "140-3" for current standard (default)
# FIPS 140-3 is mandatory for new federal systems since September 2021
FIPS_VERSION=140-3

# PBKDF2 iterations for FIPS 140-3 (NIST SP 800-132 2024 recommendation)
# 600,000 iterations provides ~0.5 second verification time on modern hardware
PBKDF2_ITERATIONS_V3=600000

# JWT signing algorithm for FIPS 140-3 (HS512 for stronger HMAC signatures)
JWT_ALGORITHM_V3=HS512

# Encryption algorithm for sensitive data (AES-256-GCM for FIPS 140-3)
ENCRYPTION_ALGORITHM_V3=AES-256-GCM

# Migration mode: "compatible" accepts both old and new formats during transition
# "strict" only accepts FIPS 140-3 compliant formats (use after migration complete)
FIPS_MIGRATION_MODE=compatible

# Entropy validation for cryptographic operations
FIPS_VALIDATE_ENTROPY=true

# TOTP algorithm for MFA (SHA1 default for app compatibility, SHA256/SHA512 for high-security)
# SHA-1 is FIPS-approved for HMAC applications per NIST SP 800-131A Rev. 2
TOTP_ALGORITHM=SHA1
```

### Super Admin Bootstrap (add after Audit Logging section)

```bash
# ===== Super Admin Bootstrap =====
# Email address for bootstrapping the first super admin user
# The first user to register with this email will automatically be assigned super_admin role
# Leave empty to disable bootstrap (require manual database update for first super admin)
BOOTSTRAP_SUPER_ADMIN_EMAIL=

# Note: After bootstrapping, remove or clear this value for security
# Super admins can promote other users to super_admin via Settings → Users

# ===== Audit Logging (v0.4.0+) =====
# Export audit events to OpenSearch for full-text search and SIEM integration
AUDIT_LOG_TO_OPENSEARCH=false
```

## Full Configuration Example

Here is a complete example showing all FIPS 140-3 and related security variables:

```bash
# ============================================================================
# FIPS 140-2/3 COMPLIANCE SETTINGS
# ============================================================================

# Enable FIPS mode to use only FIPS-approved algorithms
FIPS_MODE=true

# FIPS 140-2 PBKDF2 iterations (OWASP 2023 recommendation)
PBKDF2_ITERATIONS=210000

# ===== FIPS 140-3 Configuration =====
FIPS_VERSION=140-3
PBKDF2_ITERATIONS_V3=600000
JWT_ALGORITHM_V3=HS512
ENCRYPTION_ALGORITHM_V3=AES-256-GCM
FIPS_MIGRATION_MODE=compatible
FIPS_VALIDATE_ENTROPY=true
TOTP_ALGORITHM=SHA1

# ===== Super Admin Bootstrap =====
BOOTSTRAP_SUPER_ADMIN_EMAIL=admin@example.com
```

## Migration Notes

### From FIPS 140-2 to FIPS 140-3

1. Set `FIPS_MIGRATION_MODE=compatible` to allow both old and new formats
2. Set `FIPS_VERSION=140-3` to enable FIPS 140-3 algorithms for new operations
3. Existing data will be auto-upgraded when accessed
4. After all users have logged in and data has been migrated, optionally set `FIPS_MIGRATION_MODE=strict`

### Rollback

To rollback to FIPS 140-2:
1. Set `FIPS_VERSION=140-2`
2. Keep `FIPS_MIGRATION_MODE=compatible`
3. System will continue to read FIPS 140-3 data but create new data with FIPS 140-2 algorithms

## Related Documentation

- [FIPS 140-3 Compliance Guide](/docs/FIPS_140_3_COMPLIANCE.md)
- [FIPS 140-2 Compliance Guide](/docs/FIPS_COMPLIANCE.md)
- [Super Admin Guide](/docs/SUPER_ADMIN_GUIDE.md)
- [Auth Deployment Guide](/docs/AUTH_DEPLOYMENT_GUIDE.md)
- [Security Policy](/docs/SECURITY.md)
