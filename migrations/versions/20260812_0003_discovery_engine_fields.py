"""add discovery engine product fields

Revision ID: 20260812_0003
Revises: 20260811_0002
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_0003"
down_revision = "20260811_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    client_columns = [
        ("services", sa.Text(), ""),
        ("target_customer", sa.Text(), ""),
        ("target_industries", sa.Text(), ""),
        ("service_categories", sa.Text(), ""),
        ("keywords", sa.Text(), ""),
        ("negative_keywords", sa.Text(), ""),
        ("preferred_lead_types", sa.Text(), ""),
        ("outreach_preferences", sa.Text(), ""),
        ("qualification_rules", sa.Text(), ""),
    ]
    for name, column_type, default in client_columns:
        op.add_column("clients", sa.Column(name, column_type, nullable=False, server_default=default))

    lead_columns = [
        ("source_url", sa.Text(), ""),
        ("raw_source_text", sa.Text(), ""),
        ("detected_intent", sa.String(length=120), ""),
        ("urgency_label", sa.String(length=32), ""),
        ("estimated_value", sa.Integer(), "0"),
        ("contact_info", sa.Text(), ""),
        ("match_score", sa.Integer(), "0"),
        ("match_reasons", sa.Text(), ""),
        ("workflow_state", sa.String(length=120), "Awaiting approval"),
        ("duplicate_probability", sa.Integer(), "0"),
        ("spam_probability", sa.Integer(), "0"),
    ]
    for name, column_type, default in lead_columns:
        op.add_column("leads", sa.Column(name, column_type, nullable=False, server_default=default))

    op.create_table(
        "automation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workflow", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("records_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("automation_runs")
    for column in [
        "spam_probability",
        "duplicate_probability",
        "workflow_state",
        "match_reasons",
        "match_score",
        "contact_info",
        "estimated_value",
        "urgency_label",
        "detected_intent",
        "raw_source_text",
        "source_url",
    ]:
        op.drop_column("leads", column)
    for column in [
        "qualification_rules",
        "outreach_preferences",
        "preferred_lead_types",
        "negative_keywords",
        "keywords",
        "service_categories",
        "target_industries",
        "target_customer",
        "services",
    ]:
        op.drop_column("clients", column)
