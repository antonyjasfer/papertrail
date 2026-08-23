from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

client = TestClient(app)


def test_health_endpoint():
    """Verify that GET /health returns status 200 and expected payload."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "PaperTrail AI"
    assert data["version"] == "0.1.0"
    assert data["phase"] == settings.phase
