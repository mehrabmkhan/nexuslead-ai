from __future__ import annotations

import json
import os
import time
from http.cookiejar import CookieJar
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE_URL = os.environ.get("NEXUSLEAD_LIVE_URL", "https://99-79-66-16.sslip.io").rstrip("/")


class Session:
    def __init__(self) -> None:
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def get(self, path: str) -> tuple[int, str]:
        with self.opener.open(BASE_URL + path, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")

    def post(self, path: str, data: dict[str, str]) -> tuple[int, str]:
        request = Request(BASE_URL + path, data=urlencode(data).encode("utf-8"), method="POST")
        with self.opener.open(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def login(email: str, password: str) -> Session:
    session = Session()
    session.post("/login", {"email": email, "password": password})
    status, body = session.get("/api/auth/me")
    require(status == 200 and email in body, f"login failed for {email}")
    return session


def json_get(session: Session, path: str):
    status, body = session.get(path)
    require(status == 200, f"{path} returned {status}")
    return json.loads(body)


def main() -> None:
    marker = str(int(time.time()))
    anon = Session()
    for path in ["/", "/login", "/health", "/docs"]:
        status, body = anon.get(path)
        require(status == 200, f"{path} returned {status}")
        if path == "/health":
            require(json.loads(body)["status"] == "ready", "/health is not ready")

    admin = login("admin@nextrns.local", "admin123")
    manager = login("manager@nextrns.local", "manager123")
    agent = login("agent@nextrns.local", "agent123")

    for session, label in [(admin, "admin"), (manager, "manager"), (agent, "agent")]:
        status, body = session.get("/dashboard")
        require(status == 200 and "NexusLead AI" in body, f"{label} dashboard failed")

    client_name = f"Live Acceptance Client {marker}"
    admin.post(
        "/clients",
        {
            "name": client_name,
            "category": "Carpenter",
            "city": "Toronto",
            "service_area": "Toronto",
            "min_budget": "100",
            "max_budget": "6000",
            "contact_email": "ops+acceptance@nextrns.local",
            "notes": "Live acceptance verification client",
        },
    )
    clients = json_get(admin, "/api/clients")
    require(any(client["name"] == client_name for client in clients), "client creation failed")

    context = f"Live acceptance lead {marker}"
    admin.post(
        "/leads",
        {
            "source": "Manual intake",
            "category": "Carpenter",
            "city": "Toronto",
            "context": context,
            "budget": "3500",
            "owner": "Unassigned",
            "due_date": "",
        },
    )
    leads = json_get(admin, "/api/leads")
    lead = next((item for item in leads if item["context"] == context), None)
    require(lead is not None, "lead creation failed")
    require(int(lead["score"]) > 0, "lead scoring failed")
    require(lead["matched_client"], "client matching failed")

    lead_id = str(lead["id"])
    manager.post(f"/leads/{lead_id}/assign", {"owner": "Lead Operations Agent"})
    manager.post(f"/leads/{lead_id}/approve", {})
    agent.post(f"/leads/{lead_id}/status", {"status": "Follow-up", "note": "Live acceptance status change"})

    tasks = json_get(agent, "/api/tasks")
    if tasks:
        agent.post(f"/tasks/{tasks[0]['id']}/close", {})

    for path in ["/api/analytics", "/reports/daily", "/export/leads.csv", "/export/google-sheets.csv", "/export/tasks.csv"]:
        status, body = admin.get(path)
        require(status == 200 and body, f"{path} failed")

    print(f"NEXUSLEAD_LIVE_ACCEPTANCE_OK lead_id={lead_id} marker={marker}")


if __name__ == "__main__":
    main()
