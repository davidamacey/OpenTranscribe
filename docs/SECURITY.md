# Security Policy

## Supported Versions

We actively maintain and provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability in OpenTranscribe, please follow these guidelines:

### Reporting Process

1. **DO NOT** create a public GitHub issue for security vulnerabilities
2. Email security concerns to: [your-email@domain.com] (replace with your email)
3. Include as much detail as possible:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fixes (if any)

### What to Expect

- **Acknowledgment**: We'll acknowledge receipt of your report within 48 hours
- **Investigation**: We'll investigate and assess the vulnerability
- **Updates**: We'll provide regular updates on our progress
- **Resolution**: We'll work to resolve the issue as quickly as possible

### Response Timeline

- **Critical vulnerabilities**: 24-48 hours for initial response, 7 days for fix
- **High severity**: 72 hours for initial response, 14 days for fix
- **Medium/Low severity**: 1 week for initial response, 30 days for fix

## Security Best Practices for Users

### Docker Security
- Keep Docker and Docker Compose updated
- Use non-root users in containers when possible
- Regularly update base images
- Scan images for vulnerabilities

### API Security
- Use strong JWT secrets in production
- Enable HTTPS/TLS for all communications
- Regularly rotate API keys and secrets
- Implement rate limiting

### Data Security
- Encrypt sensitive data at rest
- Use secure file upload validation
- Regularly backup your data
- Monitor access logs

### Infrastructure Security
- Keep all dependencies updated
- Use firewalls to restrict access
- Monitor system logs
- Implement proper access controls

## Known Security Considerations

### File Uploads
- OpenTranscribe processes user-uploaded audio/video files
- Files are validated for type and size
- Consider running in isolated environments for maximum security

### AI Model Security
- WhisperX models are downloaded from Hugging Face
- Verify model checksums when possible
- Keep models updated

### Database Security
- Use strong database passwords
- Limit database access to necessary services only
- Regularly backup database with encryption

## Security Features

### Core Security
- JWT-based authentication with secure token rotation
- Role-based access control (RBAC)
- File type validation
- Input sanitization
- CORS protection
- Rate limiting capabilities

### Authentication Methods

OpenTranscribe supports multiple authentication methods for different security requirements:

| Method | Description | Use Case |
|--------|-------------|----------|
| **Local** | bcrypt password hashing with SHA256 pre-hash | Default for standalone deployments |
| **LDAP/AD** | LDAPS with service account binding | Enterprise Active Directory integration |
| **OIDC/Keycloak** | OAuth 2.0 with PKCE flow | Single Sign-On, federated identity |
| **PKI/X.509** | Certificate-based authentication | Government systems (CAC/PIV) |

See detailed setup guides:
- [LDAP Authentication](LDAP_AUTH.md)
- [Keycloak/OIDC Setup](KEYCLOAK_SETUP.md)
- [PKI/Certificate Authentication](PKI_SETUP.md)

### Multi-Factor Authentication (MFA)

- **TOTP Support**: RFC 6238 compliant time-based one-time passwords
- **Backup Codes**: Emergency recovery codes (stored hashed)
- **Configurable Enforcement**: Can be required for specific roles or all users
- **Device Trust**: Remember trusted devices to reduce friction

### Password Security

**Password Policies:**
- Minimum length (configurable, default 12 characters)
- Complexity requirements (uppercase, lowercase, numbers, symbols)
- Password history (prevents reuse of last N passwords)
- Expiration policies (configurable, optional)
- Common password blacklist

**Implementation:**
- bcrypt_sha256 hashing (overcomes bcrypt's 72-byte limit)
- Automatic hash algorithm upgrade on login
- Secure password reset with time-limited tokens

### Account Lockout

- Configurable failed attempt threshold (default: 5 attempts)
- Progressive lockout duration
- Automatic unlock after timeout
- Admin override capability
- Lockout events logged for security monitoring

### Session Management

- Short-lived access tokens (configurable expiration)
- Refresh token rotation on use
- Secure token storage recommendations
- Session invalidation on password change
- Concurrent session limits (optional)

### Rate Limiting

Authentication endpoints are protected with rate limiting:
- Login attempts: Configurable per-IP and per-user limits
- Registration: Prevents mass account creation
- Password reset: Prevents enumeration attacks
- API endpoints: Configurable limits per endpoint

### Audit Logging

All authentication events are logged for security monitoring:
- Login attempts (success/failure)
- Password changes
- MFA enrollment/removal
- Account lockouts
- Session creation/termination
- Administrative actions

Log format supports integration with SIEM systems.

## FedRAMP Compliance Features

OpenTranscribe includes features to support FedRAMP compliance requirements:

### AC-8: System Use Notification
- Classification banners (configurable levels: UNCLASSIFIED, CUI, SECRET, TOP SECRET)
- System use notifications displayed before login
- Customizable banner text and colors

### IA-2: Identification and Authentication
- Multi-factor authentication (TOTP)
- PKI/CAC support for government systems
- Strong authentication for privileged users

### IA-5: Authenticator Management
- Password complexity policies
- Password history enforcement
- Authenticator feedback protection (no password hints)
- Password expiration policies

### AC-12: Session Termination
- Configurable session timeouts
- Automatic logout on inactivity
- Session termination on logout

### AU-2/AU-3: Audit Events
- Comprehensive audit logging
- Timestamp and user identification
- Event type and outcome recording
- Source IP address logging

For testing compliance features, see [TESTING_CHECKLIST.md](TESTING_CHECKLIST.md).

## Responsible Disclosure

We appreciate the security research community's efforts to improve OpenTranscribe's security. We're committed to working with researchers and will acknowledge their contributions (with their permission) in our security advisories.

Thank you for helping keep OpenTranscribe secure!
