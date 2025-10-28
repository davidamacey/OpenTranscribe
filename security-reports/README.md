# Security Reports

This directory contains automated security scan reports for OpenTranscribe container images.

## Purpose

We believe in **security transparency**. All security scan results are published here so users can:
- Understand the security posture of OpenTranscribe
- Make informed deployment decisions
- Review vulnerability assessments
- Track security improvements over time

## Scan Reports

### Backend Container

- `backend-trivy.json` / `backend-trivy.txt` - Trivy vulnerability scan
- `backend-grype.json` / `backend-grype.txt` - Grype vulnerability scan with EPSS risk scoring
- `backend-dockle.json` - Dockle Docker security best practices audit
- `backend-sbom.json` / `backend-sbom.txt` - Software Bill of Materials (SBOM)

### Frontend Container

- `frontend-trivy.json` - Trivy vulnerability scan
- `frontend-grype.json` / `frontend-grype.txt` - Grype vulnerability scan
- `frontend-dockle.json` - Dockle Docker security audit
- `frontend-sbom.json` / `frontend-sbom.txt` - Software Bill of Materials (SBOM)

## Understanding the Reports

### Severity Levels

- **CRITICAL**: Requires immediate attention for direct dependencies
- **HIGH**: Should be addressed in near-term updates
- **MEDIUM**: Monitored and addressed in regular updates
- **LOW**: Informational, addressed when convenient

### Risk Assessment

Not all reported vulnerabilities pose actual risk to OpenTranscribe. We assess:

1. **Is it a direct dependency?** - If not, limited control until base image updates
2. **Does the app use the vulnerable code?** - Many vulnerabilities are in unused library functions
3. **Is there an attack vector?** - Can an attacker actually trigger the vulnerability?
4. **What's the EPSS score?** - Exploit Prediction Scoring System probability

See [SECURITY-ADVISORY.md](./SECURITY-ADVISORY.md) for detailed risk assessments of current vulnerabilities.

## Security Scanning Tools

### Trivy
- **Purpose**: Comprehensive vulnerability scanner
- **Scope**: OS packages, application dependencies, container configurations
- **Database**: Multiple vulnerability databases (NVD, vendor advisories, etc.)

### Grype
- **Purpose**: Vulnerability scanner with EPSS risk scoring
- **Scope**: OS packages, language-specific packages
- **Database**: Anchore vulnerability database
- **Unique Feature**: EPSS (Exploit Prediction Scoring System) scores

### Dockle
- **Purpose**: Docker best practices and security linter
- **Scope**: Dockerfile and container image configuration
- **Standards**: CIS Docker Benchmark compliance

### Syft
- **Purpose**: Software Bill of Materials (SBOM) generation
- **Scope**: Complete inventory of all packages and dependencies
- **Format**: SPDX, CycloneDX compatible

## Current Security Status

✅ **Backend Dockle Score**: 0 fatal, 0 warn, 1 info
- No critical security misconfigurations
- Follows Docker security best practices
- Non-root container user (UID 1000)

⚠️ **Known Vulnerabilities**: See [SECURITY-ADVISORY.md](./SECURITY-ADVISORY.md)
- CVE-2025-47917 (Critical - Low Risk): Mbed TLS vulnerability in unused functionality
- Other low-risk vulnerabilities in transitive system dependencies

## Update Frequency

Security scans are run:
- On every Docker image build
- After base image updates
- After dependency updates
- Monthly for routine checks

Reports are automatically updated in this directory.

## Security Response

For our security vulnerability response policy, see [SECURITY-ADVISORY.md](./SECURITY-ADVISORY.md).

### Reporting Security Issues

If you discover a security vulnerability:
- **DO NOT** open a public GitHub issue
- Contact: security@opentranscribe.org (or create a private security advisory)
- See [SECURITY-ADVISORY.md](./SECURITY-ADVISORY.md) for details

## Generating Reports

Run `./scripts/build-all.sh` or `./scripts/docker-build-push.sh` to generate updated reports.

For details, see [docs/BUILD_PIPELINE.md](../docs/BUILD_PIPELINE.md).

---

**Last Updated**: 2025-10-27
