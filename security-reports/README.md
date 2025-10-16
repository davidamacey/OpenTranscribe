# Security Reports

This directory contains security scan reports from the latest build pipeline execution.

Reports are generated automatically during the Docker build process and include:
- **Hadolint**: Dockerfile linting
- **Dockle**: CIS Docker best practices
- **Syft**: Software Bill of Materials (SBOM)
- **Trivy**: Vulnerability scanning
- **Grype**: Additional vulnerability scanning

## Latest Reports

Run `./scripts/build-all.sh` or `./scripts/docker-build-push.sh` to generate updated reports.

For details, see [docs/BUILD_PIPELINE.md](../docs/BUILD_PIPELINE.md).
