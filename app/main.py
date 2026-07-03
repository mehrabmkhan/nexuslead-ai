from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates

from .database import initialize_database
from .services import (
    analytics,
    daily_report,
    discover_demo_leads,
    export_csv,
    get_dashboard_data,
    seed_reviews,
)


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def bootstrap_demo_data() -> None:
    initialize_database(seed=True)
    discover_demo_leads()
    seed_reviews()


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap_demo_data()
    yield


app = FastAPI(title="NexusLead AI", version="0.1.0", lifespan=lifespan)


@app.get("/")
def health() -> dict:
    return {
        "product": "NexusLead AI",
        "status": "ready",
        "compliance": "synthetic demo data only; human approval required before outreach",
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    client_id: str | None = Query(default=None),
    city: str | None = Query(default=None),
    category: str | None = Query(default=None),
    priority: str | None = Query(default=None),
) -> HTMLResponse:
    data = get_dashboard_data(
        {"client_id": client_id, "city": city, "category": category, "priority": priority}
    )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            **data,
            "filters": {"client_id": client_id, "city": city, "category": category, "priority": priority},
        },
    )


@app.post("/demo/discover")
def run_discovery() -> dict:
    created = discover_demo_leads()
    return {"created": len(created), "message": "Synthetic lead discovery completed"}


@app.get("/api/leads")
def api_leads() -> list[dict]:
    return get_dashboard_data({})["leads"]


@app.get("/api/analytics")
def api_analytics() -> dict:
    return analytics()


@app.get("/export/leads.csv")
def export_leads() -> Response:
    return Response(
        content=export_csv("leads"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@app.get("/export/tasks.csv")
def export_tasks() -> Response:
    return Response(
        content=export_csv("tasks"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=agent_tasks.csv"},
    )


@app.get("/reports/daily", response_class=PlainTextResponse)
def report_daily() -> str:
    return daily_report()
