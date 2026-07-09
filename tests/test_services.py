from app.database import initialize_database
from app.services import (
    analytics,
    attach_file_metadata,
    build_outreach,
    classify_priority,
    create_lead,
    export_csv,
    find_client,
    list_users,
    row,
    seed_operational_records,
    seed_reviews,
)


def setup_module():
    initialize_database(seed=True)
    seed_operational_records()
    seed_reviews()


def test_default_roles_exist():
    roles = {user["role"] for user in list_users()}

    assert {"admin", "manager", "agent"}.issubset(roles)


def test_priority_scoring():
    assert classify_priority(9, 8) == "High"
    assert classify_priority(6, 6) == "Medium"
    assert classify_priority(4, 3) == "Low"


def test_client_matching_uses_category_and_service_area():
    client = find_client("Carpenter", "Scarborough", 6500)

    assert client is not None
    assert client["category"] == "Carpenter"
    assert "contact_email" in client


def test_outreach_is_draft_language_not_auto_send():
    draft = build_outreach("Security company", "Mississauga", tone="short")

    assert "Mississauga" in draft
    assert "Would you like" in draft


def test_create_lead_writes_audit_log():
    lead_id = create_lead(
        {
            "source": "Manual intake",
            "category": "Security company",
            "city": "Brampton",
            "context": "Warehouse operator needs urgent coverage this week",
            "budget": 7000,
            "owner": "Lead Operations Agent",
        },
        actor="Test User",
    )
    audit = row("SELECT * FROM audit_logs WHERE entity_type = 'lead' AND entity_id = ?", (lead_id,))

    assert audit is not None
    assert audit["action"] == "lead.created"


def test_attachment_metadata_is_recorded():
    lead_id = create_lead(
        {
            "source": "Manual intake",
            "category": "Cleaning service",
            "city": "Toronto",
            "context": "Office manager needs recurring cleaning quote",
            "budget": 1200,
            "owner": "Lead Operations Agent",
        },
        actor="Test User",
    )
    attachment_id = attach_file_metadata(lead_id, "brief.pdf", "application/pdf", "uploads/brief.pdf", "Test User")
    lead = row("SELECT * FROM leads WHERE id = ?", (lead_id,))

    assert attachment_id > 0
    assert lead["attachment_name"] == "brief.pdf"


def test_analytics_and_exports():
    data = analytics()
    csv_text = export_csv("leads")

    assert data["daily_lead_count"] >= 5
    assert data["high_priority_leads"] >= 1
    assert "outreach_status" in csv_text
