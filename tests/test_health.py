from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_metadata():
    response = client.get("/api/v1/metadata")
    assert response.status_code == 200
    assert response.json()["api_version"] == "v1"

def test_auth_requires_token():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
