# PKI/X.509 Certificate Authentication Setup

This guide covers setting up PKI (Public Key Infrastructure) certificate-based authentication with OpenTranscribe.

## Overview

PKI authentication allows users to authenticate using X.509 client certificates instead of passwords. This is commonly used in:
- Government and military environments (CAC/PIV cards)
- Enterprise environments with certificate-based security
- High-security deployments requiring mutual TLS

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│                 │     │                  │     │                 │
│  Client         │────▶│    Nginx         │────▶│  OpenTranscribe │
│  (with cert)    │     │  (mTLS termination)    │    Backend      │
│                 │     │                  │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                        │                       │
        │                        │                       │
   Client Cert            Extract DN/Cert         Validate & Auth
   Presented              Pass via Headers        Create User
```

1. Client presents X.509 certificate during TLS handshake
2. Nginx validates certificate against CA
3. Nginx extracts certificate info and passes via headers
4. Backend authenticates user based on certificate DN
5. User is created/updated in database

## Testing Options

| Method | Complexity | Use Case |
|--------|------------|----------|
| API Testing | Easy | Verify PKI logic works without browser |
| Browser Testing | Medium | Full end-to-end with certificate selection |
| Production | Advanced | Enterprise deployment with real CA |

---

## Quick Start: API Testing (No Browser)

For quick API testing without setting up HTTPS/mTLS:

### Step 1: Generate Test Certificates

```bash
# Generate test CA and client certificates
./scripts/pki/setup-test-pki.sh
```

This creates:
- Root CA at `scripts/pki/test-certs/ca/ca.crt`
- Client certificates for: testuser, admin, john.doe, jane.smith
- PKCS12 files for browser import (password: `changeit`)

### Step 2: Configure OpenTranscribe

```bash
# .env settings
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
# Get the DN from the certificate
ADMIN_DN=$(openssl x509 -in scripts/pki/test-certs/clients/admin.crt -noout -subject | sed 's/subject=//')

# Authenticate
curl -X POST http://localhost:5174/api/auth/pki/authenticate \
  -H "Content-Type: application/json" \
  -H "X-Client-Cert-DN: $ADMIN_DN"
```

This simulates what Nginx would do in production by passing the `X-Client-Cert-DN` header.

**Note:** API testing only verifies the backend PKI logic. For full browser-based testing with certificate selection prompts, see "Browser-Based PKI Testing" below.

### Step 4: Browser Testing (Requires Nginx mTLS)

For browser-based PKI login (clicking "Sign in with Certificate"), you need HTTPS with mutual TLS.

---

## Browser-Based PKI Testing (Quick Setup)

This is the easiest way to test PKI authentication with a real browser.

### Step 1: Generate Test Certificates (if not done)

```bash
./scripts/pki/setup-test-pki.sh
```

### Step 2: Enable PKI in `.env`

```bash
PKI_ENABLED=true
PKI_CA_CERT_PATH=/app/scripts/pki/test-certs/ca/ca.crt
PKI_VERIFY_REVOCATION=false
PKI_CERT_HEADER=X-Client-Cert
PKI_CERT_DN_HEADER=X-Client-Cert-DN
PKI_ADMIN_DNS=emailAddress=admin@example.com,CN=Admin User,OU=Users,O=OpenTranscribe Admins,L=Arlington,ST=Virginia,C=US
```

### Step 3: Start with PKI Overlay

**IMPORTANT:** PKI authentication requires production mode because it needs nginx with mTLS (mutual TLS) to verify client certificates. Dev mode uses Vite dev server which cannot handle client certificate verification.

**Recommended Method (using opentr.sh):**
```bash
# Production mode with PKI (test before push)
./opentr.sh start prod --build --with-pki

# Production mode with PKI (Docker Hub images)
./opentr.sh start prod --with-pki
```

**Advanced Method (manual docker compose):**
```bash
# Production mode with PKI (local images)
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.local.yml -f docker-compose.pki.yml up -d --build

# Production mode with PKI (local images)
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.local.yml -f docker-compose.pki.yml up -d --build
```

### Step 4: Import Certificate to Browser

Import one of the `.p12` files from `scripts/pki/test-certs/clients/`:

**macOS:**
```bash
# Import to keychain (password: changeit)
security import scripts/pki/test-certs/clients/admin.p12 -k ~/Library/Keychains/login.keychain-db -P changeit -A
```

Then in **Keychain Access**:
1. Find the private key under "Keys"
2. Right-click → Get Info → Access Control
3. Select "Allow all applications to access this item"
4. Save Changes

**Windows/Linux Chrome:**
1. Settings → Privacy and security → Security → Manage certificates
2. Import → Select `admin.p12`
3. Password: `changeit`

**Firefox:**
1. Settings → Privacy & Security → Certificates → View Certificates
2. Your Certificates → Import
3. Select `admin.p12`, password: `changeit`

### Step 5: Access via HTTPS

Open: **https://localhost:5182**

- Accept the self-signed certificate warning
- Click "Sign in with Certificate"
- Browser will prompt you to select a certificate
- Select the imported certificate
- You'll be authenticated!

### Available Test Users

| Certificate | Email | Role |
|-------------|-------|------|
| admin.p12 | admin@example.com | Admin |
| testuser.p12 | testuser@example.com | User |
| john.doe.p12 | john.doe@example.com | User |
| jane.smith.p12 | jane.smith@example.com | User |

Password for all `.p12` files: `changeit`

---

## Full Development Environment Setup (Alternative)

### Step 1: Start Step CA (Certificate Authority)

```bash
# Start Step CA for PKI testing
docker compose -f docker-compose.yml -f docker-compose.keycloak.yml --profile pki up -d step-ca

# View CA initialization logs
docker compose -f docker-compose.yml -f docker-compose.keycloak.yml logs step-ca
```

### Step 2: Initialize Step CA

```bash
# Get the CA fingerprint
docker exec step-ca step ca health
docker exec step-ca step ca bootstrap --ca-url https://localhost:9000 --fingerprint <fingerprint>
```

### Step 3: Generate Client Certificate

```bash
# Generate a client certificate
docker exec step-ca step ca certificate "user@example.com" user.crt user.key --not-after=8760h

# Copy certificates from container
docker cp step-ca:/home/step/user.crt ./certs/
docker cp step-ca:/home/step/user.key ./certs/

# Export as PKCS#12 for browser import
openssl pkcs12 -export -out user.p12 -inkey certs/user.key -in certs/user.crt
```

### Step 4: Configure Nginx for mTLS

Create or update Nginx configuration for mutual TLS:

```nginx
# /etc/nginx/conf.d/pki.conf

server {
    listen 443 ssl;
    server_name localhost;

    # Server certificate
    ssl_certificate /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;

    # Client certificate verification
    ssl_client_certificate /etc/nginx/certs/ca.crt;
    ssl_verify_client optional;  # 'required' for mandatory PKI
    ssl_verify_depth 2;

    # PKI authentication endpoint
    location /api/auth/pki {
        # Pass certificate info to backend
        proxy_set_header X-Client-Cert $ssl_client_escaped_cert;
        proxy_set_header X-Client-Cert-Verify $ssl_client_verify;
        proxy_set_header X-Client-Cert-DN $ssl_client_s_dn;

        proxy_pass http://backend:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Other API routes (no PKI required)
    location /api/ {
        proxy_pass http://backend:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Frontend
    location / {
        proxy_pass http://frontend:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Step 5: Configure OpenTranscribe

Add to your `.env` file:

```bash
# PKI/X.509 Configuration
PKI_ENABLED=true
PKI_CA_CERT_PATH=/etc/ssl/certs/ca.crt
PKI_VERIFY_REVOCATION=false
PKI_CERT_HEADER=X-Client-Cert
PKI_CERT_DN_HEADER=X-Client-Cert-DN
PKI_ADMIN_DNS=CN=Admin User,O=OpenTranscribe,C=US
```

### Step 6: Import Certificate to Browser

**Chrome/Edge (Windows/Linux):**
1. Settings → Privacy and security → Security → Manage certificates
2. Import → Select user.p12 file
3. Enter password: `changeit`

**Firefox:**
1. Settings → Privacy & Security → Certificates → View Certificates
2. Your Certificates → Import
3. Select user.p12 file, password: `changeit`

**macOS (Safari/Chrome):**
1. Import via terminal (recommended):
   ```bash
   security import admin.p12 -k ~/Library/Keychains/login.keychain-db -P changeit -A
   ```
2. Or double-click the .p12 file to open Keychain Access
3. **Important:** After import, open Keychain Access:
   - Find the private key under "Keys"
   - Right-click → Get Info → Access Control
   - Select **"Allow all applications to access this item"**
   - Click Save Changes
4. This prevents the browser from freezing on repeated keychain prompts

### Step 7: Test PKI Authentication

1. Open OpenTranscribe in your browser
2. Click "Sign in with Certificate"
3. Browser will prompt to select certificate
4. Select your imported certificate
5. You'll be authenticated and redirected

## Production Configuration

### Using Enterprise CA

For production, use your organization's Certificate Authority:

```bash
# .env for production
PKI_ENABLED=true
PKI_CA_CERT_PATH=/etc/ssl/certs/enterprise-ca.crt
PKI_VERIFY_REVOCATION=true
PKI_CERT_HEADER=X-Client-Cert
PKI_CERT_DN_HEADER=X-Client-Cert-DN
PKI_ADMIN_DNS=CN=Admin1,OU=IT,O=Company,C=US,CN=Admin2,OU=IT,O=Company,C=US
```

### Nginx Production Configuration

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;

    # Strong TLS configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # Server certificate
    ssl_certificate /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;

    # Client certificate verification
    ssl_client_certificate /etc/nginx/certs/ca-bundle.crt;
    ssl_verify_client optional_no_ca;  # Verify if provided
    ssl_verify_depth 4;

    # CRL checking (if enabled)
    # ssl_crl /etc/nginx/certs/ca.crl;

    location /api/auth/pki {
        # Only allow if client cert was verified
        if ($ssl_client_verify != SUCCESS) {
            return 403;
        }

        proxy_set_header X-Client-Cert $ssl_client_escaped_cert;
        proxy_set_header X-Client-Cert-Verify $ssl_client_verify;
        proxy_set_header X-Client-Cert-DN $ssl_client_s_dn;

        proxy_pass http://backend:8080;
    }
}
```

### Certificate Requirements

Client certificates should include:
- **Common Name (CN)**: User's full name
- **Email Address**: User's email (in subject or SAN)
- **Key Usage**: Digital Signature, Key Encipherment
- **Extended Key Usage**: TLS Web Client Authentication

Example certificate subject:
```
CN=John Doe,emailAddress=john.doe@company.com,OU=Engineering,O=Company Inc,C=US
```

## Admin Configuration

### Designating PKI Admins

Admins are designated by their certificate Distinguished Name (DN):

```bash
# Single admin
PKI_ADMIN_DNS=CN=John Doe,O=Company,C=US

# Multiple admins (comma-separated)
PKI_ADMIN_DNS=CN=John Doe,O=Company,C=US,CN=Jane Smith,O=Company,C=US
```

**Note**: DN must match exactly as it appears in the certificate.

### User Creation

When a user authenticates via PKI for the first time:
1. User is automatically created in the database
2. Email is extracted from certificate (or generated from CN if not present)
3. Full name is extracted from CN
4. Role is set based on PKI_ADMIN_DNS match

## Smart Card / CAC / PIV Support

For DoD CAC or PIV card authentication:

1. Ensure card reader drivers are installed
2. Browser must have PKCS#11 module configured
3. Insert smart card before navigating to login page
4. Select certificate when prompted

### Chrome CAC Setup (Linux)

```bash
# Install OpenSC
sudo apt install opensc opensc-pkcs11

# Configure Chrome to use PKCS#11
# Settings → Privacy → Security → Manage certificates → Security Devices
# Add: /usr/lib/x86_64-linux-gnu/opensc-pkcs11.so
```

### Firefox CAC Setup

```bash
# Settings → Privacy & Security → Certificates → Security Devices
# Load module: /usr/lib/x86_64-linux-gnu/opensc-pkcs11.so
```

## Troubleshooting

### Common Issues

**"PKI authentication is not enabled"**
- Ensure `PKI_ENABLED=true` in `.env`
- Restart backend after configuration changes

**"Invalid or missing client certificate"**
- Verify certificate is imported in browser
- Check Nginx is passing headers correctly
- Verify certificate is not expired

**"Certificate not accepted"**
- Verify CA certificate matches issuer
- Check certificate validity dates
- Ensure certificate has correct key usage

### Debug Logging

Check Nginx logs for certificate verification:
```bash
# Nginx error log
tail -f /var/log/nginx/error.log

# Look for ssl_client_verify status
```

Check backend logs:
```bash
./opentr.sh logs backend
```

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

1. **CA Security**: Protect your CA private key
2. **Certificate Revocation**: Implement CRL or OCSP checking
3. **Certificate Lifecycle**: Plan for certificate renewal
4. **Key Storage**: Use hardware tokens for high-security environments
5. **DN Validation**: Ensure DN matching is case-sensitive and exact

## Certificate Revocation (Optional)

Enable CRL checking:

```bash
# .env
PKI_VERIFY_REVOCATION=true
```

Nginx CRL configuration:
```nginx
ssl_crl /etc/nginx/certs/ca.crl;
```

Generate CRL:
```bash
# Using Step CA
step ca crl > ca.crl

# Using OpenSSL
openssl ca -gencrl -out ca.crl -config openssl.cnf
```
