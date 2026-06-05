import pytest


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "Billion Dollar API"
    assert "as_of" in payload
    assert "data_status" in payload
