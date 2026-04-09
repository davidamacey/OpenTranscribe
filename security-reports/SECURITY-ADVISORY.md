# Security Advisory - OpenTranscribe

**Last Updated**: 2026-04-08
**Applies to**: OpenTranscribe v0.4.0
**Base Images**: `python:3.13-slim-trixie` (Debian 13), `nginx:1.29.8-alpine3.23`

## Overview

This document provides transparency about known security vulnerabilities in OpenTranscribe's container images and explains their actual risk to the application. It is updated alongside every tagged release.

## Pre-Release Posture for 0.4.0

Before the 0.4.0 release we:

- Bumped the backend base image from `python:3.13-slim-bookworm` to `python:3.13-slim-trixie` (Debian 13)
- Bumped the frontend/nginx base image to `nginx:1.29.8-alpine3.23`
- Added `apt-get upgrade -y` to the backend runtime stage in `backend/Dockerfile.prod` so every image build picks up Debian security updates without waiting for a base image retag
- Added `apk upgrade --no-cache` to the frontend runtime stage in `frontend/Dockerfile.prod` so every image build picks up Alpine security updates
- Upgraded PyTorch to 2.8.0+cu128 (includes CVE-2025-32434 fix), CTranslate2 to 4.6.0+, WhisperX to 3.8.1, and other direct Python dependencies to current patched versions

**Backend scan delta** (trivy, 0.4.0-rc vs pre-fix baseline):

| Severity | Baseline | 0.4.0 (Current) | Delta |
|---|---|---|---|
| CRITICAL | 6 | 3 | -50% |
| HIGH | 66 | 15 | -77% |
| MEDIUM | (unscored) | 62 | — |

The remaining Critical/High findings are all Debian 13 OS-level packages that are **not directly exploitable** by OpenTranscribe's code paths. Each is documented below with the reason it's considered accepted risk, and — where applicable — the upstream tracking link.

---

## Remaining Critical / High Vulnerabilities (v0.4.0)

### CVE-2026-34873 — Mbed TLS Client Impersonation (CRITICAL)

**Package**: `libmbedcrypto16` 3.6.5-0.1~deb13u1
**Status**: **ACCEPTED RISK** — no upstream patch, not in any exploitable code path
**Attack requirement**: Attacker must perform a TLS 1.3 handshake against a server using mbedtls for certificate validation

**Why this is not exploitable for OpenTranscribe:**

1. OpenTranscribe does NOT use mbedtls for any TLS operation. All HTTPS is done via Python's `requests` / `urllib3` / `httpx`, which use OpenSSL, not mbedtls.
2. `libmbedcrypto16` is present as a transitive dependency of a Debian system package (pulled in by `libgnutls` or similar), NOT because any OpenTranscribe binary links against it.
3. The vulnerability is a client-side impersonation flaw. OpenTranscribe's backend acts as an HTTP server (FastAPI / uvicorn), not a TLS client using mbedtls.
4. There is no code path in OpenTranscribe that would cause mbedtls to perform a TLS 1.3 handshake.

**Mitigation**: Will be updated when Debian 13 ships a patched `libmbedcrypto16`. Tracked at https://security-tracker.debian.org/tracker/CVE-2026-34873.

---

### CVE-2026-34872 — Mbed TLS Shared Secret Leak (HIGH)

Same package (`libmbedcrypto16`) and same reasoning as CVE-2026-34873 above. Accepted risk — not reachable from OpenTranscribe's code paths.

---

### CVE-2026-0968 — libssh SFTP Denial of Service (CRITICAL)

**Package**: `libssh-4` 0.11.2-1+deb13u1
**Status**: **ACCEPTED RISK** — marked `affected` by Debian, fix pending
**Attack requirement**: Attacker must connect to an SFTP server that uses libssh and send a malformed SFTP message

**Why this is not exploitable for OpenTranscribe:**

1. OpenTranscribe does NOT run an SSH or SFTP server. No inbound SSH/SFTP surface.
2. OpenTranscribe does NOT act as an SSH/SFTP client. Media ingest uses HTTPS (yt-dlp) or S3 (MinIO), never SSH.
3. `libssh-4` is a transitive dependency of `curl` (via `libcurl4`), not something OpenTranscribe code directly calls.

**Mitigation**: Will ship when Debian 13 releases the patched `libssh-4`. Tracked at https://security-tracker.debian.org/tracker/CVE-2026-0968.

---

### CVE-2026-3731 — libssh Out-of-Bounds Read (HIGH)

Same package and same reasoning as CVE-2026-0968 above. Accepted risk.

---

### CVE-2024-36600 — libcdio ISO File Arbitrary Code Execution (HIGH)

**Package**: `libcdio19t64` 2.2.0-4
**Status**: **ACCEPTED RISK** — not installed through any path OpenTranscribe exercises
**Attack requirement**: Attacker must pass a crafted ISO image file to a libcdio consumer

**Why this is not exploitable for OpenTranscribe:**

1. OpenTranscribe does not process ISO image files. Supported media types are audio (mp3, wav, flac, m4a, ogg) and video (mp4, mkv, mov, avi, webm).
2. `libcdio19t64` is pulled in transitively through one of the ffmpeg/libav dependencies. OpenTranscribe's ffmpeg invocations never use the CD/DVD code paths.

---

### CVE-2026-25210 — libexpat Information Disclosure (HIGH)

**Package**: `libexpat1` 2.7.1-2
**Status**: **ACCEPTED RISK** — not in any user-reachable XML parsing path

OpenTranscribe does not parse user-supplied XML. Expat is pulled in transitively by Debian packages (likely fontconfig, gettext, or dbus).

---

### CVE-2026-5201 — libgdk-pixbuf Heap DoS (HIGH)

**Package**: `libgdk-pixbuf-2.0-0` 2.42.12+dfsg-4
**Status**: **ACCEPTED RISK** — no GTK/graphics code path in OpenTranscribe

OpenTranscribe is a headless backend. `libgdk-pixbuf-2.0-0` is a transitive dependency not exercised by any OpenTranscribe code.

---

### CVE-2026-1837 — libjxl Grayscale OOB Write (HIGH)

**Package**: `libjxl0.11` 0.11.1-4
**Status**: **ACCEPTED RISK** — JPEG XL decoding path is not user-reachable

OpenTranscribe does not accept JPEG XL uploads. Image processing (thumbnails via ffmpeg) targets standard JPEG/PNG formats.

---

### CVE-2025-69720 — ncurses Buffer Overflow (HIGH)

**Package**: `libncursesw6` + `ncurses-base` 6.5+20250216-2
**Status**: **ACCEPTED RISK** — no interactive terminal code path in a containerized backend

ncurses is not called by any OpenTranscribe Python module. It's a transitive system package.

---

### CVE-2026-29111 — systemd Arbitrary Code Execution (HIGH)

**Package**: `libsystemd0` 257.9-1~deb13u1
**Status**: **ACCEPTED RISK** — container does not run systemd

The OpenTranscribe backend container uses a single `uvicorn` process as PID 1. No systemd daemon is running inside the container. `libsystemd0` is a transitive library dependency only (its journal-logging API is not used).

---

### CVE-2026-4775 — libtiff Arbitrary Code Execution (HIGH)

**Package**: `libtiff6` 4.7.0-3+deb13u1
**Status**: **ACCEPTED RISK** — TIFF decoding is not a supported OpenTranscribe input path

OpenTranscribe does not accept TIFF uploads. libtiff is pulled in by ffmpeg's image filters, which are not exercised by the transcription pipeline.

---

### CVE-2024-23342 — python-ecdsa Minerva Attack (HIGH)

**Package**: `ecdsa` 0.19.2 (Python, transitive via `python-jose`)
**Status**: **ACCEPTED RISK** — not used for any timing-sensitive signing

python-ecdsa is pulled in by `python-jose` for JWT token operations. OpenTranscribe uses HS256 (HMAC-SHA256) for JWT signing by default, NOT ECDSA. The Minerva side-channel attack requires the attacker to observe timing of many ECDSA signing operations against a secret key — OpenTranscribe does not perform ECDSA signing operations.

---

## Frontend Image (v0.4.0)

**Base**: `nginx:1.29.8-alpine3.23` + `apk upgrade --no-cache`

Post-fix trivy scan: **0 Critical, 0 High** on the frontend image. All previous Alpine advisories have been resolved by the base image bump plus `apk upgrade`.

## Docs Image (v0.4.0)

**Base**: `nginx:1.29.8-alpine3.23` + `apk upgrade --no-cache`

Post-fix trivy scan: **0 Critical, 0 High** on the docs image (Docusaurus static site).

---

## Security Scanning Process

OpenTranscribe is scanned with the following tools on every release:

- **Trivy** — comprehensive vulnerability scanner with CVE database
- **Grype** — secondary scanner with EPSS risk scoring for corroboration
- **Syft** — software bill of materials (SBOM) generation (SPDX + CycloneDX)
- **Dockle** — Docker best-practices and image hardening linter
- **Hadolint** — Dockerfile linter

All scan outputs are committed to `security-reports/` in this repository for transparency and reproducibility. Re-run them yourself with:

```bash
IMAGE_TAG=0.4.0 ./scripts/security-scan.sh all
```

---

## Reporting Security Issues

If you discover a security vulnerability in OpenTranscribe:

1. **DO NOT** open a public GitHub issue
2. Report via GitHub private security advisory: https://github.com/davidamacey/OpenTranscribe/security/advisories
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if available)

---

## Update Policy

- **Critical vulnerabilities** in direct dependencies: patched within 7 days
- **High vulnerabilities** in direct dependencies: patched within 30 days
- **Transitive / OS-level vulnerabilities**: evaluated for actual exploitability; patched automatically via `apt-get upgrade` / `apk upgrade` on every image build
- **Base image updates**: applied on every release (see `backend/Dockerfile.prod` and `frontend/Dockerfile.prod` runtime stages)

---

## Hardening Notes

### Non-Root Container User

OpenTranscribe backend containers run as `appuser` (UID 1000), not root. This significantly reduces the attack surface even if a vulnerability exists in system libraries.

### Minimal Attack Surface

The application:
- Requires authentication for all operations (local password, LDAP, Keycloak/OIDC, or PKI client cert)
- Validates all user inputs via Pydantic schemas
- Uses parameterized SQL queries (SQLAlchemy ORM only — no string-interpolated SQL)
- Isolates services via Docker networking with minimum-necessary port exposure
- Stores credentials encrypted at rest (Fernet, per-field encryption for API keys)
- Enforces configurable password policy + rate limiting + account lockout
- Supports optional TOTP MFA (RFC 6238) for local-auth users

### Container Isolation

- All services run as non-root inside their containers
- No privileged mode
- Backend container uses `--cap-drop ALL` where possible
- Network segmentation via Docker bridge networks

---

**Document Version**: 2.0
**Applies to**: OpenTranscribe 0.4.0
**Maintainer**: OpenTranscribe Security Team
