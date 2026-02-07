"""Media file endpoint tests.

These tests require MinIO/S3 storage which is disabled in the test environment.
They are marked as skipped by default. Run with actual storage services for full testing.
"""

import io
import os

import pytest

# Skip all tests in this module if S3 is not available
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_S3", "True").lower() == "true",
    reason="S3/MinIO storage is disabled in test environment",
)


@pytest.fixture
def sample_audio_file():
    """Create a mock audio file for testing"""
    return {"file": ("test_audio.mp3", io.BytesIO(b"mock audio content"), "audio/mpeg")}


def test_list_files(client, user_token_headers):
    """Test listing user's files"""
    response = client.get("/api/files", headers=user_token_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data  # Paginated response
    assert isinstance(data["items"], list)


def test_list_files_unauthorized(client):
    """Test that unauthorized users cannot list files"""
    response = client.get("/api/files")
    assert response.status_code == 401  # Unauthorized


def test_upload_file(client, user_token_headers, sample_audio_file, db_session):
    """Test uploading a file"""
    response = client.post("/api/files", headers=user_token_headers, files=sample_audio_file)
    assert response.status_code == 200
    file_data = response.json()

    # Basic schema validation - uses uuid not id
    assert "uuid" in file_data
    assert "filename" in file_data
    assert file_data["filename"] == "test_audio.mp3"


def test_upload_file_unauthorized(client, sample_audio_file):
    """Test that unauthorized users cannot upload files"""
    response = client.post("/api/files", files=sample_audio_file)
    assert response.status_code == 401  # Unauthorized


def test_get_file_not_found(client, user_token_headers):
    """Test getting a non-existent file"""
    import uuid as uuid_module

    fake_uuid = str(uuid_module.uuid4())
    response = client.get(f"/api/files/{fake_uuid}", headers=user_token_headers)
    assert response.status_code == 404  # Not found
