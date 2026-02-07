def test_health_endpoint(client):
    """Test that the health endpoint returns the proper response."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
