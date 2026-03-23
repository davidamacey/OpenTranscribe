---
sidebar_label: PKI / X.509 Certificates
sidebar_position: 4
---

# PKI/X.509 Certificate Authentication Setup

This guide covers setting up PKI (Public Key Infrastructure) certificate-based authentication with OpenTranscribe.

## Overview

PKI authentication allows users to authenticate using X.509 client certificates instead of passwords. This is commonly used in:
- Government and military environments (CAC/PIV cards)
- Enterprise environments with certificate-based security
- High-security deployments requiring mutual TLS

> **v0.4.0 Change**: PKI configuration is now managed via the Super Admin UI (Settings → Authentication → PKI/X.509). Settings are stored encrypted (AES-256-GCM) in the database. Environment variables continue to work as a fallback seed.
>
> **OCSP/CRL**: v0.4.0 adds OCSP and CRL checking. Configure via Admin UI for real-time or periodic revocation checking.
>
> **Super admin password fallback**: Even when PKI is the only enabled auth method, the super admin account can always authenticate with a password. This ensures emergency access if PKI infrastructure fails.

## How It Works

```
 Client (with cert)  ────▶  Nginx (mTLS termination)  ────▶  OpenTranscribe Backend
         │                          │                                    │
    Client Cert               Extract DN/Cert                   Validate & Auth
    Presented                 Pass via Headers                  Create User
```

1. Client presents X.509 certificate during TLS handshake
2. Nginx validates certificate against CA
3. Nginx extracts certificate info and passes via headers
4. Backend authenticates user based on certificate DN
5. User is created/updated in database

## Quick Start: API Testing (No Browser)

### Step 1: Generate Test Certificates

```bash
./scripts/pki/setup-test-pki.sh
```

This creates:
- Root CA at `scripts/pki/test-certs/ca/ca.crt`
- Client certificates for: testuser, admin, john.doe, jane.smith
- PKCS12 files for browser import (password: `changeit`)

### Step 2: Configure OpenTranscribe

```bash
PKI_ENABLED=true
PKI_CA_CERT_PATH=/mnt/nvm/repos/transcribe-app/scripts/pki/test-certs/ca/ca.crt
PKI_VERIFY_REVOCATION=false
PKI_CERT_HEADER=X-Client-Cert
PKI_CERT_DN_HEADER=X-Client-Cert-DN
PKI_ADMIN_DNS=emailAddress=admin@example.com,CN=Admin User,OU=Users,O=OpenTranscribe Admins,L=Arlington,ST=Virginia,C=US
```

### Step 3: Test via API

```bash
# Using the test script
./scripts/pki/test-pki-auth.sh admin      # Gets admin role
./scripts/pki/test-pki-auth.sh testuser   # Gets user role

# Or manually with curl (simulates what Nginx does)
ADMIN_DN=$(openssl x509 -in scripts/pki/test-certs/clients/admin.crt -noout -subject | sed 's/subject=//')

curl -X POST http://localhost:5174/api/auth/pki/authenticate \
  -H "Content-Type: application/json" \
  -H "X-Client-Cert-DN: $ADMIN_DN"
```

## Browser-Based PKI Testing (Requires Nginx mTLS)

**IMPORTANT:** PKI authentication requires production mode (`--with-pki`) because it needs nginx with mTLS to verify client certificates. Dev mode (Vite dev server) cannot handle client certificate verification.

### Step 1: Generate Test Certificates

```bash
./scripts/pki/setup-test-pki.sh
```

### Step 2: Enable PKI

**Admin UI (recommended):**
1. Log in as super_admin
2. Navigate to Settings → Authentication → PKI/X.509
3. Enable PKI, set CA Certificate Path, optionally configure OCSP/CRL

**Environment variables (fallback):**
```bash
PKI_ENABLED=true
PKI_CA_CERT_PATH=/app/scripts/pki/test-certs/ca/ca.crt
PKI_VERIFY_REVOCATION=false
PKI_CERT_HEADER=X-Client-Cert
PKI_CERT_DN_HEADER=X-Client-Cert-DN
PKI_ADMIN_DNS=emailAddress=admin@example.com,CN=Admin User,OU=Users,O=OpenTranscribe Admins,L=Arlington,ST=Virginia,C=US
```

### Step 3: Start with PKI Overlay

```bash
# Production mode with PKI (test before push)
./opentr.sh start prod --build --with-pki

# Production mode with PKI (Docker Hub images)
./opentr.sh start prod --with-pki
```

### Step 4: Import Certificate to Browser

Import one of the `.p12` files from `scripts/pki/test-certs/clients/`:

**macOS:**
```bash
security import scripts/pki/test-certs/clients/admin.p12 -k ~/Library/Keychains/login.keychain-db -P changeit -A
```

Then in **Keychain Access**: find the private key → Right-click → Get Info → Access Control → "Allow all applications to access this item"

**Windows/Linux Chrome:**
Settings → Privacy and security → Security → Manage certificates → Import → Select `admin.p12` → Password: `changeit`

**Firefox:**
Settings → Privacy & Security → Certificates → View Certificates → Your Certificates → Import

### Step 5: Access via HTTPS

Open: **https://localhost:5182**

- Accept the self-signed certificate warning
- Click "Sign in with Certificate"
- Browser will prompt you to select a certificate
- Select the imported certificate

### Available Test Users

| Certificate | Email | Role |
|-------------|-------|------|
| admin.p12 | admin@example.com | Admin |
| testuser.p12 | testuser@example.com | User |
| john.doe.p12 | john.doe@example.com | User |
| jane.smith.p12 | jane.smith@example.com | User |

Password for all `.p12` files: `changeit`

## Production Configuration

### Using Enterprise CA

Configure via the Admin UI (Settings → Authentication → PKI/X.509) for encrypted storage:

```bash
PKI_ENABLED=true
PKI_CA_CERT_PATH=/etc/ssl/certs/enterprise-ca.crt
PKI_VERIFY_REVOCATION=true
PKI_CERT_HEADER=X-Client-Cert
PKI_CERT_DN_HEADER=X-Client-Cert-DN
PKI_ADMIN_DNS=CN=Admin1,OU=IT,O=Company,C=US|CN=Admin2,OU=IT,O=Company,C=US
```

### OCSP Revocation Checking (Recommended)

OCSP provides real-time certificate revocation status:

| Setting | Description | Example |
|---------|-------------|---------|
| **Enable OCSP** | Turn on OCSP checking | `true` |
| **OCSP Responder URL** | Your CA's OCSP endpoint | `http://ocsp.pki.company.com` |

Configure via Admin UI: Settings → Authentication → PKI/X.509 → Enable OCSP.

### CRL Revocation Checking (Alternative)

CRL downloads and caches a list of revoked certificates, refreshed periodically:

| Setting | Description | Default |
|---------|-------------|---------|
| **Enable CRL** | Turn on CRL checking | `false` |
| **CRL Endpoint URL** | CRL distribution point | `http://pki.company.com/crl` |
| **CRL Refresh Hours** | How often to refresh | `24` |

**OCSP vs CRL:**
- OCSP: Real-time check on every login — revocation takes effect immediately
- CRL: Periodic check — revocation takes effect within the refresh interval (up to 24 hours)
- Both can be enabled simultaneously for defence-in-depth

## Smart Card / CAC / PIV Support

For DoD CAC or PIV card authentication:

1. Ensure card reader drivers are installed
2. Browser must have PKCS#11 module configured
3. Insert smart card before navigating to login page

```bash
# Chrome CAC setup (Linux)
sudo apt install opensc opensc-pkcs11
# Settings → Privacy → Security → Manage certificates → Security Devices
# Add: /usr/lib/x86_64-linux-gnu/opensc-pkcs11.so
```

## Troubleshooting

**"PKI authentication is not enabled"**
- Verify PKI is enabled in Settings → Authentication → PKI/X.509
- Database config takes precedence — an explicit `enabled=false` overrides .env

**"Invalid or missing client certificate"**
- Verify certificate is imported in browser
- Check Nginx is passing headers correctly
- Verify certificate is not expired

**"Certificate not accepted"**
- Verify CA certificate matches issuer
- Check certificate validity dates
- Ensure certificate has correct key usage extensions

### Verify Certificate Chain

```bash
# Verify certificate against CA
openssl verify -CAfile ca.crt user.crt

# View certificate details
openssl x509 -in user.crt -text -noout

# Check certificate DN format
openssl x509 -in user.crt -subject -noout
```

## Security Considerations

1. **CA Security**: Protect your CA private key — compromise of the CA allows issuing fraudulent certificates
2. **Certificate Revocation**: Enable OCSP or CRL checking in production
3. **Certificate Lifecycle**: Plan for certificate renewal before expiry
4. **Key Storage**: Use hardware tokens (CAC, PIV, YubiKey) for high-security environments
5. **DN Validation**: DN matching is case-sensitive and exact — copy DN strings directly from certificate details
6. **Super Admin Fallback**: Ensure the super admin password is documented in a secure location; it is the only non-PKI access path when PKI-only mode is active
7. **mTLS Requirement**: PKI authentication requires NGINX with mTLS (`--with-pki` flag); dev mode cannot use PKI
