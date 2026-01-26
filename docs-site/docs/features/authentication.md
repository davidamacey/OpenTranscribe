---
sidebar_position: 4
title: Authentication & Security
---

# Authentication & Security

OpenTranscribe includes enterprise-grade authentication and security features to meet organizational security requirements and compliance standards.

## Authentication Methods

### Local Authentication
Default authentication using PostgreSQL-stored credentials:
- Username/password authentication
- Self-registration or admin-created accounts
- JWT-based session management

### LDAP/Active Directory
Integrate with existing directory services:
- Hybrid authentication (local + LDAP users)
- Auto-provisioning on first login
- Role mapping via `LDAP_ADMIN_USERS`
- Support for Active Directory and OpenLDAP

### OIDC/Keycloak
Single Sign-On via OpenID Connect:
- Integration with Keycloak identity server
- Support for identity federation
- Social login via Keycloak (Google, GitHub, etc.)
- Role synchronization

### PKI/X.509 Certificates
Certificate-based authentication:
- Mutual TLS authentication via Nginx
- CAC/PIV smart card support
- No passwords required
- Government/military environment support

## Security Features

### Multi-Factor Authentication (MFA)
TOTP-based second factor authentication:
- Compatible with Google Authenticator, Authy, etc.
- QR code setup for easy enrollment
- One-time backup codes for recovery
- Per-user enablement

### Password Policies
FedRAMP IA-5 compliant password requirements:
- Configurable minimum length (default: 12)
- Character complexity (uppercase, lowercase, digits, special)
- Password history tracking (prevent reuse)
- Password expiration with grace period
- Common pattern detection

### Account Lockout
NIST AC-7 compliant account protection:
- Lock after configurable failed attempts
- Progressive lockout durations
- Admin unlock capability
- Automatic expiration

### Rate Limiting
Protection against brute force attacks:
- Per-IP rate limiting
- Configurable limits for auth and API endpoints
- Redis-backed for distributed deployments
- Trusted proxy support

### Audit Logging
FedRAMP AU-2/AU-3 compliant logging:
- Structured JSON or CEF format
- All authentication events captured
- Optional OpenSearch integration
- Request ID correlation

### Session Management
Secure session handling:
- JWT token-based sessions
- Refresh token rotation
- Concurrent session limits
- Session revocation

## Compliance

OpenTranscribe's security features support compliance with:

| Standard | Controls | Features |
|----------|----------|----------|
| FedRAMP | IA-2 | MFA, PKI authentication |
| FedRAMP | IA-5 | Password policies |
| FedRAMP | AU-2/AU-3 | Audit logging |
| NIST 800-53 | AC-7 | Account lockout |

## Quick Start

Enable security features in your `.env`:

```bash
# Enable enterprise authentication
LDAP_ENABLED=true      # or
KEYCLOAK_ENABLED=true  # or
PKI_ENABLED=true

# Enable security features
MFA_ENABLED=true
PASSWORD_POLICY_ENABLED=true
ACCOUNT_LOCKOUT_ENABLED=true
AUDIT_LOG_ENABLED=true
```

## Next Steps

- [Authentication Overview](../authentication/overview.md) - Detailed configuration
- [Environment Variables](../configuration/environment-variables.md) - Full configuration reference
- [FAQ](../faq.md) - Common questions
