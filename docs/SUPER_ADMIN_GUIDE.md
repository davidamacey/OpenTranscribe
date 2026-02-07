# Super Admin Guide

This guide covers the super admin role and authentication configuration management in OpenTranscribe.

## Overview

The **super admin** role provides full system access including:
- Authentication method configuration (LDAP, Keycloak, PKI)
- User account management (lock/unlock, password reset, MFA reset)
- Session management (view/terminate user sessions)
- Audit log access and export
- Role management (promote users to admin/super_admin)

## Accessing Super Admin Features

### First-Time Setup

Bootstrap the first super admin using one of these methods:

**Option 1: Environment Variable**
```bash
BOOTSTRAP_SUPER_ADMIN_EMAIL=admin@example.com
```
The first user with this email will automatically be assigned super_admin role.

**Option 2: Manual Database Update**
```sql
UPDATE "user" SET role = 'super_admin' WHERE email = 'admin@example.com';
```

### Role Hierarchy

| Role | Permissions |
|------|-------------|
| `user` | Standard access to transcription features |
| `admin` | User management, system statistics, task monitoring |
| `super_admin` | All admin permissions + auth configuration + audit logs |

## Authentication Configuration

### Accessing Settings

1. Log in as super admin
2. Click Settings (gear icon)
3. Select "Authentication" tab

### Available Configuration Categories

#### Local Authentication
- Password policy (length, complexity, history)
- MFA settings (enable/require)
- Session timeouts

#### LDAP/Active Directory
- Server connection (host, port, SSL/TLS)
- Bind credentials
- Search base and attribute mappings
- Admin users/groups configuration

#### OIDC/Keycloak
- Server URL and realm
- Client ID and secret
- PKCE and audience settings
- Admin role mapping

#### PKI/Certificate
- CA certificate path
- Revocation checking (OCSP/CRL)
- Admin DNs configuration
- Certificate headers

#### Sessions
- Access token expiration
- Refresh token expiration
- Idle and absolute timeouts
- Concurrent session limits

### Testing Connections

Before saving LDAP or Keycloak configuration:
1. Fill in all required fields
2. Click "Test Connection"
3. Verify successful connection message
4. Save configuration

### Configuration Audit

All configuration changes are logged with:
- Who made the change
- When it was made
- What was changed (values masked for sensitive fields)
- IP address and user agent

View audit logs in Settings > Authentication > Audit Log tab.

## Account Management

### User Search

Navigate to Settings > Users to search and filter users by:
- Email or name
- Role (user, admin, super_admin)
- Authentication type (local, ldap, keycloak, pki)
- Account status (active, inactive)

### Account Actions

| Action | Description | Required Role |
|--------|-------------|---------------|
| Reset Password | Set new password, optionally force change | super_admin |
| Lock Account | Disable account with reason | admin |
| Unlock Account | Re-enable locked account | admin |
| Terminate Sessions | Force logout from all devices | admin |
| Reset MFA | Remove TOTP configuration | super_admin |
| Change Role | Promote/demote user role | super_admin |

### Viewing User Sessions

1. Click user row in table
2. Select "View Sessions"
3. See all active sessions with:
   - Device/browser info
   - IP address
   - Session start time
   - Last activity

### Terminating Sessions

To force logout a user:
1. Select user
2. Click "Terminate All Sessions"
3. Confirm action

User's refresh tokens are revoked and they must re-authenticate.

## Audit Log Management

### Viewing Logs

Super admins can access audit logs at Settings > Audit Logs:

- Filter by date range
- Filter by event type
- Filter by outcome (success/failure)
- Search by user

### Event Types

| Event Type | Description |
|------------|-------------|
| AUTH_LOGIN_SUCCESS | Successful login |
| AUTH_LOGIN_FAILURE | Failed login attempt |
| AUTH_LOGOUT | User logout |
| AUTH_MFA_SETUP | MFA enabled |
| AUTH_MFA_VERIFY | MFA verification |
| AUTH_PASSWORD_CHANGE | Password changed |
| AUTH_ACCOUNT_LOCKOUT | Account locked |
| AUTH_ACCOUNT_UNLOCK | Account unlocked |
| ADMIN_USER_CREATE | New user created |
| ADMIN_ROLE_CHANGE | User role changed |
| ADMIN_SETTINGS_CHANGE | Auth settings modified |

### Exporting Logs

Export audit logs for compliance:
1. Set date range filter
2. Click "Export CSV" or "Export JSON"
3. Download file

## Reports

### Account Status Dashboard

View summary statistics:
- Total users
- Active vs inactive
- MFA adoption rate
- Password expiration status

### Failed Login Report

Monitor security events:
- Failed attempts by user
- Failed attempts by IP
- Lockout events
- Suspicious patterns

## Best Practices

### Security
- Limit super_admin accounts to essential personnel
- Use strong, unique passwords
- Enable MFA for all admin accounts
- Review audit logs regularly
- Monitor failed login attempts

### Configuration
- Test auth method connections before saving
- Document configuration changes
- Keep .env as backup for critical settings
- Use descriptive audit comments

### Incident Response
- Know how to lock accounts quickly
- Have process for password reset requests
- Maintain audit log exports for compliance
- Document security incidents
