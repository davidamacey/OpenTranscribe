---
sidebar_label: LDAP / Active Directory
sidebar_position: 2
---

# LDAP/Active Directory Authentication

## Overview

OpenTranscribe supports hybrid authentication combining LDAP/Active Directory with local database users:

- **LDAP users**: Auto-created on first login with role based on `LDAP_ADMIN_USERS`
- **Local admin users**: Created manually via registration endpoint with database passwords
- **Flexible auth**: System supports both email-based (local) and **username-based (LDAP)** login — users can log in with their sAMAccountName, uid, or any configured username attribute
- **Priority**: Local users checked first when `auth_type='local'` in database

> **v0.4.0 Change**: LDAP configuration is now managed via the Super Admin UI (Settings → Authentication → LDAP/Active Directory). Settings are stored encrypted (AES-256-GCM) in the database. Environment variables (`LDAP_SERVER`, `LDAP_BASE_DN`, etc.) continue to work as an initial seed fallback but database configuration takes precedence once saved.

## Configuration

### Primary Method: Super Admin UI (v0.4.0+)

Configure LDAP via the Admin UI for immediate, encrypted, restart-free configuration:

1. Log in as super_admin (`admin@example.com`)
2. Navigate to Settings → Authentication → LDAP/Active Directory
3. Click "Edit" and fill in all fields (see table in SUPER_ADMIN_GUIDE.md)
4. Click "Test Connection" to verify before saving
5. Click "Save Configuration"

Settings saved via the UI are encrypted with AES-256-GCM and take effect immediately.

### Environment Variables (Fallback / Initial Seed)

These variables are used only when no database configuration exists for LDAP. Once configuration is saved via the Admin UI, these env vars are ignored.

Add the following to your `.env` file:

```env
# Enable LDAP authentication
LDAP_ENABLED=true

# LDAP/AD Server
LDAP_SERVER=ldaps://your-ad-server.domain.com
LDAP_PORT=636
LDAP_USE_SSL=true
LDAP_USE_TLS=false

# Service account for LDAP search (read-only user)
LDAP_BIND_DN=CN=service-account,CN=Users,DC=domain,DC=com
LDAP_BIND_PASSWORD=your-service-account-password

# Search base and filter
LDAP_SEARCH_BASE=DC=domain,DC=com
LDAP_USERNAME_ATTR=sAMAccountName  # Username attribute (sAMAccountName, uid, etc.)
LDAP_USER_SEARCH_FILTER=({username_attr}={username})  # Uses LDAP_USERNAME_ATTR

# User attributes
LDAP_EMAIL_ATTR=mail
LDAP_NAME_ATTR=cn

# Timeout (seconds)
LDAP_TIMEOUT=10

# Optional: Comma-separated list of AD usernames that should be admins
LDAP_ADMIN_USERS=admin1,admin2,john.doe
```

### Configuration Details

- **LDAP_SERVER**: Full LDAP URL (ldaps:// for secure LDAP)
- **LDAP_PORT**: 389 for standard LDAP, 636 for LDAPS
- **LDAP_USE_SSL**: Enable LDAPS (recommended for production)
- **LDAP_USE_TLS**: Alternative to LDAPS (StartTLS)
- **LDAP_BIND_DN**: Distinguished Name of service account (must have read access to user objects)
- **LDAP_BIND_PASSWORD**: Password for service account (stored in .env)
- **LDAP_SEARCH_BASE**: Base DN for user searches (e.g., DC=domain,DC=com)
- **LDAP_USERNAME_ATTR**: Username attribute for user search (default: `sAMAccountName`)
  - Active Directory: `sAMAccountName`
  - OpenLDAP: `uid`
- **LDAP_USER_SEARCH_FILTER**: Filter to find users by username
  - Format: `({username_attr}={username})` where `{username_attr}` is replaced by `LDAP_USERNAME_ATTR`
  - Active Directory: `(sAMAccountName={username})`
  - OpenLDAP: `(uid={username})`
- **LDAP_EMAIL_ATTR**: Attribute containing user email (mail, userPrincipalName, etc.)
- **LDAP_NAME_ATTR**: Attribute containing full name (cn, displayName, etc.)
- **LDAP_ADMIN_USERS**: List of AD usernames that should automatically be admins

### Username Attribute Configuration

The `LDAP_USERNAME_ATTR` setting provides flexibility for different directory services:

**Active Directory (default):**
```env
LDAP_USERNAME_ATTR=sAMAccountName
LDAP_USER_SEARCH_FILTER=(sAMAccountName={username})
```

**OpenLDAP:**
```env
LDAP_USERNAME_ATTR=uid
LDAP_USER_SEARCH_FILTER=(uid={username})
```

**Custom Attribute:**
```env
LDAP_USERNAME_ATTR=employeeId
LDAP_USER_SEARCH_FILTER=(employeeId={username})
```

The system automatically replaces `{username_attr}` in `LDAP_USER_SEARCH_FILTER` with the value of `LDAP_USERNAME_ATTR`, allowing consistent filter configuration across different directory services.

## Authentication Flow

### Hybrid Authentication Strategy

The system uses a flexible authentication flow based on the user's `auth_type` in the database:

#### 1. Local User (Database Password)

```
User exists in DB + auth_type = 'local'
  → Try direct database authentication (bypasses ORM for reliability)
  → If direct fails, try ORM authentication
  → Success: Return JWT token
  → Failure: Try LDAP (as fallback if user exists)
```

#### 2. LDAP User

```
LDAP Enabled OR user not found locally
  → Bind to AD with service account
  → Search for user by LDAP_USERNAME_ATTR (or email if username contains @)
  → If not found by username, try search by email address
  → Extract email, username, and cn attributes
  → Bind as user to verify password
  → Create/update user in database
  → Return JWT token
```

#### 3. First-Time LDAP Login

```
User not in database
  → Authenticate via LDAP
  → Create user record:
    - email: from AD
    - full_name: from AD
    - ldap_uid: sAMAccountName
    - auth_type: 'ldap'
    - role: 'admin' if in LDAP_ADMIN_USERS else 'user'
  → Return JWT token
```

### Login Input Options

Users can login with:
- **Email address** (for local users, also supported for LDAP users)
- **Username/sAMAccountName** (for LDAP users)

The system automatically handles both formats:

```bash
# Local user login (email-based)
curl -X POST http://localhost:5174/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=local_password"

# LDAP user login (username-based)
curl -X POST http://localhost:5174/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=john.doe&password=ad_password"

# LDAP user login (email-based - extracts username before @)
curl -X POST http://localhost:5174/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=john.doe@example.com&password=ad_password"
```

## Security Features

### LDAP Injection Protection

The system escapes special characters in LDAP filter values to prevent injection attacks:

```python
_escaped_username = _escape_ldap_filter(username)
# Escapes: ( ) * \ NUL characters
```

### SSL/TLS

- **LDAPS** (LDAP over SSL) is recommended for production
- Use port 636 with `LDAP_USE_SSL=true`
- Ensure valid SSL certificate on AD server
- Test connection: `openssl s_client -connect ad-server:636`

### Password Change Restrictions

- **LDAP users cannot change passwords** in OpenTranscribe — changes must be done in AD/LDAP
- **Local users only** can change their password via the UI or API

## Deployment

### Development/Testing with LDAP Test Container

```bash
# Start OpenTranscribe with LDAP test container
./opentr.sh start dev --with-ldap-test
```

**Test Container Details:**
- LDAP server: `localhost:3890`
- Web UI: `http://localhost:17170`
- Admin credentials: `admin` / `admin_password`
- Base DN: `dc=example,dc=com`

### Production Deployment with Active Directory

1. Log in as super_admin
2. Go to Settings → Authentication → LDAP/Active Directory
3. Configure with your AD settings and click "Test Connection"
4. Click "Save Configuration" — changes take effect immediately

## Troubleshooting

### Common Errors

1. **"Failed to bind to LDAP server"** — Check LDAP_SERVER, LDAP_PORT, and service account credentials
2. **"User not found in LDAP"** — Verify LDAP_SEARCH_BASE and LDAP_USER_SEARCH_FILTER
3. **"User has no email attribute"** — Verify LDAP_EMAIL_ATTR is populated in AD
4. **"Authentication failed: user is LDAP type, cannot use password auth"** — User has `auth_type='ldap'`; use LDAP credentials, not local password
5. **"Password change not allowed for LDAP users"** — Change password in AD/LDAP directory directly

## Production Checklist

- [ ] LDAPS enabled with valid SSL certificate
- [ ] Read-only service account created
- [ ] LDAP config saved via Super Admin UI (Settings → Authentication → LDAP/AD)
- [ ] `LDAP_ADMIN_USERS` configured for admins
- [ ] `LDAP_USERNAME_ATTR` configured correctly for your directory
- [ ] Firewall allows outbound LDAP connections from backend container
- [ ] Test authentication with real AD users (username-based and email-based)
- [ ] Verify LDAP users cannot change passwords in UI or API
