from fastapi.testclient import TestClient
import pytest

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["product"] == "NexusLead AI"


def test_dashboard_endpoint(client):
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "NexusLead AI" in response.text
    assert "No scraping" in response.text


def test_analytics_endpoint(client):
    response = client.get("/api/analytics")

    assert response.status_code == 200
    assert response.json()["daily_lead_count"] >= 5


def test_csv_export_endpoint(client):
    response = client.get("/export/tasks.csv")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "task" in response.text
