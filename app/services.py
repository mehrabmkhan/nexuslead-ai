from __future__ import annotations

import csv
import hashlib
import hmac
import os
from collections import Counter
from datetime import date, timedelta
from io import StringIO
from typing import Iterable

import pandas as pd

from .database import connect, database_summary
from .notifications import notify_outreach_approved


PIPELINE_STATUSES = ["New", "Qualified", "Contacted", "Follow-up", "Converted", "Not Fit"]
ROLES = ["admin", "manager", "agent"]
REQUIRED_LEAD_COLUMNS = {"source", "category", "city", "context", "budget"}

INTAKE_RECORDS = [
    {
        "source": "Manual intake",
        "context": "Facilities manager requested warehouse security coverage in Mississauga this month",
        "category": "Security company",
        "city": "Mississauga",
        "budget": 9000,
        "owner": "Lead Operations Agent",
    },
    {
        "source": "CRM import",
        "context": "Property manager needs recurring cleaning service near Markham starting next week",
        "category": "Cleaning service",
        "city": "Markham",
        "budget": 1800,
        "owner": "Lead Operations Agent",
    },
    {
        "source": "Google Sheets import",
        "context": "Homeowner requested custom cabinetry quote in Etobicoke for kitchen remodel",
        "category": "Custom cabinetry",
        "city": "Etobicoke",
        "budget": 18000,
        "owner": "Lead Operations Agent",
    },
    {
        "source": "Approved directory",
        "context": "Retail operator needs a carpenter in Scarborough after water damage",
        "category": "Carpenter",
        "city": "Scarborough",
        "budget": 6500,
        "owner": "Lead Operations Agent",
    },
    {
        "source": "Manual intake",
        "context": "First-time buyer asked for a real estate agent in Scarborough",
        "category": "Real estate agent",
        "city": "Scarborough",
        "budget": 1200,
        "owner": "Lead Operations Agent",
    },
]

TONE_TEMPLATES = {
    "professional": "Hello, we reviewed your request for {category_lower} support in {city}. A NextRNS client may be a fit. Would you like us to prepare a short introduction for approval?",
    "friendly": "Hi, it sounds like you are looking for help with {category_lower} work in {city}. We can suggest a vetted local option if you are still looking.",
    "short": "Hi, we may know a suitable {category_lower} option in {city}. Would you like an introduction?",
    "formal": "Hello, based on your request for {category_lower} services in {city}, NextRNS can prepare a reviewed provider introduction for approval.",
}


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or os.urandom(12).hex()
    iterations = 200_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, digest = encoded.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(candidate, digest)


def row(query: str, params: Iterable = ()) -> dict | None:
    with connect() as connection:
        found = connection.execute(query, tuple(params)).fetchone()
        return dict(found) if found else None


def rows(query: str, params: Iterable = ()) -> list[dict]:
    with connect() as connection:
        return [dict(item) for item in connection.execute(query, tuple(params)).fetchall()]


def audit_log(actor: str, action: str, entity_type: str, entity_id: int | None, detail: str) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO audit_logs (actor, action, entity_type, entity_id, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (actor, action, entity_type, entity_id, detail),
        )
        connection.commit()


def authenticate(email: str, password: str) -> dict | None:
    user = row("SELECT * FROM users WHERE lower(email) = lower(?) AND active = TRUE", (email.strip(),))
    if user and verify_password(password, user["password_hash"]):
        audit_log(user["name"], "auth.login", "user", user["id"], "User signed in")
        return user
    return None


def list_users(active_only: bool = True) -> list[dict]:
    where = "WHERE active = TRUE" if active_only else ""
    return rows(f"SELECT id, email, name, role, active, created_at FROM users {where} ORDER BY role, name")


def create_user(payload: dict, actor: str) -> int:
    role = payload["role"].strip().lower()
    if role not in ROLES:
        raise ValueError("Unsupported role")
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO users (email, name, role, password_hash, active)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                payload["email"].strip().lower(),
                payload["name"].strip(),
                role,
                hash_password(payload.get("password") or "changeme123"),
                True,
            ),
        )
        user_id = int(cursor.lastrowid)
        connection.commit()
    audit_log(actor, "user.created", "user", user_id, f"Created {role} user {payload['email']}")
    return user_id


def can_manage_clients(user: dict) -> bool:
    return user["role"] == "admin"


def can_review_leads(user: dict) -> bool:
    return user["role"] in {"admin", "manager"}


def can_export(user: dict, kind: str) -> bool:
    return user["role"] in {"admin", "manager"} or (user["role"] == "agent" and kind == "tasks")


def normalize_lead_payload(payload: dict) -> dict:
    source = str(payload.get("source") or "Manual intake").strip()
    category = str(payload.get("category") or "").strip()
    city = str(payload.get("city") or "").strip()
    context = str(payload.get("context") or payload.get("lead_context") or "").strip()
    try:
        budget = int(payload.get("budget") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Budget must be a whole number") from exc
    if not category:
        raise ValueError("Category is required")
    if not city:
        raise ValueError("City is required")
    if not context:
        raise ValueError("Lead context is required")
    if budget < 0:
        raise ValueError("Budget cannot be negative")
    normalized = {
        **payload,
        "source": source,
        "category": category,
        "city": city,
        "context": context,
        "budget": budget,
    }
    return normalized


def duplicate_lead(payload: dict) -> dict | None:
    normalized = normalize_lead_payload(payload)
    return row(
        """
        SELECT id, source, category, city, context, budget, created_at
        FROM leads
        WHERE lower(category) = lower(?)
          AND lower(city) = lower(?)
          AND lower(context) = lower(?)
          AND budget = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (normalized["category"], normalized["city"], normalized["context"], normalized["budget"]),
    )


def classify_priority(urgency: int, fit: int) -> str:
    score = urgency + fit
    if score >= 16:
        return "High"
    if score >= 11:
        return "Medium"
    return "Low"


def urgency_score(text: str) -> int:
    lowered = text.lower()
    score = 5
    if any(word in lowered for word in ["urgent", "asap", "today", "this week", "this month"]):
        score += 3
    if any(word in lowered for word in ["need", "requested", "looking for", "quote", "coverage"]):
        score += 2
    return min(score, 10)


def client_fit_score(category: str, city: str, budget: int, client: dict | None) -> int:
    if not client:
        return 3
    score = 4
    if client["category"].lower() == category.lower():
        score += 3
    if city.lower() in client["service_area"].lower() or city.lower() == client["city"].lower():
        score += 2
    if client["min_budget"] <= budget <= client["max_budget"]:
        score += 1
    return min(score, 10)


def find_client(category: str, city: str, budget: int) -> dict | None:
    candidates = rows("SELECT * FROM clients WHERE status = 'active'")
    ranked = sorted(candidates, key=lambda item: client_fit_score(category, city, budget, item), reverse=True)
    if not ranked:
        return None
    best = ranked[0]
    return best if client_fit_score(category, city, budget, best) >= 5 else None


def build_outreach(category: str, city: str, tone: str = "professional") -> str:
    template = TONE_TEMPLATES.get(tone, TONE_TEMPLATES["professional"])
    return template.format(category_lower=category.lower(), city=city)


def score_lead(category: str, city: str, budget: int, context: str) -> dict:
    client = find_client(category, city, budget)
    urgency = urgency_score(context)
    fit = client_fit_score(category, city, budget, client)
    priority = classify_priority(urgency, fit)
    explanation = (
        f"{priority} priority: urgency {urgency}/10, client fit {fit}/10, "
        f"category {category}, market {city}, budget ${budget:,}."
    )
    return {"client": client, "urgency": urgency, "fit": fit, "priority": priority, "explanation": explanation}


def create_lead(payload: dict, actor: str = "System", detect_duplicate: bool = False) -> int:
    payload = normalize_lead_payload(payload)
    if detect_duplicate:
        existing = duplicate_lead(payload)
        if existing:
            raise ValueError(f"Duplicate lead matches existing lead #{existing['id']}")
    category = payload["category"]
    city = payload["city"]
    context = payload["context"]
    budget = payload["budget"]
    scored = score_lead(category, city, budget, context)
    client = scored["client"]
    status = payload.get("status") or ("Qualified" if scored["priority"] in {"High", "Medium"} else "New")
    owner = payload.get("owner") or "Unassigned"
    next_action = payload.get("next_action") or "Review outreach draft"
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO leads (
                source, category, city, context, urgency, budget, client_fit, priority,
                explanation, matched_client_id, outreach_status, outreach_draft, status,
                notes, next_action, owner, attachment_name, attachment_path, attachment_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("source", "Manual intake"),
                category,
                city,
                context,
                scored["urgency"],
                budget,
                scored["fit"],
                scored["priority"],
                scored["explanation"],
                client["id"] if client else None,
                "Needs approval",
                build_outreach(category, city, payload.get("tone", "professional")),
                status,
                payload.get("notes", ""),
                next_action,
                owner,
                payload.get("attachment_name", ""),
                payload.get("attachment_path", ""),
                payload.get("attachment_type", ""),
            ),
        )
        lead_id = int(cursor.lastrowid)
        due_date = payload.get("due_date") or (date.today() + timedelta(days=1)).isoformat()
        task_label = "Review qualified lead and prepare follow-up" if status == "Qualified" else next_action
        connection.execute(
            """
            INSERT INTO follow_up_tasks (lead_id, client_id, due_date, task, owner, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (lead_id, client["id"] if client else None, due_date, task_label, owner, "Open"),
        )
        connection.execute(
            "INSERT INTO lead_events (lead_id, actor, event_type, note) VALUES (?, ?, ?, ?)",
            (lead_id, actor, "created", f"Lead added from {payload.get('source', 'Manual intake')}.")
        )
        connection.execute(
            "INSERT INTO lead_events (lead_id, actor, event_type, note) VALUES (?, ?, ?, ?)",
            (lead_id, "NexusLead AI", "qualification", scored["explanation"]),
        )
        if client:
            connection.execute(
                "INSERT INTO lead_events (lead_id, actor, event_type, note) VALUES (?, ?, ?, ?)",
                (lead_id, "NexusLead AI", "client_match", f"Recommended {client['name']} for {category} in {city}."),
            )
        connection.execute(
            "INSERT INTO lead_events (lead_id, actor, event_type, note) VALUES (?, ?, ?, ?)",
            (lead_id, "NexusLead AI", "task", f"Created follow-up task due {due_date}."),
        )
        connection.execute(
            """
            INSERT INTO audit_logs (actor, action, entity_type, entity_id, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (actor, "lead.created", "lead", lead_id, f"Created {category} lead in {city}"),
        )
        connection.commit()
    return lead_id


def create_intake_lead(payload: dict, actor: str = "API") -> dict:
    lead_id = create_lead(payload, actor=actor, detect_duplicate=True)
    return row(
        """
        SELECT leads.*, clients.name AS client_name
        FROM leads
        LEFT JOIN clients ON clients.id = leads.matched_client_id
        WHERE leads.id = ?
        """,
        (lead_id,),
    ) or {"id": lead_id}


def seed_operational_records() -> list[int]:
    created: list[int] = []
    for item in INTAKE_RECORDS:
        if row("SELECT id FROM leads WHERE context = ?", (item["context"],)):
            continue
        created.append(create_lead(item, actor="Seed"))
    return created


def record_import_batch(actor: str, source: str, file_name: str, result: dict) -> int:
    summary_parts = [
        f"{result['created']} created",
        f"{result.get('duplicates', 0)} duplicates",
        f"{len(result['errors'])} errors",
    ]
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO import_batches (
                actor, source, file_name, total_rows, created_count,
                duplicate_count, error_count, status, summary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor,
                source,
                file_name,
                result.get("total_rows", 0),
                result["created"],
                result.get("duplicates", 0),
                len(result["errors"]),
                "Completed with errors" if result["errors"] else "Completed",
                ", ".join(summary_parts),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def import_history(limit: int = 10) -> list[dict]:
    return rows("SELECT * FROM import_batches ORDER BY created_at DESC, id DESC LIMIT ?", (limit,))


def import_leads_csv(csv_text: str, actor: str, file_name: str = "") -> dict:
    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames or not REQUIRED_LEAD_COLUMNS.issubset({name.strip() for name in reader.fieldnames}):
        result = {
            "created": 0,
            "duplicates": 0,
            "total_rows": 0,
            "errors": ["CSV must include source, category, city, context, budget columns."],
        }
        result["batch_id"] = record_import_batch(actor, "CSV import", file_name, result)
        return result
    created = 0
    duplicates = 0
    errors: list[str] = []
    total_rows = 0
    for index, item in enumerate(reader, start=2):
        total_rows += 1
        try:
            create_lead(item, actor=actor, detect_duplicate=True)
            created += 1
        except ValueError as exc:
            if "Duplicate lead" in str(exc):
                duplicates += 1
            else:
                errors.append(f"Line {index}: {exc}")
        except Exception as exc:  # pragma: no cover - defensive user input path
            errors.append(f"Line {index}: {exc}")
    result = {"created": created, "duplicates": duplicates, "total_rows": total_rows, "errors": errors}
    result["batch_id"] = record_import_batch(actor, "CSV import", file_name, result)
    return result


def create_client(payload: dict, actor: str = "System") -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO clients (name, category, city, service_area, min_budget, max_budget, contact_email, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["name"].strip(),
                payload["category"].strip(),
                payload["city"].strip(),
                payload["service_area"].strip(),
                int(payload.get("min_budget") or 0),
                int(payload.get("max_budget") or 0),
                payload.get("contact_email", "").strip(),
                payload.get("notes", "").strip(),
                payload.get("status", "active"),
            ),
        )
        client_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO audit_logs (actor, action, entity_type, entity_id, detail) VALUES (?, ?, ?, ?, ?)",
            (actor, "client.created", "client", client_id, f"Created client {payload['name']}"),
        )
        connection.commit()
    return client_id


def update_lead_status(lead_id: int, status: str, note: str, actor: str) -> None:
    if status not in PIPELINE_STATUSES:
        raise ValueError("Unsupported lead status")
    lead = row("SELECT notes FROM leads WHERE id = ?", (lead_id,))
    existing_notes = lead["notes"] if lead else ""
    updated_notes = "\n".join(item for item in [existing_notes, note] if item).strip()
    with connect() as connection:
        connection.execute(
            "UPDATE leads SET status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, updated_notes, lead_id),
        )
        connection.execute(
            "INSERT INTO lead_events (lead_id, actor, event_type, note) VALUES (?, ?, ?, ?)",
            (lead_id, actor, "status", f"{status}: {note}" if note else f"Status changed to {status}"),
        )
        connection.execute(
            "INSERT INTO audit_logs (actor, action, entity_type, entity_id, detail) VALUES (?, ?, ?, ?, ?)",
            (actor, "lead.status_changed", "lead", lead_id, f"Status changed to {status}"),
        )
        connection.commit()


def assign_lead(lead_id: int, owner: str, actor: str) -> None:
    with connect() as connection:
        connection.execute("UPDATE leads SET owner = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (owner, lead_id))
        connection.execute(
            "UPDATE follow_up_tasks SET owner = ? WHERE lead_id = ? AND status != 'Closed'",
            (owner, lead_id),
        )
        connection.execute(
            "INSERT INTO lead_events (lead_id, actor, event_type, note) VALUES (?, ?, ?, ?)",
            (lead_id, actor, "assignment", f"Assigned to {owner}"),
        )
        connection.execute(
            "INSERT INTO audit_logs (actor, action, entity_type, entity_id, detail) VALUES (?, ?, ?, ?, ?)",
            (actor, "lead.assigned", "lead", lead_id, f"Assigned to {owner}"),
        )
        connection.commit()


def approve_outreach(lead_id: int, actor: str) -> None:
    lead = row(
        """
        SELECT leads.*, clients.contact_email, clients.name AS client_name
        FROM leads LEFT JOIN clients ON clients.id = leads.matched_client_id
        WHERE leads.id = ?
        """,
        (lead_id,),
    )
    with connect() as connection:
        connection.execute(
            "UPDATE leads SET outreach_status = 'Approved', status = 'Contacted', next_action = 'Send through approved channel', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (lead_id,),
        )
        connection.execute(
            "INSERT INTO lead_events (lead_id, actor, event_type, note) VALUES (?, ?, ?, ?)",
            (lead_id, actor, "approval", "Outreach draft approved for use in an approved workflow."),
        )
        connection.execute(
            "INSERT INTO audit_logs (actor, action, entity_type, entity_id, detail) VALUES (?, ?, ?, ?, ?)",
            (actor, "outreach.approved", "lead", lead_id, "Human-reviewed draft approved"),
        )
        connection.commit()
    if lead and lead.get("contact_email"):
        notify_outreach_approved(lead["contact_email"], f"{lead['category']} lead in {lead['city']}")


def attach_file_metadata(lead_id: int, file_name: str, content_type: str, storage_path: str, actor: str) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO lead_attachments (lead_id, file_name, content_type, storage_path, uploaded_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (lead_id, file_name, content_type, storage_path, actor),
        )
        attachment_id = int(cursor.lastrowid)
        connection.execute(
            """
            UPDATE leads SET attachment_name = ?, attachment_path = ?, attachment_type = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (file_name, storage_path, content_type, lead_id),
        )
        connection.execute(
            "INSERT INTO lead_events (lead_id, actor, event_type, note) VALUES (?, ?, ?, ?)",
            (lead_id, actor, "attachment", f"Attached metadata for {file_name}"),
        )
        connection.execute(
            "INSERT INTO audit_logs (actor, action, entity_type, entity_id, detail) VALUES (?, ?, ?, ?, ?)",
            (actor, "lead.attachment_added", "lead", lead_id, file_name),
        )
        connection.commit()
    return attachment_id


def close_task(task_id: int, actor: str) -> None:
    with connect() as connection:
        task = connection.execute("SELECT lead_id FROM follow_up_tasks WHERE id = ?", (task_id,)).fetchone()
        connection.execute("UPDATE follow_up_tasks SET status = 'Closed' WHERE id = ?", (task_id,))
        if task:
            connection.execute(
                "INSERT INTO lead_events (lead_id, actor, event_type, note) VALUES (?, ?, ?, ?)",
                (task["lead_id"], actor, "task", f"Closed task {task_id}"),
            )
        connection.execute(
            "INSERT INTO audit_logs (actor, action, entity_type, entity_id, detail) VALUES (?, ?, ?, ?, ?)",
            (actor, "task.closed", "task", task_id, "Follow-up task closed"),
        )
        connection.commit()


def schedule_task(task_id: int, due_date: str, actor: str) -> None:
    if not due_date:
        raise ValueError("Due date is required")
    with connect() as connection:
        task = connection.execute("SELECT lead_id FROM follow_up_tasks WHERE id = ?", (task_id,)).fetchone()
        connection.execute("UPDATE follow_up_tasks SET due_date = ? WHERE id = ?", (due_date, task_id))
        if task:
            connection.execute(
                "INSERT INTO lead_events (lead_id, actor, event_type, note) VALUES (?, ?, ?, ?)",
                (task["lead_id"], actor, "task", f"Follow-up task {task_id} rescheduled to {due_date}"),
            )
        connection.execute(
            "INSERT INTO audit_logs (actor, action, entity_type, entity_id, detail) VALUES (?, ?, ?, ?, ?)",
            (actor, "task.rescheduled", "task", task_id, f"Due {due_date}"),
        )
        connection.commit()


def create_review_response(client_id: int, rating: int, text: str, source: str = "Client feedback") -> int:
    sentiment = classify_sentiment(rating, text)
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO reviews (client_id, source, rating, text, sentiment, response_draft, attention_required)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (client_id, source, rating, text, sentiment, draft_review_response(sentiment), sentiment == "negative"),
        )
        connection.commit()
        return int(cursor.lastrowid)


def seed_reviews() -> None:
    if row("SELECT id FROM reviews LIMIT 1"):
        return
    reviews = [
        (1, "Client feedback", 5, "Great carpentry work and clear communication."),
        (2, "Client feedback", 4, "Helpful agent and responsive follow-up."),
        (3, "Client feedback", 2, "Slow response on a weekend security issue."),
        (4, "Client feedback", 5, "Excellent cabinet finish and installation."),
        (5, "Client feedback", 3, "Cleaning was good but scheduling was confusing."),
    ]
    for client_id, source, rating, text in reviews:
        create_review_response(client_id, rating, text, source)


def classify_sentiment(rating: int, text: str) -> str:
    lowered = text.lower()
    if rating <= 2 or any(word in lowered for word in ["slow", "bad", "poor", "confusing"]):
        return "negative"
    if rating == 3:
        return "neutral"
    return "positive"


def draft_review_response(sentiment: str) -> str:
    if sentiment == "negative":
        return "Thank you for the feedback. A NextRNS team member will review the details and follow up with a specific resolution."
    if sentiment == "neutral":
        return "Thank you for sharing this. We will review the experience and identify the next improvement step."
    return "Thank you for the kind feedback. We appreciate the opportunity to support your project."


def _lead_where(filters: dict[str, str | None], user: dict | None = None) -> tuple[str, list[str]]:
    where = []
    params: list[str] = []
    if user and user["role"] == "agent":
        where.append("(leads.owner = ? OR leads.owner = 'Unassigned')")
        params.append(user["name"])
    if filters.get("client_id"):
        where.append("leads.matched_client_id = ?")
        params.append(str(filters["client_id"]))
    if filters.get("city"):
        where.append("leads.city = ?")
        params.append(str(filters["city"]))
    if filters.get("category"):
        where.append("leads.category = ?")
        params.append(str(filters["category"]))
    if filters.get("priority"):
        where.append("leads.priority = ?")
        params.append(str(filters["priority"]))
    if filters.get("status"):
        where.append("leads.status = ?")
        params.append(str(filters["status"]))
    return ("WHERE " + " AND ".join(where) if where else "", params)


def get_dashboard_data(filters: dict[str, str | None], user: dict | None = None) -> dict:
    where_sql, params = _lead_where(filters, user)
    lead_rows = rows(
        f"""
        SELECT leads.*, clients.name AS client_name, clients.contact_email AS client_contact_email
        FROM leads
        LEFT JOIN clients ON clients.id = leads.matched_client_id
        {where_sql}
        ORDER BY CASE leads.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, leads.created_at DESC
        """,
        params,
    )
    task_where = "WHERE follow_up_tasks.status != 'Closed'"
    task_params: list[str] = []
    if user and user["role"] == "agent":
        task_where += " AND follow_up_tasks.owner = ?"
        task_params.append(user["name"])
    return {
        "leads": lead_rows,
        "clients": rows("SELECT * FROM clients ORDER BY name"),
        "users": list_users(),
        "tasks": rows(
            f"""
            SELECT follow_up_tasks.*, leads.context, leads.priority, clients.name AS client_name
            FROM follow_up_tasks
            LEFT JOIN leads ON leads.id = follow_up_tasks.lead_id
            LEFT JOIN clients ON clients.id = follow_up_tasks.client_id
            {task_where}
            ORDER BY due_date ASC
            """,
            task_params,
        ),
        "reviews": rows(
            """
            SELECT reviews.*, clients.name AS client_name
            FROM reviews
            LEFT JOIN clients ON clients.id = reviews.client_id
            ORDER BY attention_required DESC, rating ASC
            """
        ),
        "lead_events": rows(
            """
            SELECT lead_events.*, leads.category, leads.city
            FROM lead_events
            LEFT JOIN leads ON leads.id = lead_events.lead_id
            ORDER BY lead_events.created_at DESC
            LIMIT 20
            """
        ),
        "audit_logs": rows("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 20"),
        "approval_queue": rows(
            """
            SELECT leads.*, clients.name AS client_name
            FROM leads
            LEFT JOIN clients ON clients.id = leads.matched_client_id
            WHERE leads.outreach_status = 'Needs approval'
            ORDER BY CASE leads.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, leads.created_at DESC
            LIMIT 10
            """
        ),
        "import_history": import_history(),
        "integrations": integration_status(),
        "analytics": analytics(user),
        "pipeline_statuses": PIPELINE_STATUSES,
        "roles": ROLES,
    }


def analytics(user: dict | None = None) -> dict:
    if user and user["role"] == "agent":
        lead_rows = rows("SELECT * FROM leads WHERE owner = ? OR owner = 'Unassigned'", (user["name"],))
        tasks = rows("SELECT * FROM follow_up_tasks WHERE status != 'Closed' AND owner = ?", (user["name"],))
    else:
        lead_rows = rows("SELECT * FROM leads")
        tasks = rows("SELECT * FROM follow_up_tasks WHERE status != 'Closed'")
    status_counts = Counter(item["status"] for item in lead_rows)
    category_counts = Counter(item["category"] for item in lead_rows)
    city_counts = Counter(item["city"] for item in lead_rows)
    high_priority = [item for item in lead_rows if item["priority"] == "High"]
    converted = status_counts.get("Converted", 0)
    conversion_rate = round((converted / len(lead_rows)) * 100, 1) if lead_rows else 0
    return {
        "daily_lead_count": len(lead_rows),
        "leads_by_category": dict(category_counts),
        "leads_by_city": dict(city_counts),
        "high_priority_leads": len(high_priority),
        "follow_up_queue": len(tasks),
        "estimated_opportunity_value": sum(int(item["budget"]) for item in lead_rows),
        "conversion_status_summary": dict(status_counts),
        "conversion_rate": conversion_rate,
        "database": database_summary(),
    }


def dataframe_for(query: str, params: Iterable = ()) -> pd.DataFrame:
    return pd.DataFrame(rows(query, params))


def export_csv(kind: str, user: dict | None = None) -> str:
    audit_actor = user["name"] if user else "System"
    if kind == "tasks":
        where = ""
        params: list[str] = []
        if user and user["role"] == "agent":
            where = "WHERE follow_up_tasks.owner = ?"
            params.append(user["name"])
        frame = dataframe_for(
            f"""
            SELECT follow_up_tasks.id, follow_up_tasks.due_date, follow_up_tasks.task,
                   follow_up_tasks.owner, follow_up_tasks.status, leads.context, clients.name AS client_name
            FROM follow_up_tasks
            LEFT JOIN leads ON leads.id = follow_up_tasks.lead_id
            LEFT JOIN clients ON clients.id = follow_up_tasks.client_id
            {where}
            ORDER BY follow_up_tasks.due_date
            """,
            params,
        )
    else:
        frame = dataframe_for(
            """
            SELECT leads.id, leads.source, leads.category, leads.city, leads.context, leads.urgency,
                   leads.client_fit, leads.priority, leads.status, leads.owner, clients.name AS client_name,
                   leads.outreach_status, leads.outreach_draft, leads.next_action, leads.notes,
                   leads.attachment_name, leads.created_at, leads.updated_at
            FROM leads
            LEFT JOIN clients ON clients.id = leads.matched_client_id
            ORDER BY leads.priority
            """
        )
    audit_log(audit_actor, "export.generated", "export", None, f"Generated {kind} CSV")
    buffer = StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue()


def google_sheets_csv(user: dict | None = None) -> str:
    return export_csv("leads", user)


def google_sheets_template_csv() -> str:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["source", "category", "city", "context", "budget", "owner", "due_date", "notes"])
    writer.writeheader()
    writer.writerow(
        {
            "source": "Google Sheets import",
            "category": "Security company",
            "city": "Mississauga",
            "context": "Warehouse manager needs urgent overnight coverage this week",
            "budget": "9000",
            "owner": "Unassigned",
            "due_date": (date.today() + timedelta(days=1)).isoformat(),
            "notes": "Approved intake source; review before outreach.",
        }
    )
    return buffer.getvalue()


def daily_report(user: dict | None = None) -> str:
    data = analytics(user)
    lines = [
        "# NexusLead AI daily report",
        "",
        f"- Daily lead count: {data['daily_lead_count']}",
        f"- High priority leads: {data['high_priority_leads']}",
        f"- Follow-up queue: {data['follow_up_queue']}",
        f"- Estimated opportunity value: ${data['estimated_opportunity_value']:,}",
        f"- Conversion rate: {data['conversion_rate']}%",
        "",
        "## Leads by category",
        "",
    ]
    for category, count in data["leads_by_category"].items():
        lines.append(f"- {category}: {count}")
    lines.extend(["", "## Pipeline status", ""])
    for status, count in data["conversion_status_summary"].items():
        lines.append(f"- {status}: {count}")
    return "\n".join(lines)


def integration_status() -> dict:
    webhook_token_configured = bool(os.getenv("NEXUSLEAD_WEBHOOK_TOKEN") or os.getenv("NEXUSLEAD_API_KEY"))
    return {
        "connected": [
            {
                "name": "Manual lead intake",
                "status": "Operational",
                "detail": "Dashboard form writes qualified leads, client recommendations, outreach drafts, tasks, and activity history.",
            },
            {
                "name": "CSV bulk import",
                "status": "Operational",
                "detail": "Validated upload with duplicate detection and import history.",
            },
            {
                "name": "Google Sheets CSV workflow",
                "status": "Operational",
                "detail": "Sheets-ready template, upload path, and export are available without direct Google account connection.",
            },
            {
                "name": "Session-authenticated API intake",
                "status": "Operational",
                "detail": "POST /api/leads/intake accepts JSON for signed-in Admin, Manager, and Agent users.",
            },
            {
                "name": "n8n webhook endpoint",
                "status": "Operational" if webhook_token_configured else "Configuration required",
                "detail": "POST /webhooks/n8n/leads accepts JSON with a Bearer token. Configure NEXUSLEAD_WEBHOOK_TOKEN for external workflows.",
            },
        ],
        "future": [
            {
                "name": "Direct Google Sheets API sync",
                "status": "Future integration",
                "detail": "Use OAuth or a service account only after an approved Google Cloud setup exists.",
            },
            {
                "name": "CRM imports",
                "status": "Future integration",
                "detail": "Connect approved CRMs through official APIs or scheduled CSV exports.",
            },
            {
                "name": "Outbound sending",
                "status": "Future integration",
                "detail": "Drafts remain human-approved; sending should use approved email/CRM tools with audit logging.",
            },
        ],
    }
