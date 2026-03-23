---
sidebar_position: 1
title: Authentication Overview
---

# Authentication Overview

OpenTranscribe supports multiple authentication methods to integrate with your existing infrastructure and meet enterprise security requirements.

## Authentication Methods

| Method | Use Case | Configuration |
|--------|----------|---------------|
| **Local** | Default, standalone deployments | Built-in, no additional setup |
| **LDAP/Active Directory** | Enterprise with existing AD infrastructure | [LDAP Setup Guide](./ldap) |
| **OIDC/Keycloak** | SSO with identity providers | [Keycloak Setup Guide](./keycloak) |
| **PKI/X.509** | Government, high-security environments | [PKI Setup Guide](./pki) |

## Quick Comparison

### Local Authentication
- Username/password stored in PostgreSQL
- Self-registration or admin-created accounts
- Password policies enforced (length, complexity, history)
- Best for: Small teams, standalone deployments

### LDAP/Active Directory
- Authenticate against existing AD/LDAP directory
- Users auto-created on first login
- Roles mapped via `LDAP_ADMIN_USERS` configuration
- Hybrid mode: Local + LDAP users coexist
- Best for: Enterprise with existing directory services

### OIDC/Keycloak
- Single Sign-On via OpenID Connect
- Supports identity federation (LDAP, social login via Keycloak)
- Roles synchronized from Keycloak
- Best for: Organizations with existing IdP, SSO requirements

### PKI/X.509 Certificates
- Certificate-based authentication via mutual TLS
- CAC/PIV smart card support
- No passwords required
- Best for: Government, military, high-security environments

## Security Features

OpenTranscribe includes enterprise security features that work with all authentication methods:

### Multi-Factor Authentication (MFA)
- TOTP-based (Google Authenticator, Authy, etc.)
- Backup codes for recovery
- Per-user enablement
- Configuration: `MFA_ENABLED=true`

### Password Policies (FedRAMP IA-5)
- Minimum length (default: 12 characters)
- Complexity requirements (uppercase, lowercase, digits, special)
- Password history (prevent reuse of last 24 passwords)
- Password expiration (default: 60 days)
- Configuration: `PASSWORD_POLICY_ENABLED=true`

### Account Lockout (NIST AC-7)
- Lock after failed attempts (default: 5)
- Progressive lockout durations
- Admin unlock capability
- Configuration: `ACCOUNT_LOCKOUT_ENABLED=true`

### Rate Limiting
- Per-IP rate limiting for authentication endpoints
- Redis-backed for distributed deployments
- Configuration: `RATE_LIMIT_AUTH_PER_MINUTE=10`

### Audit Logging (FedRAMP AU-2/AU-3)
- Structured JSON or CEF format
- All authentication events logged
- Optional OpenSearch integration
- Configuration: `AUDIT_LOG_ENABLED=true`

### Classification Banners
- Configurable login banner text
- User acknowledgment tracking
- Configuration: `LOGIN_BANNER_TEXT`, `LOGIN_BANNER_TITLE`

## Configuration Quick Reference

Add to your `.env` file:

```bash
# Authentication Method (choose one or combine)
LDAP_ENABLED=false
KEYCLOAK_ENABLED=false
PKI_ENABLED=false

# Security Features
MFA_ENABLED=true
PASSWORD_POLICY_ENABLED=true
ACCOUNT_LOCKOUT_ENABLED=true
RATE_LIMIT_ENABLED=true
AUDIT_LOG_ENABLED=true

# Password Policy
PASSWORD_MIN_LENGTH=12
PASSWORD_REQUIRE_UPPERCASE=true
PASSWORD_REQUIRE_LOWERCASE=true
PASSWORD_REQUIRE_DIGIT=true
PASSWORD_REQUIRE_SPECIAL=true
PASSWORD_HISTORY_COUNT=24
PASSWORD_MAX_AGE_DAYS=60

# Account Lockout
ACCOUNT_LOCKOUT_THRESHOLD=5
ACCOUNT_LOCKOUT_DURATION_MINUTES=15
ACCOUNT_LOCKOUT_PROGRESSIVE=true
ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES=1440

# Rate Limiting
RATE_LIMIT_AUTH_PER_MINUTE=10
RATE_LIMIT_API_PER_MINUTE=100

# MFA
MFA_ISSUER_NAME=OpenTranscribe
MFA_BACKUP_CODE_COUNT=10

# Audit Logging
AUDIT_LOG_FORMAT=json
AUDIT_LOG_TO_OPENSEARCH=false

# Login Banner (optional)
LOGIN_BANNER_ENABLED=false
LOGIN_BANNER_TITLE=Security Notice
LOGIN_BANNER_TEXT=Authorized users only...
```

## Compliance

OpenTranscribe's authentication system is designed with compliance requirements in mind:

| Requirement | Feature | Configuration |
|-------------|---------|---------------|
| FedRAMP IA-2 | Multi-Factor Authentication | `MFA_ENABLED=true` |
| FedRAMP IA-5 | Password Policies | `PASSWORD_POLICY_ENABLED=true` |
| NIST AC-7 | Account Lockout | `ACCOUNT_LOCKOUT_ENABLED=true` |
| FedRAMP AU-2/AU-3 | Audit Logging | `AUDIT_LOG_ENABLED=true` |

## Next Steps

- [LDAP/Active Directory Setup](./ldap) - Enterprise directory integration
- [Keycloak/OIDC Setup](./keycloak) - Single Sign-On configuration
- [PKI/X.509 Setup](./pki) - Certificate-based authentication
- [Environment Variables](../configuration/environment-variables.md) - Complete configuration reference
