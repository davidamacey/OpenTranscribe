# Authentication Deployment Guide

This guide provides quick-start commands for deploying OpenTranscribe with different authentication methods.

## Overview

OpenTranscribe supports four authentication methods:

| Method | Use Case | Test Container | Dev Mode | Prod Mode |
|--------|----------|----------------|----------|-----------|
| **Local** | Default username/password | N/A (built-in) | ✅ Yes | ✅ Yes |
| **LDAP/AD** | Enterprise directory integration | ✅ LLDAP | ✅ Yes | ✅ Yes |
| **Keycloak/OIDC** | SSO with external identity providers | ✅ Keycloak | ✅ Yes | ✅ Yes |
| **PKI/X.509** | Certificate-based (CAC/PIV cards) | ✅ Self-signed certs | ❌ No* | ✅ Yes |

*PKI requires nginx with mTLS for client certificate verification. Dev mode uses Vite dev server which cannot handle this.

## Quick Start Commands

### Development Mode

**IMPORTANT:** PKI authentication requires production mode (nginx with mTLS). It cannot work in dev mode which uses Vite dev server.

**Local Authentication Only (Default):**
```bash
./opentr.sh start dev
```

**With LDAP Test Container:**
```bash
./opentr.sh start dev --with-ldap-test
```

**With Keycloak Test Container:**
```bash
./opentr.sh start dev --with-keycloak-test
```

**LDAP + Keycloak Testing:**
```bash
./opentr.sh start dev --with-ldap-test --with-keycloak-test
```

### Production Mode

**Standard Production (Docker Hub images):**
```bash
./opentr.sh start prod
```

**Production with Local Build (Test Before Push):**
```bash
./opentr.sh start prod --build
```

**Production with PKI (HTTPS + Client Certificates):**
```bash
# PKI only works in production mode (requires nginx with mTLS)
./opentr.sh start prod --build --with-pki
```

**Production with All Auth Methods:**
```bash
# All test containers including PKI
./opentr.sh start prod --build --with-pki --with-ldap-test --with-keycloak-test
```

## Authentication Configuration

### Super Admin Account

OpenTranscribe always maintains a local super_admin account for emergency access and authentication configuration:

- **Username:** `admin@example.com`
- **Password:** `password` (change this immediately in production!)
- **Role:** `super_admin`
- **Purpose:** Configure authentication methods, manage users

**Why super_admin exists:**
- Configure LDAP/Keycloak/PKI settings via Admin UI
- "Break glass" account if external IdP systems fail
- Regular admins (from LDAP/Keycloak/PKI) cannot configure authentication settings

### Configuration Methods

1. **Admin UI (Recommended):**
   - Log in as super_admin
   - Navigate to Settings → Authentication
   - Configure LDAP, Keycloak, PKI, MFA settings
   - Database-backed configuration (persists across restarts)

2. **Environment Variables (.env file):**
   - Fallback if database not configured
   - Database configuration takes precedence
   - See `.env.example` for all options

## Test Container Details

### LLDAP Test Container

**Access:**
- LDAP server: `localhost:3890`
- Web UI: `http://localhost:17170`
- Admin credentials: `admin` / `admin_password`
- Base DN: `dc=example,dc=com`

**Test Users (create via Web UI or API):**
- Admin: `ldap-admin` / `LdapAdmin123`
- Regular: `ldap-user` / `LdapUser123`

**Configuration in OpenTranscribe:**
- Server: `lldap-test` (or `localhost` for external access)
- Port: `3890`
- Use SSL: `false`
- Bind DN: `uid=admin,ou=people,dc=example,dc=com`
- Bind Password: `admin_password`
- Search Base: `dc=example,dc=com`
- Username Attribute: `uid`
- Admin Users: `ldap-admin`

### Keycloak Test Container

**Access:**
- Keycloak URL: `http://localhost:8180`
- Admin console credentials: `admin` / `admin`
- Realm: `opentranscribe`

**Test Users (create via Admin Console):**
- Create users in the `opentranscribe` realm
- Assign roles: `user` or `admin`
- Set passwords (disable "Temporary" flag)

**Configuration in OpenTranscribe:**
- Server URL: `http://localhost:8180` (or `http://[server-ip]:8180` for LAN access)
- Internal URL: `http://transcribe-app-keycloak-1:8080`
- Realm: `opentranscribe`
- Client ID: `opentranscribe-app`
- Client Secret: (from Keycloak client Credentials tab)
- Callback URL: `http://localhost:5173/login` (FRONTEND page, not backend API!)
- Admin Role: `admin`

### PKI Test Certificates

**Location:** `scripts/pki/test-certs/clients/`

**Available Certificates:**
- `admin.p12` - Admin User (admin@example.com) - **Admin Role**
- `testuser.p12` - Test User (testuser@example.com) - **User Role**
- `john.doe.p12` - John Doe (john.doe@gov.example.com) - **User Role**
- `jane.smith.p12` - Jane Smith (jane.smith@gov.example.com) - **User Role**

**Password:** `changeit` (for all .p12 files)

**Browser Import:**
- **macOS:** Double-click .p12 file, enter password, imported to Keychain
- **Windows/Chrome:** Settings → Security → Manage certificates → Import
- **Firefox:** Settings → Certificates → Your Certificates → Import

**Access:** `https://localhost:5182` (or `https://[server-ip]:5182` for LAN access)

**Configuration in OpenTranscribe:**
- PKI Enabled: `true`
- CA Certificate Path: `/app/scripts/pki/test-certs/ca/ca.crt`
- Admin DNs: `emailAddress=admin@example.com,CN=Admin User,OU=Users,O=OpenTranscribe Admins,L=Arlington,ST=Virginia,C=US`

## Production Deployment

### With Enterprise Active Directory

```bash
# Start OpenTranscribe (no test containers)
./opentr.sh start prod --build

# Configure via Admin UI:
# Settings → Authentication → LDAP
# - Server: ldaps://your-ad-server.domain.com
# - Port: 636
# - Use SSL: true
# - Bind DN: CN=service-account,CN=Users,DC=domain,DC=com
# - Search Base: DC=domain,DC=com
# - Username Attribute: sAMAccountName
# - Admin Users: admin1,admin2,john.doe
```

### With Enterprise Keycloak

```bash
# Start OpenTranscribe (no test containers)
./opentr.sh start prod --build

# Configure via Admin UI:
# Settings → Authentication → Keycloak
# - Server URL: https://keycloak.yourdomain.com
# - Realm: your-realm
# - Client ID: opentranscribe-app
# - Client Secret: (from your Keycloak admin)
# - Callback URL: https://yourdomain.com/login
# - Admin Role: admin
```

### With Production PKI (CAC/PIV Cards)

```bash
# Start with PKI overlay
./opentr.sh start prod --build --with-pki

# Configure via Admin UI:
# Settings → Authentication → PKI
# - PKI Enabled: true
# - CA Certificate: (upload your organization's CA cert)
# - Admin DNs: (comma-separated list of admin certificate DNs)
# - Verify Revocation: true (in production)
# - CRL URL: https://your-ca.domain.com/crl
```

## Troubleshooting

### Common Issues

**LDAP: "Invalid credentials"**
- Verify bind DN and password are correct
- Test with `ldapsearch` from command line
- Check service account has read access to user objects

**Keycloak: Shows raw JSON instead of logging in**
- Callback URL must point to FRONTEND (`/login`), not backend API
- Update via Admin UI → Settings → Authentication → Keycloak

**Keycloak: Login page slow to load from remote device**
- Server URL must be accessible from user's browser
- Use server IP address instead of `localhost` for LAN access
- Update Keycloak client redirect URIs to include all access URLs

**PKI: Browser doesn't prompt for certificate**
- Verify certificate is imported to correct keychain/store
- Check browser settings allow client certificate prompts
- macOS: Set private key to "Allow all applications to access"

**PKI: "Certificate verification failed"**
- Ensure CA certificate is correctly configured in admin UI
- Verify client certificate was issued by the configured CA
- Check certificate is not expired or revoked

### Logs

```bash
# Backend authentication logs
docker compose logs -f backend | grep -i "auth\|ldap\|keycloak\|pki"

# LDAP container logs
docker compose logs -f lldap

# Keycloak container logs
docker compose logs -f keycloak
```

## Advanced Usage

### Manual Docker Compose (Without opentr.sh)

**Development with LDAP and Keycloak:**
```bash
docker compose -f docker-compose.yml \
  -f docker-compose.ldap-test.yml \
  -f docker-compose.keycloak.yml \
  up -d --build
```

**Production with PKI (requires nginx + mTLS):**
```bash
docker compose -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.local.yml \
  -f docker-compose.pki.yml \
  up -d --build
```

**Production with all test containers:**
```bash
docker compose -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.local.yml \
  -f docker-compose.pki.yml \
  -f docker-compose.ldap-test.yml \
  -f docker-compose.keycloak.yml \
  up -d --build
```

### Hybrid Authentication

Enable multiple methods simultaneously:

```bash
# Development: LDAP + Keycloak (no PKI)
./opentr.sh start dev --with-ldap-test --with-keycloak-test

# Production: All auth methods including PKI
./opentr.sh start prod --build --with-pki --with-ldap-test --with-keycloak-test

# Configure via Admin UI:
# Settings → Authentication
# - Enable: Local, LDAP, Keycloak, PKI
```

Users can then choose their login method on the login page.

**Note:** PKI requires production mode because dev mode uses Vite dev server which cannot handle client certificate verification (mTLS).

### Reset and Test Each Method

Systematically test each authentication method:

```bash
# Test 1: Local only
./opentr.sh reset dev
# Disable all except local in Admin UI
# Test: admin@example.com / password

# Test 2: LDAP only
./opentr.sh reset dev --with-ldap-test
# Enable LDAP, disable others in Admin UI
# Test: ldap-admin / LdapAdmin123

# Test 3: Keycloak only
./opentr.sh reset dev --with-keycloak-test
# Enable Keycloak, disable others in Admin UI
# Test: (Keycloak user) / (password)

# Test 4: PKI only (REQUIRES PRODUCTION MODE)
./opentr.sh reset prod --build --with-pki
# Enable PKI, disable others in Admin UI
# Test: Import admin.p12, access https://localhost:5182
# Note: PKI requires nginx with mTLS, cannot use dev mode
```

## Documentation References

- **PKI Detailed Setup:** `docs/PKI_SETUP.md`
- **LDAP/AD Detailed Setup:** `docs/LDAP_AUTH.md`
- **Keycloak Detailed Setup:** `docs/KEYCLOAK_SETUP.md`
- **Development Guide:** `CLAUDE.md`
- **Environment Variables:** `.env.example`
