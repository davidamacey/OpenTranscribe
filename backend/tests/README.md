# Backend Tests

This directory contains pytest tests for the OpenTranscribe backend.

## Quick Start

```bash
# Activate virtual environment
source backend/venv/bin/activate

# Run all backend tests (parallel, recommended)
pytest backend/tests/ -n 4 --ignore=backend/tests/e2e -q

# Run with auto-detected parallelism
pytest backend/tests/ -n auto --ignore=backend/tests/e2e -q
```

## Test Categories

| Directory/File | Description | Requirements |
|----------------|-------------|--------------|
| `api/endpoints/` | API endpoint tests | PostgreSQL |
| `e2e/` | Playwright E2E tests | Running server + browser |
| `test_asr_settings.py` | ASR provider settings tests (68 tests) | PostgreSQL |
| `test_auth_config_integration.py` | Auth config DB round-trip | PostgreSQL |
| `test_auth_config_service.py` | Auth config service (mock-based) | `RUN_AUTH_CONFIG_TESTS=true` |
| `test_fedramp_compliance.py` | FedRAMP compliance tests | PostgreSQL |
| `test_fips_140_3.py` | FIPS 140-3 compliance | `RUN_FIPS_TESTS=true` |
| `test_llm_settings.py` | LLM settings tests | `RUN_LLM_TESTS=true` |
| `test_mfa_integration.py` | MFA integration tests | PostgreSQL |
| `test_mfa_security.py` | MFA security tests | `RUN_MFA_TESTS=true` |
| `test_pki_auth.py` | PKI authentication tests | `RUN_PKI_TESTS=true` |
| `test_search_quality.py` | Search quality tests | Live server + indexed data |
| `test_speaker_constraints.py` | Speaker database constraints | PostgreSQL |
| `test_error_classification.py` | Error classification logic | None |

## Running Tests

### Parallel Execution (Recommended)

Tests use `pytest-xdist` for parallel execution, which significantly speeds up test runs:

```bash
# 4 parallel workers (good default)
pytest backend/tests/ -n 4 --ignore=backend/tests/e2e

# Auto-detect CPU cores
pytest backend/tests/ -n auto --ignore=backend/tests/e2e

# Sequential (slower, useful for debugging)
pytest backend/tests/ --ignore=backend/tests/e2e
```

### Specific Test Files

```bash
# Authentication tests (43 tests)
pytest backend/tests/api/endpoints/test_auth_comprehensive.py -v

# ASR settings tests (68 tests)
pytest backend/tests/test_asr_settings.py -v

# Admin endpoint tests
pytest backend/tests/api/endpoints/test_admin.py -v

# User management tests
pytest backend/tests/api/endpoints/test_users.py -v

# Tag tests
pytest backend/tests/api/endpoints/test_tags.py -v
```

### Verbose Output

```bash
# Show test names
pytest backend/tests/ -v --ignore=backend/tests/e2e

# Show print statements
pytest backend/tests/ -s --ignore=backend/tests/e2e

# Stop on first failure
pytest backend/tests/ -x --ignore=backend/tests/e2e
```

## Environment Variables

The test suite uses these environment variables (set automatically by conftest.py):

| Variable | Default | Description |
|----------|---------|-------------|
| `TESTING` | `True` | Enables test mode |
| `SKIP_CELERY` | `True` | Skips heavy AI module imports (torch, pyannote) |
| `SKIP_S3` | `True` | Skips MinIO/S3 operations |
| `SKIP_REDIS` | `True` | Skips Redis operations |
| `SKIP_OPENSEARCH` | `True` | Skips OpenSearch operations |
| `POSTGRES_HOST` | `localhost` | Database host for local testing |
| `POSTGRES_PORT` | `5176` | Database port (Docker exposed port) |

### Optional Test Flags

Enable specific test suites with environment variables:

```bash
# Auth config service tests (mock-based)
RUN_AUTH_CONFIG_TESTS=true pytest backend/tests/test_auth_config_service.py -v

# LLM settings tests
RUN_LLM_TESTS=true pytest backend/tests/test_llm_settings.py -v

# FIPS 140-3 compliance tests
RUN_FIPS_TESTS=true pytest backend/tests/test_fips_140_3.py -v

# MFA security tests
RUN_MFA_TESTS=true pytest backend/tests/test_mfa_security.py -v

# PKI authentication tests
RUN_PKI_TESTS=true pytest backend/tests/test_pki_auth.py -v

# Search quality tests (requires live server)
RUN_SEARCH_QUALITY_TESTS=true pytest backend/tests/test_search_quality.py -v

# Advanced admin tests
RUN_ADVANCED_ADMIN_TESTS=true pytest backend/tests/test_admin_security.py -v
```

## Test Performance

### Why Tests Are Slow

1. **Heavy AI imports**: PyAnnote, WhisperX, and torch take ~10s to import
2. **Database transactions**: Each test uses PostgreSQL with transaction rollback
3. **Password hashing**: PBKDF2 with 210,000 iterations (FIPS compliant)

### Speedup Strategies

1. **Parallel execution**: Use `-n 4` or `-n auto` (pytest-xdist)
2. **Skip AI imports**: `SKIP_CELERY=True` skips torch/pyannote in some paths
3. **Run specific tests**: Target only the tests you need

### Typical Performance

| Test Suite | Sequential | Parallel (-n 4) |
|------------|------------|-----------------|
| auth_comprehensive (43 tests) | ~5 min | ~1.5 min |
| All backend tests (~90 tests) | ~12 min | ~3-4 min |

## Database Setup

Tests require PostgreSQL running (via Docker Compose):

```bash
# Start development environment
./opentr.sh start dev

# Or just start PostgreSQL
docker compose up -d postgres
```

The test database uses the same PostgreSQL instance as development but with transaction rollback isolation - all test changes are rolled back after each test.

## Test Fixtures

Key fixtures defined in `conftest.py`:

| Fixture | Scope | Description |
|---------|-------|-------------|
| `db_session` | function | Database session with transaction rollback |
| `client` | function | FastAPI TestClient with test DB |
| `normal_user` | function | Creates a regular user |
| `admin_user` | function | Creates an admin user |
| `user_token_headers` | function | Auth headers for regular user |
| `admin_token_headers` | function | Auth headers for admin user |

## Writing New Tests

### Basic Test Structure

```python
def test_example_endpoint(client, user_token_headers):
    """Test description."""
    response = client.get("/api/endpoint", headers=user_token_headers)
    assert response.status_code == 200
    assert "expected_field" in response.json()
```

### Skip Tests Conditionally

```python
import pytest
import os

# Skip if external service not available
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_S3", "True").lower() == "true",
    reason="S3/MinIO storage is disabled in test environment",
)

# Skip entire test class
@pytest.mark.skipif(
    os.environ.get("RUN_FEATURE_TESTS", "false").lower() != "true",
    reason="Feature tests disabled (set RUN_FEATURE_TESTS=true to run)",
)
class TestNewFeature:
    def test_something(self):
        pass
```

## Troubleshooting

### "Connection refused" errors

Ensure PostgreSQL is running:
```bash
./opentr.sh status
# or
docker compose ps
```

### Import errors

Activate the virtual environment:
```bash
source backend/venv/bin/activate
```

### Slow first run

The first test run loads AI models (~10s). Subsequent runs in the same session are faster. Use parallel execution (`-n 4`) to mitigate.

### Test isolation issues

Each test uses database transaction rollback. If you see data leaking between tests, check that the test is using the `db_session` fixture correctly.
