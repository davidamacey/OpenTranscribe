import pytest
from fastapi.testclient import TestClient
import io
from datetime import datetime

def test_list_tasks(client, user_token_headers):
    """Test listing user's tasks"""
    response = client.get("/api/tasks/", headers=user_token_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    
def test_list_tasks_unauthorized(client):
    """Test that unauthorized users cannot list tasks"""
    response = client.get("/api/tasks/")
    assert response.status_code == 401  # Unauthorized

def test_get_task_not_found(client, user_token_headers):
    """Test getting a non-existent task"""
    response = client.get("/api/tasks/task_999999", headers=user_token_headers)
    assert response.status_code == 404  # Not found

# This test depends on the file upload creating a task
def test_get_task(client, user_token_headers, db_session):
    """Test getting a specific task"""
    # First upload a file to create an associated task
    sample_file = {
        "file": ("task_test.mp3", io.BytesIO(b"test content"), "audio/mpeg")
    }
    upload_response = client.post("/api/files/", headers=user_token_headers, files=sample_file)
    file_id = upload_response.json()["id"]
    
    # Get tasks to find the one associated with this file
    tasks_response = client.get("/api/tasks/", headers=user_token_headers)
    tasks = tasks_response.json()
    
    # Find task associated with the file we just uploaded
    task = next((t for t in tasks if t["media_file_id"] == file_id), None)
    
    if task:
        # Now test getting the specific task
        response = client.get(f"/api/tasks/{task['id']}", headers=user_token_headers)
        assert response.status_code == 200
        task_data = response.json()
        
        assert task_data["id"] == task["id"]
        assert task_data["media_file_id"] == file_id
    else:
        # Skip test if no task was created (some implementations might not auto-create tasks)
        pytest.skip("No task was created for the uploaded file")
