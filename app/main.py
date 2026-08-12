from __future__ import annotations

import base64
import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .background import scheduler_status
from .database import database_health, initialize_database
from .services import (
    analytics,
    approve_outreach,
    assign_lead,
    attach_file_metadata,
    audit_log,
    authenticate,
    can_export,
    can_manage_clients,
    can_review_leads,
    close_task,
    create_client,
    create_lead,
    create_review_response,
    create_user,
    daily_report,
    export_csv,
    get_dashboard_data,
    google_sheets_template_csv,
    import_leads_csv,
    import_history,
    integration_status,
    list_users,
    row,
    rows,
    schedule_task,
    seed_operational_records,
    seed_reviews,
    create_intake_lead,
    discover_from_rss,
    update_lead_status,
)


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.getenv("NEXUSLEAD_UPLOAD_DIR", "uploads"))
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
SESSION_COOKIE = "nexuslead_session"
SECURE_COOKIES = os.getenv("NEXUSLEAD_SECURE_COOKIES", "").lower() in {"1", "true", "yes", "on"}
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("nexuslead")


def bootstrap_data() -> None:
    initialize_database(seed=True)
    seed_operational_records()
    seed_reviews()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap_data()
    yield


app = FastAPI(
    title="NexusLead AI",
    version="1.2.2",
    description="Internal B2B lead operations platform for NextRNS-style BPO teams.",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "auth", "description": "Session authentication and current user context"},
        {"name": "leads", "description": "Lead intake, pipeline, assignment, notes, and approvals"},
        {"name": "clients", "description": "Multi-tenant client profiles and matching"},
        {"name": "tasks", "description": "Follow-up task queues and due dates"},
        {"name": "analytics", "description": "Operating metrics and reports"},
        {"name": "exports", "description": "CSV and Google Sheets-ready exports"},
        {"name": "integrations", "description": "Operational intake and integration readiness"},
        {"name": "monitoring", "description": "Health, metrics, and background job readiness"},
    ],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception("request_failed method=%s path=%s elapsed_ms=%s", request.method, request.url.path, elapsed_ms)
        raise
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "request_complete method=%s path=%s status=%s elapsed_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


def session_secret() -> str:
    return os.getenv("NEXUSLEAD_SESSION_SECRET", "local-development-secret")


def sign_session(user_id: int) -> str:
    payload = str(user_id)
    signature = hmac.new(session_secret().encode(), payload.encode(), sha256).hexdigest()
    token = f"{payload}:{signature}".encode()
    return base64.urlsafe_b64encode(token).decode()


def read_session(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, signature = decoded.split(":", 1)
    except Exception:
        return None
    expected = hmac.new(session_secret().encode(), user_id.encode(), sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return row("SELECT id, email, name, role, active FROM users WHERE id = ? AND active = TRUE", (user_id,))


def current_user(request: Request) -> dict:
    user = read_session(request.cookies.get(SESSION_COOKIE))
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def admin_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def reviewer_user(user: dict = Depends(current_user)) -> dict:
    if not can_review_leads(user):
        raise HTTPException(status_code=403, detail="Manager or admin role required")
    return user


def webhook_token() -> str:
    return os.getenv("NEXUSLEAD_WEBHOOK_TOKEN") or os.getenv("NEXUSLEAD_API_KEY") or "local-webhook-token"


def webhook_actor(
    authorization: str | None = Header(default=None),
    x_nexuslead_token: str | None = Header(default=None),
) -> str:
    expected = webhook_token()
    supplied = x_nexuslead_token or ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization.split(" ", 1)[1].strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Valid webhook token required")
    return "n8n webhook"


def export_user(kind: str, user: dict) -> dict:
    if not can_export(user, kind):
        raise HTTPException(status_code=403, detail="Export is not available for this role")
    return user


def no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def health_payload() -> dict:
    database = database_health()
    return {
        "product": "NexusLead AI",
        "platform": "Internal B2B lead operations platform for NextRNS-style BPO teams",
        "status": "ready" if database["status"] == "ok" else "degraded",
        "database": database,
    }


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def product_entry(request: Request):
    if read_session(request.cookies.get(SESSION_COOKIE)):
        return no_store(RedirectResponse("/dashboard", status_code=303))
    return no_store(templates.TemplateResponse(request, "login.html", {"error": None}))


@app.get("/health", tags=["monitoring"])
def health_check() -> dict:
    return health_payload()


@app.get("/metrics", tags=["monitoring"])
def metrics() -> dict:
    data = analytics()
    return {
        "nexuslead_leads_total": data["daily_lead_count"],
        "nexuslead_high_priority_leads": data["high_priority_leads"],
        "nexuslead_follow_up_queue": data["follow_up_queue"],
        "nexuslead_conversion_rate": data["conversion_rate"],
    }


@app.get("/jobs/status", tags=["monitoring"])
def jobs_status(user: dict = Depends(admin_user)) -> dict:
    return scheduler_status()


@app.get("/integrations", response_class=HTMLResponse, tags=["integrations"])
def integrations_page(request: Request, user: dict = Depends(current_user)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "integrations.html",
        {"user": user, "integrations": integration_status(), "message": request.query_params.get("message")},
    )


@app.get("/login", response_class=HTMLResponse, tags=["auth"])
def login_page(request: Request, error: str | None = None) -> HTMLResponse:
    return no_store(templates.TemplateResponse(request, "login.html", {"error": error}))


@app.post("/login", tags=["auth"])
def login(email: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    user = authenticate(email, password)
    if not user:
        return RedirectResponse("/login?error=Invalid+credentials", status_code=303)
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(SESSION_COOKIE, sign_session(user["id"]), httponly=True, samesite="lax", secure=SECURE_COOKIES)
    return response


@app.post("/logout", tags=["auth"])
def logout(user: dict = Depends(current_user)) -> RedirectResponse:
    audit_log(user["name"], "auth.logout", "user", user["id"], "User signed out")
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/api/auth/me", tags=["auth"])
def api_me(user: dict = Depends(current_user)) -> dict:
    return user


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    client_id: str | None = Query(default=None),
    city: str | None = Query(default=None),
    category: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    status: str | None = Query(default=None),
    user: dict = Depends(current_user),
) -> HTMLResponse:
    data = get_dashboard_data(
        {"client_id": client_id, "city": city, "category": category, "priority": priority, "status": status},
        user,
    )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            **data,
            "user": user,
            "can_manage_clients": can_manage_clients(user),
            "can_review_leads": can_review_leads(user),
            "can_export_leads": can_export(user, "leads"),
            "filters": {"client_id": client_id, "city": city, "category": category, "priority": priority, "status": status},
            "message": request.query_params.get("message"),
        },
    )


@app.post("/leads", tags=["leads"])
def add_lead(
    source: str = Form("Manual intake"),
    category: str = Form(...),
    city: str = Form(...),
    context: str = Form(...),
    budget: int = Form(0),
    owner: str = Form("Unassigned"),
    due_date: str = Form(""),
    user: dict = Depends(current_user),
) -> RedirectResponse:
    chosen_owner = user["name"] if user["role"] == "agent" else owner
    try:
        create_lead(
            {"source": source, "category": category, "city": city, "context": context, "budget": budget, "owner": chosen_owner, "due_date": due_date or None},
            actor=user["name"],
        )
    except ValueError as exc:
        return RedirectResponse(f"/dashboard?message={str(exc).replace(' ', '+')}", status_code=303)
    return RedirectResponse("/dashboard?message=Lead+created", status_code=303)


@app.post("/leads/import", tags=["leads"])
async def import_leads(file: UploadFile = File(...), user: dict = Depends(current_user)) -> RedirectResponse:
    content = (await file.read()).decode("utf-8-sig")
    result = import_leads_csv(content, user["name"], file.filename or "")
    if result["errors"]:
        message = result["errors"][0].replace(" ", "+")
    else:
        message = f"{result['created']}+created,+{result['duplicates']}+duplicates,+batch+{result['batch_id']}"
    return RedirectResponse(f"/dashboard?message={message}", status_code=303)


@app.post("/api/leads/intake", tags=["leads"])
def api_lead_intake(payload: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    lead = create_intake_lead(payload, actor=user["name"])
    return {"status": "created", "lead": lead}


@app.post("/webhooks/n8n/leads", tags=["integrations"])
def n8n_lead_webhook(payload: dict = Body(...), actor: str = Depends(webhook_actor)) -> dict:
    lead = create_intake_lead({**payload, "source": payload.get("source") or "n8n webhook"}, actor=actor)
    return {"status": "accepted", "lead": lead}


@app.post("/api/discovery/opportunities", tags=["leads"])
def api_discovery_opportunity(payload: dict = Body(...), actor: str = Depends(webhook_actor)) -> dict:
    lead = create_intake_lead({**payload, "source": payload.get("source") or "Authorized discovery API"}, actor=actor)
    return {"status": "accepted", "opportunity": lead}


@app.post("/api/discovery/rss", tags=["integrations"])
def api_discovery_rss(payload: dict = Body(...), user: dict = Depends(reviewer_user)) -> dict:
    feed_url = str(payload.get("feed_url") or "").strip()
    if not feed_url:
        raise HTTPException(status_code=400, detail="feed_url is required")
    try:
        return discover_from_rss(feed_url, actor=user["name"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/leads/{lead_id}/status", tags=["leads"])
def change_status(
    lead_id: int,
    status: str = Form(...),
    note: str = Form(""),
    user: dict = Depends(current_user),
) -> RedirectResponse:
    update_lead_status(lead_id, status, note, user["name"])
    return RedirectResponse("/dashboard?message=Lead+updated", status_code=303)


@app.post("/leads/{lead_id}/assign", tags=["leads"])
def assign(lead_id: int, owner: str = Form(...), user: dict = Depends(reviewer_user)) -> RedirectResponse:
    assign_lead(lead_id, owner, user["name"])
    return RedirectResponse("/dashboard?message=Lead+assigned", status_code=303)


@app.post("/leads/{lead_id}/approve", tags=["leads"])
def approve(lead_id: int, user: dict = Depends(reviewer_user)) -> RedirectResponse:
    approve_outreach(lead_id, user["name"])
    return RedirectResponse("/dashboard?message=Outreach+approved", status_code=303)


@app.post("/leads/{lead_id}/attachments", tags=["leads"])
async def attach_file(lead_id: int, file: UploadFile = File(...), user: dict = Depends(current_user)) -> RedirectResponse:
    safe_name = Path(file.filename or "attachment").name
    storage_path = UPLOAD_DIR / f"lead-{lead_id}-{safe_name}"
    content = await file.read()
    storage_path.write_bytes(content)
    attach_file_metadata(lead_id, safe_name, file.content_type or "application/octet-stream", str(storage_path), user["name"])
    return RedirectResponse("/dashboard?message=Attachment+metadata+added", status_code=303)


@app.post("/tasks/{task_id}/close", tags=["tasks"])
def close_follow_up_task(task_id: int, user: dict = Depends(current_user)) -> RedirectResponse:
    close_task(task_id, user["name"])
    return RedirectResponse("/dashboard?message=Task+closed", status_code=303)


@app.post("/tasks/{task_id}/schedule", tags=["tasks"])
def reschedule_follow_up_task(task_id: int, due_date: str = Form(...), user: dict = Depends(current_user)) -> RedirectResponse:
    schedule_task(task_id, due_date, user["name"])
    return RedirectResponse("/dashboard?message=Task+rescheduled", status_code=303)


@app.post("/clients", tags=["clients"])
def add_client(
    name: str = Form(...),
    category: str = Form(...),
    city: str = Form(...),
    service_area: str = Form(...),
    min_budget: int = Form(0),
    max_budget: int = Form(0),
    contact_email: str = Form(""),
    notes: str = Form(""),
    services: str = Form(""),
    target_customer: str = Form(""),
    target_industries: str = Form(""),
    service_categories: str = Form(""),
    keywords: str = Form(""),
    negative_keywords: str = Form("jobs, course, training, diy"),
    preferred_lead_types: str = Form(""),
    outreach_preferences: str = Form("Human-approved draft"),
    qualification_rules: str = Form(""),
    user: dict = Depends(admin_user),
) -> RedirectResponse:
    create_client(
        {
            "name": name,
            "category": category,
            "city": city,
            "service_area": service_area,
            "min_budget": min_budget,
            "max_budget": max_budget,
            "contact_email": contact_email,
            "notes": notes,
            "services": services,
            "target_customer": target_customer,
            "target_industries": target_industries,
            "service_categories": service_categories,
            "keywords": keywords,
            "negative_keywords": negative_keywords,
            "preferred_lead_types": preferred_lead_types,
            "outreach_preferences": outreach_preferences,
            "qualification_rules": qualification_rules,
            "status": "active",
        },
        actor=user["name"],
    )
    return RedirectResponse("/dashboard?message=Client+created", status_code=303)


@app.post("/users", tags=["auth"])
def add_user(
    email: str = Form(...),
    name: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
    user: dict = Depends(admin_user),
) -> RedirectResponse:
    create_user({"email": email, "name": name, "role": role, "password": password}, actor=user["name"])
    return RedirectResponse("/dashboard?message=User+created", status_code=303)


@app.post("/reviews", tags=["clients"])
def add_review(
    client_id: int = Form(...),
    rating: int = Form(...),
    text: str = Form(...),
    source: str = Form("Client feedback"),
    user: dict = Depends(current_user),
) -> RedirectResponse:
    create_review_response(client_id, rating, text, source)
    audit_log(user["name"], "review.response_drafted", "client", client_id, "Review response draft generated")
    return RedirectResponse("/dashboard?message=Review+drafted", status_code=303)


@app.get("/api/leads", tags=["leads"])
def api_leads(user: dict = Depends(current_user)) -> list[dict]:
    return get_dashboard_data({}, user)["leads"]


@app.get("/api/clients", tags=["clients"])
def api_clients(user: dict = Depends(current_user)) -> list[dict]:
    return rows("SELECT * FROM clients ORDER BY name")


@app.get("/api/tasks", tags=["tasks"])
def api_tasks(user: dict = Depends(current_user)) -> list[dict]:
    return get_dashboard_data({}, user)["tasks"]


@app.get("/api/users", tags=["auth"])
def api_users(user: dict = Depends(admin_user)) -> list[dict]:
    return list_users()


@app.get("/api/analytics", tags=["analytics"])
def api_analytics(user: dict = Depends(current_user)) -> dict:
    if user["role"] == "agent":
        return analytics(user)
    return analytics()


@app.get("/api/imports", tags=["integrations"])
def api_import_history(user: dict = Depends(current_user)) -> list[dict]:
    return import_history()


@app.get("/api/integrations", tags=["integrations"])
def api_integrations(user: dict = Depends(current_user)) -> dict:
    return integration_status()


@app.get("/export/leads.csv", tags=["exports"])
def export_leads(user: dict = Depends(current_user)) -> Response:
    export_user("leads", user)
    return Response(
        content=export_csv("leads", user),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@app.get("/export/google-sheets.csv", tags=["exports"])
def export_google_sheets(user: dict = Depends(current_user)) -> Response:
    export_user("leads", user)
    return Response(
        content=export_csv("leads", user),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=nexuslead_google_sheets.csv"},
    )


@app.get("/templates/google-sheets-leads.csv", tags=["exports"])
def google_sheets_template(user: dict = Depends(current_user)) -> Response:
    return Response(
        content=google_sheets_template_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=nexuslead_google_sheets_template.csv"},
    )


@app.get("/export/tasks.csv", tags=["exports"])
def export_tasks(user: dict = Depends(current_user)) -> Response:
    export_user("tasks", user)
    return Response(
        content=export_csv("tasks", user),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=agent_tasks.csv"},
    )


@app.get("/reports/daily", response_class=PlainTextResponse, tags=["analytics"])
def report_daily(user: dict = Depends(current_user)) -> str:
    return daily_report(user)
