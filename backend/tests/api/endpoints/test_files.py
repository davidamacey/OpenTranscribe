import io

import pytest


@pytest.fixture
def sample_audio_file():
    """Create a mock audio file for testing"""
    return {"file": ("test_audio.mp3", io.BytesIO(b"mock audio content"), "audio/mpeg")}


def test_list_files(client, user_token_headers):
    """Test listing user's files"""
    response = client.get("/api/files/", headers=user_token_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_files_unauthorized(client):
    """Test that unauthorized users cannot list files"""
    response = client.get("/api/files/")
    assert response.status_code == 401  # Unauthorized


def test_upload_file(client, user_token_headers, sample_audio_file, db_session):
    """Test uploading a file"""
    response = client.post("/api/files/", headers=user_token_headers, files=sample_audio_file)
    assert response.status_code == 200
    file_data = response.json()

    # Basic schema validation
    assert "id" in file_data
    assert "filename" in file_data
    assert file_data["filename"] == "test_audio.mp3"

    # Verify file exists in the database
    from app.models.media import MediaFile

    db_file = db_session.query(MediaFile).filter(MediaFile.id == file_data["id"]).first()
    assert db_file is not None
    assert db_file.filename == "test_audio.mp3"


def test_upload_file_unauthorized(client, sample_audio_file):
    """Test that unauthorized users cannot upload files"""
    response = client.post("/api/files/", files=sample_audio_file)
    assert response.status_code == 401  # Unauthorized


def test_get_file_not_found(client, user_token_headers):
    """Test getting a non-existent file"""
    response = client.get("/api/files/999999", headers=user_token_headers)
    assert response.status_code == 404  # Not found


# This test assumes the upload test has been run first
def test_get_file(client, user_token_headers, db_session):
    """Test getting a specific file"""
    # First upload a file to get its ID
    sample_file = {"file": ("test_get.mp3", io.BytesIO(b"test content"), "audio/mpeg")}
    upload_response = client.post("/api/files/", headers=user_token_headers, files=sample_file)
    file_id = upload_response.json()["id"]

    # Now test getting the file
    response = client.get(f"/api/files/{file_id}", headers=user_token_headers)
    assert response.status_code == 200
    file_data = response.json()

    assert file_data["id"] == file_id
    assert file_data["filename"] == "test_get.mp3"


def test_update_file(client, user_token_headers, db_session):
    """Test updating a file's metadata"""
    # First upload a file to get its ID
    sample_file = {"file": ("test_update.mp3", io.BytesIO(b"test content"), "audio/mpeg")}
    upload_response = client.post("/api/files/", headers=user_token_headers, files=sample_file)
    file_id = upload_response.json()["id"]

    # Now test updating the file
    update_data = {
        "filename": "updated_filename.mp3",
        "summary": "This is a test summary",
    }
    response = client.put(f"/api/files/{file_id}", headers=user_token_headers, json=update_data)
    assert response.status_code == 200
    file_data = response.json()

    assert file_data["id"] == file_id
    assert file_data["filename"] == "updated_filename.mp3"
    assert file_data["summary"] == "This is a test summary"

    # Verify changes in the database
    from app.models.media import MediaFile

    db_file = db_session.query(MediaFile).filter(MediaFile.id == file_id).first()
    assert db_file.filename == "updated_filename.mp3"
    assert db_file.summary == "This is a test summary"


def test_delete_file(client, user_token_headers, db_session):
    """Test deleting a file"""
    # First upload a file to get its ID
    sample_file = {"file": ("test_delete.mp3", io.BytesIO(b"test content"), "audio/mpeg")}
    upload_response = client.post("/api/files/", headers=user_token_headers, files=sample_file)
    file_id = upload_response.json()["id"]

    # Now test deleting the file
    response = client.delete(f"/api/files/{file_id}", headers=user_token_headers)
    assert response.status_code == 204  # No content

    # Verify the file is deleted from the database
    from app.models.media import MediaFile

    db_file = db_session.query(MediaFile).filter(MediaFile.id == file_id).first()
    assert db_file is None
