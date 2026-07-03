from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from io import StringIO
from typing import Iterable

import pandas as pd

from .database import connect


DEMO_SIGNALS = [
    {
        "source": "Demo community post",
        "text": "Looking for carpenter in Toronto for built-in shelves this month",
        "category": "Carpenter",
        "city": "Toronto",
        "budget": 4500,
    },
    {
        "source": "Demo buyer request",
        "text": "Need real estate agent in Scarborough for first-time buyer",
        "category": "Real estate agent",
        "city": "Scarborough",
        "budget": 1200,
    },
    {
        "source": "Demo operations request",
        "text": "Need security company for warehouse in Mississauga",
        "category": "Security company",
        "city": "Mississauga",
        "budget": 9000,
    },
    {
        "source": "Demo renovation forum",
        "text": "Need custom cabinetry quote in Etobicoke for kitchen remodel",
        "category": "Custom cabinetry",
        "city": "Etobicoke",
        "budget": 18000,
    },
    {
        "source": "Demo local business board",
        "text": "Office needs cleaning service near Markham starting next week",
        "category": "Cleaning service",
        "city": "Markham",
        "budget": 1500,
    },
    {
        "source": "Demo urgent request",
        "text": "Urgent carpenter needed in Scarborough after water damage",
        "category": "Carpenter",
        "city": "Scarborough",
        "budget": 6500,
    },
]


TONE_TEMPLATES = {
    "professional": "Hello, we saw your request about {category_lower} support in {city}. One of our reviewed client teams may be a fit. Would you like a short introduction?",
    "friendly": "Hi, it sounds like you are looking for help with {category_lower} work in {city}. We can suggest a vetted local option if you are still looking.",
    "short": "Hi, we may know a suitable {category_lower} option in {city}. Would you like an introduction?",
    "formal": "Hello, based on your request for {category_lower} services in {city}, we can prepare a reviewed provider introduction for your approval.",
}


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
    if any(word in lowered for word in ["urgent", "asap", "today", "this week"]):
        score += 4
    if any(word in lowered for word in ["need", "looking for", "quote"]):
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
    with connect() as connection:
        rows = [dict(row) for row in connection.execute("SELECT * FROM clients WHERE status = 'active'").fetchall()]
    ranked = sorted(
        rows,
        key=lambda row: client_fit_score(category, city, budget, row),
        reverse=True,
    )
    return ranked[0] if ranked else None


def build_outreach(category: str, city: str, tone: str = "professional") -> str:
    template = TONE_TEMPLATES.get(tone, TONE_TEMPLATES["professional"])
    return template.format(category_lower=category.lower(), city=city)


def discover_demo_leads() -> list[dict]:
    created: list[dict] = []
    with connect() as connection:
        for signal in DEMO_SIGNALS:
            existing = connection.execute("SELECT id FROM leads WHERE context = ?", (signal["text"],)).fetchone()
            if existing:
                continue
            client = find_client(signal["category"], signal["city"], signal["budget"])
            urgency = urgency_score(signal["text"])
            fit = client_fit_score(signal["category"], signal["city"], signal["budget"], client)
            priority = classify_priority(urgency, fit)
            explanation = (
                f"Priority is {priority} because urgency scored {urgency}/10 and client fit scored {fit}/10 "
                f"for {signal['category']} in {signal['city']}."
            )
            draft = build_outreach(signal["category"], signal["city"])
            cursor = connection.execute(
                """
                INSERT INTO leads (
                    source, category, city, context, urgency, budget, client_fit, priority,
                    explanation, matched_client_id, outreach_status, outreach_draft, status,
                    notes, next_action
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal["source"],
                    signal["category"],
                    signal["city"],
                    signal["text"],
                    urgency,
                    signal["budget"],
                    fit,
                    priority,
                    explanation,
                    client["id"] if client else None,
                    "Drafted",
                    draft,
                    "Qualified" if priority in {"High", "Medium"} else "New",
                    "Synthetic demo lead. Human review required before outreach.",
                    "Review outreach draft",
                ),
            )
            lead_id = cursor.lastrowid
            connection.execute(
                """
                INSERT INTO follow_up_tasks (lead_id, client_id, due_date, task, owner, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    lead_id,
                    client["id"] if client else None,
                    (date.today() + timedelta(days=1)).isoformat(),
                    "Review lead context and approve or reject outreach draft",
                    "BPO Agent",
                    "Open",
                ),
            )
            created.append({"id": lead_id, **signal})
        connection.commit()
    return created


def seed_reviews() -> None:
    reviews = [
        (1, "Demo review board", 5, "Great carpentry work and clear communication."),
        (2, "Demo review board", 4, "Helpful agent and responsive follow-up."),
        (3, "Demo review board", 2, "Slow response on a weekend security issue."),
        (4, "Demo review board", 5, "Excellent cabinet finish and installation."),
        (5, "Demo review board", 3, "Cleaning was good but scheduling was confusing."),
    ]
    with connect() as connection:
        existing = connection.execute("SELECT COUNT(*) AS count FROM reviews").fetchone()["count"]
        if existing:
            return
        for client_id, source, rating, text in reviews:
            sentiment = classify_sentiment(rating, text)
            connection.execute(
                """
                INSERT INTO reviews (client_id, source, rating, text, sentiment, response_draft, attention_required)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    source,
                    rating,
                    text,
                    sentiment,
                    draft_review_response(sentiment),
                    1 if sentiment == "negative" else 0,
                ),
            )
        connection.commit()


def classify_sentiment(rating: int, text: str) -> str:
    lowered = text.lower()
    if rating <= 2 or any(word in lowered for word in ["slow", "bad", "poor", "confusing"]):
        return "negative"
    if rating == 3:
        return "neutral"
    return "positive"


def draft_review_response(sentiment: str) -> str:
    if sentiment == "negative":
        return "Thank you for the feedback. A team member should review this and follow up with a specific resolution."
    if sentiment == "neutral":
        return "Thank you for sharing this. We will review the details and look for ways to improve the experience."
    return "Thank you for the kind feedback. We appreciate the opportunity to support your project."


def rows(query: str, params: Iterable = ()) -> list[dict]:
    with connect() as connection:
        return [dict(row) for row in connection.execute(query, tuple(params)).fetchall()]


def get_dashboard_data(filters: dict[str, str | None]) -> dict:
    where = []
    params: list[str] = []
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
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    lead_rows = rows(
        f"""
        SELECT leads.*, clients.name AS client_name
        FROM leads
        LEFT JOIN clients ON clients.id = leads.matched_client_id
        {where_sql}
        ORDER BY CASE leads.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, leads.created_at DESC
        """,
        params,
    )
    return {
        "leads": lead_rows,
        "clients": rows("SELECT * FROM clients ORDER BY name"),
        "tasks": rows(
            """
            SELECT follow_up_tasks.*, leads.context, clients.name AS client_name
            FROM follow_up_tasks
            LEFT JOIN leads ON leads.id = follow_up_tasks.lead_id
            LEFT JOIN clients ON clients.id = follow_up_tasks.client_id
            ORDER BY due_date ASC
            """
        ),
        "reviews": rows(
            """
            SELECT reviews.*, clients.name AS client_name
            FROM reviews
            LEFT JOIN clients ON clients.id = reviews.client_id
            ORDER BY attention_required DESC, rating ASC
            """
        ),
        "analytics": analytics(),
    }


def analytics() -> dict:
    lead_rows = rows("SELECT * FROM leads")
    status_counts = Counter(row["status"] for row in lead_rows)
    category_counts = Counter(row["category"] for row in lead_rows)
    city_counts = Counter(row["city"] for row in lead_rows)
    high_priority = [row for row in lead_rows if row["priority"] == "High"]
    tasks = rows("SELECT * FROM follow_up_tasks WHERE status != 'Closed'")
    return {
        "daily_lead_count": len(lead_rows),
        "leads_by_category": dict(category_counts),
        "leads_by_city": dict(city_counts),
        "high_priority_leads": len(high_priority),
        "follow_up_queue": len(tasks),
        "estimated_opportunity_value": sum(int(row["budget"]) for row in lead_rows),
        "conversion_status_summary": dict(status_counts),
    }


def dataframe_for(query: str) -> pd.DataFrame:
    return pd.DataFrame(rows(query))


def export_csv(kind: str) -> str:
    if kind == "tasks":
        frame = dataframe_for(
            """
            SELECT follow_up_tasks.id, follow_up_tasks.due_date, follow_up_tasks.task,
                   follow_up_tasks.owner, follow_up_tasks.status, leads.context, clients.name AS client_name
            FROM follow_up_tasks
            LEFT JOIN leads ON leads.id = follow_up_tasks.lead_id
            LEFT JOIN clients ON clients.id = follow_up_tasks.client_id
            ORDER BY follow_up_tasks.due_date
            """
        )
    else:
        frame = dataframe_for(
            """
            SELECT leads.id, leads.source, leads.category, leads.city, leads.context, leads.urgency,
                   leads.client_fit, leads.priority, leads.status, clients.name AS client_name,
                   leads.outreach_status, leads.next_action
            FROM leads
            LEFT JOIN clients ON clients.id = leads.matched_client_id
            ORDER BY leads.priority
            """
        )
    buffer = StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue()


def daily_report() -> str:
    data = analytics()
    lines = [
        "# NexusLead AI daily report",
        "",
        "Synthetic demo data only. Outreach remains human-reviewed.",
        "",
        f"- Daily lead count: {data['daily_lead_count']}",
        f"- High priority leads: {data['high_priority_leads']}",
        f"- Follow-up queue: {data['follow_up_queue']}",
        f"- Estimated opportunity value: ${data['estimated_opportunity_value']:,}",
        "",
        "## Leads by category",
        "",
    ]
    for category, count in data["leads_by_category"].items():
        lines.append(f"- {category}: {count}")
    lines.extend(["", "## Conversion status summary", ""])
    for status, count in data["conversion_status_summary"].items():
        lines.append(f"- {status}: {count}")
    return "\n".join(lines)
