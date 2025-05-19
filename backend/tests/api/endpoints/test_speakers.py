import pytest
from fastapi.testclient import TestClient

def test_list_speakers(client, user_token_headers):
    """Test listing all speakers for the user"""
    response = client.get("/api/speakers/", headers=user_token_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    
def test_list_speakers_unauthorized(client):
    """Test that unauthorized users cannot list speakers"""
    response = client.get("/api/speakers/")
    assert response.status_code == 401  # Unauthorized

def test_create_speaker(client, user_token_headers, db_session):
    """Test creating a new speaker"""
    speaker_data = {
        "name": "Test Speaker"
    }
    response = client.post("/api/speakers/", headers=user_token_headers, json=speaker_data)
    assert response.status_code == 200
    speaker = response.json()
    assert "id" in speaker
    assert speaker["name"] == "Test Speaker"
    
    # Verify speaker exists in the database
    from app.models.media import Speaker
    db_speaker = db_session.query(Speaker).filter(Speaker.name == "Test Speaker").first()
    assert db_speaker is not None
    assert db_speaker.name == "Test Speaker"

def test_get_speaker(client, user_token_headers, db_session):
    """Test getting a specific speaker"""
    # First create a speaker
    speaker_data = {
        "name": "Speaker for Get Test"
    }
    create_response = client.post("/api/speakers/", headers=user_token_headers, json=speaker_data)
    speaker_id = create_response.json()["id"]
    
    # Now get the speaker
    response = client.get(f"/api/speakers/{speaker_id}", headers=user_token_headers)
    assert response.status_code == 200
    speaker = response.json()
    assert speaker["id"] == speaker_id
    assert speaker["name"] == "Speaker for Get Test"

def test_update_speaker(client, user_token_headers, db_session):
    """Test updating a speaker"""
    # First create a speaker
    speaker_data = {
        "name": "Speaker for Update Test"
    }
    create_response = client.post("/api/speakers/", headers=user_token_headers, json=speaker_data)
    speaker_id = create_response.json()["id"]
    
    # Now update the speaker
    update_data = {
        "name": "Updated Speaker Name"
    }
    response = client.put(f"/api/speakers/{speaker_id}", headers=user_token_headers, json=update_data)
    assert response.status_code == 200
    speaker = response.json()
    assert speaker["id"] == speaker_id
    assert speaker["name"] == "Updated Speaker Name"
    
    # Verify changes in the database
    from app.models.media import Speaker
    db_speaker = db_session.query(Speaker).filter(Speaker.id == speaker_id).first()
    assert db_speaker.name == "Updated Speaker Name"

def test_delete_speaker(client, user_token_headers, db_session):
    """Test deleting a speaker"""
    # First create a speaker
    speaker_data = {
        "name": "Speaker for Delete Test"
    }
    create_response = client.post("/api/speakers/", headers=user_token_headers, json=speaker_data)
    speaker_id = create_response.json()["id"]
    
    # Now delete the speaker
    response = client.delete(f"/api/speakers/{speaker_id}", headers=user_token_headers)
    assert response.status_code == 204  # No content
    
    # Verify speaker is deleted from the database
    from app.models.media import Speaker
    db_speaker = db_session.query(Speaker).filter(Speaker.id == speaker_id).first()
    assert db_speaker is None
