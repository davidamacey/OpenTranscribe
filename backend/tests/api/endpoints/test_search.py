import io

import pytest


@pytest.fixture
def test_file_for_search(client, user_token_headers, db_session):
    """Create test files that we can search for"""
    # Upload a file for searching
    file_data = {
        "file": (
            "searchable_audio.mp3",
            io.BytesIO(b"test audio content"),
            "audio/mpeg",
        )
    }
    response = client.post("/api/files/", headers=user_token_headers, files=file_data)
    file_id = response.json()["id"]

    # Update the file with searchable metadata
    update_data = {
        "filename": "searchable_test.mp3",
        "summary": "This is a test file for search functionality",
        "language": "en",
    }
    client.put(f"/api/files/{file_id}", headers=user_token_headers, json=update_data)

    return file_id


def test_search_files(client, user_token_headers, test_file_for_search):
    """Test searching for files"""
    response = client.get("/api/search/?query=test", headers=user_token_headers)
    assert response.status_code == 200
    results = response.json()
    assert isinstance(results, list)

    # Should find our test file
    found = False
    for result in results:
        if result.get("id") == test_file_for_search:
            found = True
            break

    assert found, "Test file should be found in search results"


def test_search_with_filters(client, user_token_headers, test_file_for_search):
    """Test searching with filters"""
    # Search with language filter
    response = client.get("/api/search/?query=test&language=en", headers=user_token_headers)
    assert response.status_code == 200
    results = response.json()

    # Should find our test file with language filter
    found = False
    for result in results:
        if result.get("id") == test_file_for_search:
            found = True
            break

    assert found, "Test file should be found in filtered search results"


def test_search_unauthorized(client):
    """Test that unauthorized users cannot search"""
    response = client.get("/api/search/?query=test")
    assert response.status_code == 401  # Unauthorized
