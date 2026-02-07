"""Task endpoint tests.

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


def test_list_tasks(client, user_token_headers):
    """Test listing user's tasks"""
    response = client.get("/api/tasks", headers=user_token_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_tasks_unauthorized(client):
    """Test that unauthorized users cannot list tasks"""
    response = client.get("/api/tasks")
    assert response.status_code == 401  # Unauthorized


def test_get_task_not_found(client, user_token_headers):
    """Test getting a non-existent task"""
    import uuid as uuid_module

    fake_task_id = f"task_{uuid_module.uuid4()}"
    response = client.get(f"/api/tasks/{fake_task_id}", headers=user_token_headers)
    assert response.status_code == 404  # Not found


def test_get_task(client, user_token_headers, db_session):
    """Test getting a specific task"""
    # First upload a file to create an associated task
    sample_file = {"file": ("task_test.mp3", io.BytesIO(b"test content"), "audio/mpeg")}
    upload_response = client.post("/api/files", headers=user_token_headers, files=sample_file)
    assert upload_response.status_code == 200, f"File upload failed: {upload_response.json()}"

    file_data = upload_response.json()
    file_uuid = file_data.get("uuid") or file_data.get("id")

    # Get tasks to find the one associated with this file
    tasks_response = client.get("/api/tasks", headers=user_token_headers)
    tasks = tasks_response.json()

    # Find task associated with the file we just uploaded
    task = next(
        (
            t
            for t in tasks
            if t.get("media_file_uuid") == file_uuid or t.get("media_file_id") == file_uuid
        ),
        None,
    )

    if task:
        task_id = task.get("uuid") or task.get("id")
        # Now test getting the specific task
        response = client.get(f"/api/tasks/{task_id}", headers=user_token_headers)
        assert response.status_code == 200
        task_data = response.json()

        task_data_id = task_data.get("uuid") or task_data.get("id")
        assert task_data_id == task_id
    else:
        # Skip test if no task was created (some implementations might not auto-create tasks)
        pytest.skip("No task was created for the uploaded file")
