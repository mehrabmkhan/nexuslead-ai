from app.database import initialize_database
from app.services import (
    analytics,
    build_outreach,
    classify_priority,
    discover_demo_leads,
    export_csv,
    find_client,
    seed_reviews,
)


def setup_module():
    initialize_database(seed=True)
    discover_demo_leads()
    seed_reviews()


def test_priority_scoring():
    assert classify_priority(9, 8) == "High"
    assert classify_priority(6, 6) == "Medium"
    assert classify_priority(4, 3) == "Low"


def test_client_matching_uses_category_and_service_area():
    client = find_client("Carpenter", "Scarborough", 6500)

    assert client is not None
    assert client["category"] == "Carpenter"


def test_outreach_is_draft_language_not_auto_send():
    draft = build_outreach("Security company", "Mississauga", tone="short")

    assert "Mississauga" in draft
    assert "Would you like" in draft


def test_analytics_and_exports():
    data = analytics()
    csv_text = export_csv("leads")

    assert data["daily_lead_count"] >= 5
    assert data["high_priority_leads"] >= 1
    assert "outreach_status" in csv_text
