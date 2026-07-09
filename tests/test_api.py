from fastapi.testclient import TestClient
import pytest

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def login_as(client, email, password):
    response = client.post("/login", data={"email": email, "password": password}, follow_redirects=False)
    assert response.status_code == 303
    return client


@pytest.fixture()
def admin_client(client):
    return login_as(client, "admin@nextrns.local", "admin123")


@pytest.fixture()
def manager_client(client):
    return login_as(client, "manager@nextrns.local", "manager123")


@pytest.fixture()
def agent_client(client):
    return login_as(client, "agent@nextrns.local", "agent123")


def test_health_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["product"] == "NexusLead AI"
    assert response.json()["database"]["engine"] == "sqlite"


def test_dashboard_requires_login(client):
    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_dashboard_endpoint(admin_client):
    response = admin_client.get("/dashboard")

    assert response.status_code == 200
    assert "Lead Operations Workspace" in response.text
    assert "User management" in response.text


def test_manager_can_approve_and_assign(manager_client):
    leads = manager_client.get("/api/leads").json()
    lead_id = leads[0]["id"]

    assign_response = manager_client.post(
        f"/leads/{lead_id}/assign",
        data={"owner": "Lead Operations Agent"},
        follow_redirects=False,
    )
    approve_response = manager_client.post(f"/leads/{lead_id}/approve", follow_redirects=False)

    assert assign_response.status_code == 303
    assert approve_response.status_code == 303


def test_agent_cannot_export_all_leads(agent_client):
    response = agent_client.get("/export/leads.csv")

    assert response.status_code == 403


def test_agent_can_export_assigned_tasks(agent_client):
    response = agent_client.get("/export/tasks.csv")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "task" in response.text


def test_analytics_endpoint(admin_client):
    response = admin_client.get("/api/analytics")

    assert response.status_code == 200
    assert response.json()["daily_lead_count"] >= 5


def test_metrics_endpoint(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "nexuslead_leads_total" in response.json()


def test_openapi_includes_core_paths(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/leads" in paths
    assert "/api/clients" in paths
    assert "/api/tasks" in paths
