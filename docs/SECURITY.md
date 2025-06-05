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

- JWT-based authentication
- Role-based access control (RBAC)
- File type validation
- Input sanitization
- CORS protection
- Rate limiting capabilities

## Responsible Disclosure

We appreciate the security research community's efforts to improve OpenTranscribe's security. We're committed to working with researchers and will acknowledge their contributions (with their permission) in our security advisories.

Thank you for helping keep OpenTranscribe secure!