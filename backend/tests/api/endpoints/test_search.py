"""Search endpoint tests.

These tests require OpenSearch which is disabled in the test environment.
They are marked as skipped by default. Run with actual search services for full testing.
"""

import os

import pytest

# Skip all tests in this module if OpenSearch is not available
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_OPENSEARCH", "True").lower() == "true",
    reason="OpenSearch is disabled in test environment",
)


def test_search_files(client, user_token_headers):
    """Test searching files"""
    response = client.get("/api/search", params={"q": "test"}, headers=user_token_headers)
    assert response.status_code == 200
    data = response.json()
    assert "results" in data or "items" in data


def test_search_with_filters(client, user_token_headers):
    """Test search with filters"""
    response = client.get(
        "/api/search",
        params={"q": "test", "mode": "keyword"},
        headers=user_token_headers,
    )
    assert response.status_code == 200


def test_search_unauthorized(client):
    """Test that unauthorized users cannot search"""
    response = client.get("/api/search", params={"q": "test"})
    assert response.status_code == 401  # Unauthorized
