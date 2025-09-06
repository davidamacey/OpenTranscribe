import io

import pytest


@pytest.fixture
def test_file_with_comment(client, user_token_headers, db_session):
    """Create a test file that we can add comments to"""
    # Upload a file
    file_data = {
        "file": ("comment_test.mp3", io.BytesIO(b"test audio content"), "audio/mpeg")
    }
    response = client.post("/api/files/", headers=user_token_headers, files=file_data)
    return response.json()["id"]

def test_list_comments(client, user_token_headers, test_file_with_comment):
    """Test listing comments for a file"""
    response = client.get(f"/api/comments/?media_file_id={test_file_with_comment}", headers=user_token_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_create_comment(client, user_token_headers, test_file_with_comment, db_session):
    """Test creating a comment for a file"""
    comment_data = {
        "media_file_id": test_file_with_comment,
        "text": "This is a test comment",
        "timestamp": 30.5  # Comment at 30.5 seconds in the audio
    }
    response = client.post("/api/comments/", headers=user_token_headers, json=comment_data)
    assert response.status_code == 200
    comment = response.json()
    assert "id" in comment
    assert comment["text"] == "This is a test comment"
    assert comment["media_file_id"] == test_file_with_comment
    assert comment["timestamp"] == 30.5

    # Verify comment exists in the database
    from app.models.media import Comment
    db_comment = db_session.query(Comment).filter(
        Comment.media_file_id == test_file_with_comment,
        Comment.text == "This is a test comment"
    ).first()
    assert db_comment is not None
    assert db_comment.text == "This is a test comment"
    assert db_comment.timestamp == 30.5

def test_get_comment(client, user_token_headers, test_file_with_comment, db_session):
    """Test getting a specific comment"""
    # First create a comment
    comment_data = {
        "media_file_id": test_file_with_comment,
        "text": "Comment for get test",
        "timestamp": 45.0
    }
    create_response = client.post("/api/comments/", headers=user_token_headers, json=comment_data)
    comment_id = create_response.json()["id"]

    # Now get the comment
    response = client.get(f"/api/comments/{comment_id}", headers=user_token_headers)
    assert response.status_code == 200
    comment = response.json()
    assert comment["id"] == comment_id
    assert comment["text"] == "Comment for get test"
    assert comment["timestamp"] == 45.0

def test_update_comment(client, user_token_headers, test_file_with_comment, db_session):
    """Test updating a comment"""
    # First create a comment
    comment_data = {
        "media_file_id": test_file_with_comment,
        "text": "Comment for update test",
        "timestamp": 60.0
    }
    create_response = client.post("/api/comments/", headers=user_token_headers, json=comment_data)
    comment_id = create_response.json()["id"]

    # Now update the comment
    update_data = {
        "text": "Updated comment text",
        "timestamp": 65.5
    }
    response = client.put(f"/api/comments/{comment_id}", headers=user_token_headers, json=update_data)
    assert response.status_code == 200
    comment = response.json()
    assert comment["id"] == comment_id
    assert comment["text"] == "Updated comment text"
    assert comment["timestamp"] == 65.5

    # Verify changes in the database
    from app.models.media import Comment
    db_comment = db_session.query(Comment).filter(Comment.id == comment_id).first()
    assert db_comment.text == "Updated comment text"
    assert db_comment.timestamp == 65.5

def test_delete_comment(client, user_token_headers, test_file_with_comment, db_session):
    """Test deleting a comment"""
    # First create a comment
    comment_data = {
        "media_file_id": test_file_with_comment,
        "text": "Comment for delete test",
        "timestamp": 75.0
    }
    create_response = client.post("/api/comments/", headers=user_token_headers, json=comment_data)
    comment_id = create_response.json()["id"]

    # Now delete the comment
    response = client.delete(f"/api/comments/{comment_id}", headers=user_token_headers)
    assert response.status_code == 204  # No content

    # Verify comment is deleted from the database
    from app.models.media import Comment
    db_comment = db_session.query(Comment).filter(Comment.id == comment_id).first()
    assert db_comment is None
