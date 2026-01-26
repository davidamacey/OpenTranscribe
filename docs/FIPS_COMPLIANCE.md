# FIPS 140-2 Compliance Guide

This guide explains how to deploy OpenTranscribe in a FIPS 140-2 compliant configuration for government and high-security environments.

## Overview

FIPS 140-2 (Federal Information Processing Standard) is a U.S. government security standard that specifies requirements for cryptographic modules. There are two levels of FIPS compliance:

| Level | Description | When Required |
|-------|-------------|---------------|
| **FIPS-Approved Algorithms** | Uses algorithms on the FIPS 140-2 approved list | FedRAMP Moderate, most government systems |
| **FIPS 140-2 Validated** | Uses certified cryptographic modules | FedRAMP High, DoD IL4+, classified systems |

## Current Implementation (FIPS-Approved Algorithms)

OpenTranscribe already supports FIPS-approved algorithms with a simple configuration change:

```bash
# .env
FIPS_MODE=true
PBKDF2_ITERATIONS=210000
```

**What this enables:**
- Password hashing uses PBKDF2-SHA256 (NIST SP 800-132)
- Automatic migration of existing bcrypt hashes on user login
- 210,000 iterations (OWASP 2023 recommendation)

**No additional installation required** - the `passlib` library includes pure Python implementations.

---

## Full FIPS 140-2 Validated Deployment

For environments requiring FIPS 140-2 validated cryptographic modules (FedRAMP High, DoD IL4+), additional configuration is needed at the host and container levels.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     FIPS Boundary                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                   Host System                         │  │
│  │  - RHEL/Rocky Linux with FIPS mode enabled           │  │
│  │  - FIPS-validated kernel crypto modules              │  │
│  │  - System crypto policy set to FIPS                  │  │
│  │                                                       │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │              Container Runtime                  │  │  │
│  │  │  - Inherits FIPS mode from host                │  │  │
│  │  │  - UBI 9 base image (FIPS-enabled)             │  │  │
│  │  │  - OpenSSL 3.x with FIPS provider              │  │  │
│  │  │                                                 │  │  │
│  │  │  ┌───────────────────────────────────────────┐  │  │  │
│  │  │  │         OpenTranscribe App               │  │  │  │
│  │  │  │  - FIPS_MODE=true                        │  │  │  │
│  │  │  │  - Python using system OpenSSL           │  │  │  │
│  │  │  │  - PBKDF2-SHA256 password hashing        │  │  │  │
│  │  │  └───────────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Step 1: Configure Host System

### Prerequisites

- RHEL 8/9, Rocky Linux 8/9, or CentOS Stream 8/9
- Root or sudo access
- System reboot capability

### Enable FIPS Mode on Host

```bash
# Install FIPS packages
sudo dnf install -y \
    dracut-fips \
    openssl \
    crypto-policies \
    crypto-policies-scripts

# Enable FIPS mode (requires reboot)
sudo fips-mode-setup --enable

# Reboot the system
sudo reboot
```

### Verify FIPS Mode After Reboot

```bash
# Check FIPS status
fips-mode-setup --check
# Expected output: "FIPS mode is enabled."

# Verify kernel parameter
cat /proc/sys/crypto/fips_enabled
# Expected output: 1

# Check crypto policy
update-crypto-policies --show
# Expected output: FIPS
```

### Set System-Wide Crypto Policy

```bash
# Set FIPS crypto policy (restricts to FIPS-approved algorithms)
sudo update-crypto-policies --set FIPS

# Verify
update-crypto-policies --show
```

---

## Step 2: Update Container Base Images

### Option A: Red Hat Universal Base Image (Recommended)

Update `backend/Dockerfile.prod`:

```dockerfile
# Use Red Hat UBI 9 with Python 3.11
FROM registry.access.redhat.com/ubi9/python-311:latest

# Set environment for FIPS
ENV OPENSSL_FIPS=1

# Rest of your Dockerfile...
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ... rest of configuration
```

### Option B: Debian/Ubuntu with OpenSSL 3.x FIPS Provider

If you must use Debian-based images:

```dockerfile
FROM python:3.11-slim-bookworm

# Install OpenSSL 3.x (has FIPS provider)
RUN apt-get update && apt-get install -y \
    openssl \
    libssl3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Configure OpenSSL FIPS provider
RUN mkdir -p /etc/ssl && \
    cat > /etc/ssl/openssl.cnf << 'EOF'
openssl_conf = openssl_init

[openssl_init]
providers = provider_sect
alg_section = algorithm_sect

[provider_sect]
fips = fips_sect
base = base_sect

[fips_sect]
activate = 1

[base_sect]
activate = 1

[algorithm_sect]
default_properties = fips=yes
EOF

# Set environment
ENV OPENSSL_FIPS=1
ENV OPENSSL_CONF=/etc/ssl/openssl.cnf

# Rest of your Dockerfile...
```

### Frontend Nginx Container

Update `frontend/Dockerfile.prod`:

```dockerfile
# Use UBI 9 with nginx
FROM registry.access.redhat.com/ubi9/nginx-122:latest

# Or for Debian with OpenSSL 3.x
FROM nginx:1.25-bookworm

# Nginx will use system OpenSSL for TLS
```

---

## Step 3: Create Docker Compose FIPS Overlay

Create `docker-compose.fips.yml`:

```yaml
# FIPS 140-2 Compliance Overlay
# Usage: docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.fips.yml up -d

version: '3.8'

services:
  backend:
    environment:
      # Enable application FIPS mode
      - FIPS_MODE=true
      - OPENSSL_FIPS=1
      - PBKDF2_ITERATIONS=210000
    volumes:
      # Mount host FIPS status (read-only verification)
      - /proc/sys/crypto/fips_enabled:/host/fips_enabled:ro
    security_opt:
      # May be needed for some FIPS crypto operations
      - seccomp:unconfined
    healthcheck:
      test: ["CMD", "python", "-c", "import hashlib; hashlib.sha256(b'test')"]
      interval: 30s
      timeout: 10s
      retries: 3

  celery-worker:
    environment:
      - FIPS_MODE=true
      - OPENSSL_FIPS=1
      - PBKDF2_ITERATIONS=210000
    volumes:
      - /proc/sys/crypto/fips_enabled:/host/fips_enabled:ro
    security_opt:
      - seccomp:unconfined

  celery-worker-gpu:
    environment:
      - FIPS_MODE=true
      - OPENSSL_FIPS=1
      - PBKDF2_ITERATIONS=210000
    volumes:
      - /proc/sys/crypto/fips_enabled:/host/fips_enabled:ro
    security_opt:
      - seccomp:unconfined

  frontend:
    # Nginx inherits FIPS from host for TLS operations
    volumes:
      - /proc/sys/crypto/fips_enabled:/host/fips_enabled:ro

  postgres:
    # PostgreSQL should use FIPS-approved TLS
    environment:
      - PGSSLMODE=verify-full
    command: >
      postgres
      -c ssl=on
      -c ssl_min_protocol_version=TLSv1.2
      -c ssl_ciphers=ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384

  redis:
    # Redis TLS configuration
    command: >
      redis-server
      --tls-port 6379
      --port 0
      --tls-cert-file /tls/redis.crt
      --tls-key-file /tls/redis.key
      --tls-ca-cert-file /tls/ca.crt
      --tls-protocols "TLSv1.2 TLSv1.3"
```

---

## Step 4: Update Application Configuration

### Environment Variables

Add to `.env` for FIPS deployment:

```bash
# ============================================================================
# FIPS 140-2 COMPLIANCE SETTINGS
# ============================================================================

# Enable FIPS-approved algorithms in application
FIPS_MODE=true

# PBKDF2 iterations (OWASP 2023 recommendation)
PBKDF2_ITERATIONS=210000

# Force TLS 1.2+ for all connections
MINIO_SECURE=true
OPENSEARCH_VERIFY_CERTS=true
REDIS_SSL=true
DATABASE_SSL_MODE=verify-full

# Disable non-FIPS algorithms
# (Application enforces this when FIPS_MODE=true)
```

### Python Dependencies

Ensure `requirements.txt` uses compatible versions:

```
# Cryptography must be 41.0.0+ for OpenSSL 3.x FIPS provider support
cryptography>=41.0.0

# passlib uses hashlib which inherits FIPS from system OpenSSL
passlib[bcrypt]>=1.7.4

# PyJWT/python-jose for JWT tokens
python-jose[cryptography]>=3.3.0
```

---

## Step 5: Verification

### Create Verification Script

Create `scripts/verify-fips.sh`:

```bash
#!/bin/bash
# FIPS 140-2 Compliance Verification Script

set -e

echo "========================================"
echo "FIPS 140-2 Compliance Verification"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

echo "=== Host System Checks ==="

# Check host FIPS mode
if [ -f /proc/sys/crypto/fips_enabled ]; then
    FIPS_HOST=$(cat /proc/sys/crypto/fips_enabled)
    if [ "$FIPS_HOST" = "1" ]; then
        pass "Host FIPS mode: ENABLED"
    else
        fail "Host FIPS mode: DISABLED"
    fi
else
    warn "Cannot determine host FIPS status (not Linux or no access)"
fi

# Check crypto policy
if command -v update-crypto-policies &> /dev/null; then
    CRYPTO_POLICY=$(update-crypto-policies --show 2>/dev/null || echo "unknown")
    if [ "$CRYPTO_POLICY" = "FIPS" ]; then
        pass "Crypto policy: FIPS"
    else
        warn "Crypto policy: $CRYPTO_POLICY (should be FIPS)"
    fi
fi

echo ""
echo "=== Container Checks ==="

# Check backend container
echo "Checking backend container..."
docker compose exec -T backend python3 << 'PYTHON_SCRIPT'
import sys
import ssl
import hashlib
import os

print(f"  Python version: {sys.version.split()[0]}")
print(f"  OpenSSL version: {ssl.OPENSSL_VERSION}")

# Check FIPS environment
fips_env = os.environ.get('FIPS_MODE', 'false')
print(f"  FIPS_MODE env: {fips_env}")

# Check if FIPS algorithms work
errors = []
for algo in ['sha256', 'sha384', 'sha512']:
    try:
        h = hashlib.new(algo)
        h.update(b'test')
        h.hexdigest()
    except Exception as e:
        errors.append(f"{algo}: {e}")

if errors:
    print(f"  FIPS algorithms: FAILED")
    for e in errors:
        print(f"    - {e}")
    sys.exit(1)
else:
    print(f"  FIPS algorithms: OK (sha256, sha384, sha512)")

# Check if MD5 is blocked (strict FIPS indicator)
try:
    hashlib.md5(b'test', usedforsecurity=True)
    print(f"  MD5 (security): Available (FIPS not strictly enforced)")
except (ValueError, TypeError):
    print(f"  MD5 (security): Blocked (FIPS strictly enforced)")

# Check application config
try:
    from app.core.config import settings
    print(f"  App FIPS_MODE: {settings.FIPS_MODE}")
    print(f"  PBKDF2 iterations: {settings.PBKDF2_ITERATIONS}")
except Exception as e:
    print(f"  App config: Could not load ({e})")

sys.exit(0)
PYTHON_SCRIPT

if [ $? -eq 0 ]; then
    pass "Backend container FIPS checks"
else
    fail "Backend container FIPS checks"
fi

echo ""
echo "=== TLS Configuration Checks ==="

# Check TLS versions
check_tls() {
    local service=$1
    local host=$2
    local port=$3

    if command -v openssl &> /dev/null; then
        # Try TLS 1.2
        if echo | openssl s_client -connect ${host}:${port} -tls1_2 2>/dev/null | grep -q "Cipher is"; then
            pass "$service: TLS 1.2 supported"
        fi

        # Check for TLS 1.0/1.1 (should be disabled)
        if echo | openssl s_client -connect ${host}:${port} -tls1 2>/dev/null | grep -q "Cipher is"; then
            warn "$service: TLS 1.0 still enabled (should be disabled for FIPS)"
        fi
    fi
}

# Add TLS checks for your services as needed
# check_tls "nginx" "localhost" "443"

echo ""
echo "=== Summary ==="
echo "Review any FAIL or WARN items above."
echo "For full FIPS 140-2 validation, ensure:"
echo "  1. Host OS has FIPS mode enabled"
echo "  2. Crypto policy is set to FIPS"
echo "  3. Container base images are FIPS-enabled"
echo "  4. Application FIPS_MODE=true"
echo "  5. All TLS connections use TLS 1.2+"
echo ""
```

Make executable:
```bash
chmod +x scripts/verify-fips.sh
```

---

## Step 6: Deployment Commands

### Deploy with FIPS Overlay

```bash
# Development with FIPS
docker compose -f docker-compose.yml -f docker-compose.fips.yml up -d

# Production with FIPS
docker compose \
    -f docker-compose.yml \
    -f docker-compose.prod.yml \
    -f docker-compose.fips.yml \
    up -d

# Verify FIPS compliance
./scripts/verify-fips.sh
```

---

## FIPS-Approved Algorithms Reference

### Symmetric Encryption
| Algorithm | Key Size | Status |
|-----------|----------|--------|
| AES | 128, 192, 256 bits | Approved |
| 3DES | 168 bits | Deprecated (avoid) |

### Hash Functions
| Algorithm | Output Size | Status |
|-----------|-------------|--------|
| SHA-1 | 160 bits | Deprecated (signatures only) |
| SHA-224/256/384/512 | Various | Approved |
| SHA-3 | Various | Approved |
| MD5 | 128 bits | **NOT APPROVED** |

### Key Derivation
| Algorithm | Status |
|-----------|--------|
| PBKDF2 (SHA-256) | Approved |
| HKDF | Approved |
| bcrypt | **NOT APPROVED** (use PBKDF2) |
| scrypt | **NOT APPROVED** |
| Argon2 | **NOT APPROVED** |

### Digital Signatures
| Algorithm | Status |
|-----------|--------|
| RSA (2048+ bits) | Approved |
| ECDSA (P-256, P-384, P-521) | Approved |
| EdDSA | Not yet approved |

### TLS
| Version | Status |
|---------|--------|
| TLS 1.3 | Approved |
| TLS 1.2 | Approved |
| TLS 1.1 | **NOT APPROVED** |
| TLS 1.0 | **NOT APPROVED** |

---

## Troubleshooting

### "FIPS mode not enabled" in container

```bash
# Verify host FIPS mode
cat /proc/sys/crypto/fips_enabled

# If 0, enable on host first
sudo fips-mode-setup --enable
sudo reboot
```

### "Algorithm not available" errors

```bash
# Check if using FIPS-approved algorithm
# Replace MD5/SHA1 with SHA-256+
# Replace bcrypt with PBKDF2
```

### Performance degradation

PBKDF2 with 210,000 iterations is slower than bcrypt. This is expected and necessary for FIPS compliance. Consider:
- Caching authentication tokens (already implemented)
- Using session cookies for repeat requests
- Async password verification

### Container image compatibility

```bash
# Test image FIPS support
docker run --rm registry.access.redhat.com/ubi9/python-311:latest \
    python3 -c "import hashlib; print(hashlib.algorithms_available)"
```

---

## Compliance Checklist

- [ ] Host OS FIPS mode enabled (`fips-mode-setup --enable`)
- [ ] Crypto policy set to FIPS (`update-crypto-policies --set FIPS`)
- [ ] Container base images are FIPS-enabled (UBI 9 or similar)
- [ ] `FIPS_MODE=true` in application `.env`
- [ ] `PBKDF2_ITERATIONS=210000` or higher
- [ ] TLS 1.2+ enforced for all connections
- [ ] MD5 and SHA-1 not used for security purposes
- [ ] bcrypt passwords migrated to PBKDF2-SHA256
- [ ] Verification script passes all checks
- [ ] Documentation updated in System Security Plan (SSP)

---

## References

- [NIST FIPS 140-2](https://csrc.nist.gov/publications/detail/fips/140/2/final)
- [NIST SP 800-132 (PBKDF)](https://csrc.nist.gov/publications/detail/sp/800-132/final)
- [Red Hat FIPS Documentation](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/9/html/security_hardening/using-the-system-wide-cryptographic-policies_security-hardening)
- [OpenSSL 3.0 FIPS Provider](https://www.openssl.org/docs/man3.0/man7/fips_module.html)
- [FedRAMP Cryptographic Requirements](https://www.fedramp.gov/assets/resources/documents/FedRAMP_Security_Controls_Baseline.xlsx)
