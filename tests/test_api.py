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


def test_root_renders_login_for_public_visitors(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert "NexusLead AI" in response.text
    assert "Review credentials" in response.text
    assert response.headers["cache-control"].startswith("no-store")


def test_root_redirects_authenticated_users_to_dashboard(admin_client):
    response = admin_client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_health_endpoint(client):
    response = client.get("/health")

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
    assert "/api/leads/intake" in paths
    assert "/webhooks/n8n/leads" in paths


def test_api_lead_intake_requires_login(client):
    response = client.post("/api/leads/intake", json={"category": "Carpenter"}, follow_redirects=False)

    assert response.status_code == 303


def test_authenticated_api_lead_intake_creates_operational_workflow(admin_client):
    payload = {
        "source": "Approved API intake",
        "category": "Security company",
        "city": "Mississauga",
        "context": "Distribution centre needs urgent coverage this week",
        "budget": 11000,
        "owner": "Unassigned",
    }
    response = admin_client.post("/api/leads/intake", json=payload)
    lead = response.json()["lead"]
    tasks = admin_client.get("/api/tasks").json()

    assert response.status_code == 200
    assert lead["priority"] == "High"
    assert lead["client_name"] == "ShieldPoint Security"
    assert any(task["lead_id"] == lead["id"] for task in tasks)


def test_webhook_lead_intake_requires_token(client):
    payload = {
        "category": "Cleaning service",
        "city": "Toronto",
        "context": "Office needs recurring cleaning quote",
        "budget": 1500,
    }

    assert client.post("/webhooks/n8n/leads", json=payload).status_code == 401
    accepted = client.post("/webhooks/n8n/leads", json=payload, headers={"Authorization": "Bearer local-webhook-token"})

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"


def test_integrations_page_and_import_history(admin_client):
    page = admin_client.get("/integrations")
    api = admin_client.get("/api/integrations")
    imports = admin_client.get("/api/imports")
    template = admin_client.get("/templates/google-sheets-leads.csv")

    assert page.status_code == 200
    assert "Operational now" in page.text
    assert api.json()["connected"]
    assert imports.status_code == 200
    assert "source,category,city,context,budget" in template.text
