# Security Advisory - OpenTranscribe

**Last Updated**: 2025-10-27

## Overview

This document provides transparency about known security vulnerabilities in OpenTranscribe's container images and explains their actual risk to the application.

---

## Current Known Vulnerabilities

### CVE-2025-47917 - Mbed TLS Use-After-Free (CRITICAL - Low Risk)

**Status**: ACCEPTED RISK - Monitoring for Debian 12 patch

**Details:**
- **Package**: libmbedcrypto7 version 2.28.3-1 (Debian 12 Bookworm system package)
- **CVSS Score**: 9.8 (Critical)
- **Reported**: June 2025
- **Vulnerable Function**: `mbedtls_x509_string_to_names()`
- **Attack Vector**: Requires calling X.509 certificate parsing functions with malicious input

**Why This is Low Risk for OpenTranscribe:**

1. **Not a Direct Dependency**
   - libmbedcrypto7 is a system library pulled in transitively by `curl` or other system utilities
   - OpenTranscribe does not directly use Mbed TLS in any capacity

2. **No Attack Surface**
   - The vulnerable function `mbedtls_x509_string_to_names()` is used for X.509 certificate generation/parsing
   - OpenTranscribe does NOT perform any of the following operations:
     - X.509 certificate generation
     - Custom certificate parsing
     - Certificate request creation
     - Subject Alternative Name (SAN) processing

3. **Application Usage Pattern**
   - OpenTranscribe uses HTTPS/TLS only through standard Python libraries (`requests`, `urllib3`)
   - These libraries use OpenSSL, not Mbed TLS, for TLS operations
   - The application performs: audio transcription, file storage, database operations
   - No certificate manipulation occurs in the application code

4. **Exploitation Requirements**
   - Attacker would need to:
     - Find a code path that calls `mbedtls_x509_string_to_names()`
     - Provide malicious certificate data to that function
     - Trigger specific memory corruption conditions
   - None of these conditions exist in OpenTranscribe's codebase

**Mitigation Status:**

- **Debian 12 (Bookworm)**: Patch submitted, awaiting official release
  - Tracking: https://security-tracker.debian.org/tracker/CVE-2025-47917
  - Merge Request: https://salsa.debian.org/debian-iot-team/mbedtls/-/merge_requests/6

- **Debian 11 (Bullseye)**: ✅ FIXED in version 2.16.9-0.1+deb11u3
- **Debian Testing/Sid**: ✅ FIXED in version 3.6.4-2

**Action Plan:**

1. Continue monitoring Debian Security Tracker for Bookworm patch
2. Rebuild containers immediately when Debian 12 security update is released
3. Run security scans regularly to detect when patch is available
4. Document this assessment for users and security reviewers

**Last Checked**: 2025-10-27

---

### CVE-2024-56433 - shadow-utils subuid Conflict (LOW)

**Status**: ACCEPTED RISK - Debian marked "wont-fix"

**Details:**
- **Package**: login, passwd (shadow-utils)
- **CVSS Score**: 3.6 (Low)
- **Issue**: Potential UID conflicts in containerized environments with NFS

**Why This is Low Risk:**

1. OpenTranscribe containers do not use NFS home directories
2. Application runs as single non-root user (appuser, UID 1000)
3. No dynamic user creation or subuid mapping in application
4. Standard Docker deployment model without complex UID remapping

**Mitigation**: Default Docker security model is sufficient

---

### CVE-2023-2953 - OpenLDAP Null Pointer Dereference (HIGH)

**Status**: ACCEPTED RISK - Debian marked "wont-fix"

**Details:**
- **Package**: libldap-2.5-0
- **CVSS Score**: 7.5 (High)
- **Issue**: Denial of service via null pointer dereference in `ber_memalloc_x()`

**Why This is Low Risk:**

1. OpenTranscribe does not use LDAP functionality
2. libldap is a transitive dependency (likely from system packages)
3. Application has no LDAP client or server components
4. No LDAP-based authentication or directory services

**Mitigation**: Application does not expose LDAP attack surface

---

## Security Scanning Process

OpenTranscribe undergoes regular security scanning with multiple tools:

- **Trivy**: Comprehensive vulnerability scanner
- **Grype**: Vulnerability scanner with EPSS risk scoring
- **Dockle**: Docker best practices and security linter
- **Syft**: Software Bill of Materials (SBOM) generation

All scan results are published in the `security-reports/` directory for transparency.

---

## Reporting Security Issues

If you discover a security vulnerability in OpenTranscribe:

1. **DO NOT** open a public GitHub issue
2. Email: security@opentranscribe.org (or create a private security advisory)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if available)

---

## Update Policy

- **Critical vulnerabilities** in direct dependencies: Patched within 7 days
- **High vulnerabilities** in direct dependencies: Patched within 30 days
- **Transitive dependency vulnerabilities**: Evaluated for actual risk, patched when base images update
- **Base image updates**: Applied monthly or when security patches are available

---

## Additional Notes

### Non-Root Container User

OpenTranscribe backend containers run as non-root user (`appuser`, UID 1000) following Docker security best practices. This significantly reduces the attack surface even if vulnerabilities exist in system libraries.

### Minimal Attack Surface

The application:
- Requires authentication for all operations
- Validates all user inputs
- Uses parameterized SQL queries (SQLAlchemy ORM)
- Isolates services via Docker networking
- Stores credentials encrypted at rest

### Container Isolation

All services run in isolated Docker containers with:
- No privileged access
- Read-only root filesystems where possible
- Minimal system capabilities
- Network segmentation

---

**Document Version**: 1.0
**Maintainer**: OpenTranscribe Security Team
