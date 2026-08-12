from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable


DEFAULT_DB_PATH = Path("data/nexuslead.db")


def database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def db_path() -> Path:
    url = database_url()
    if url and url.startswith("sqlite:///"):
        return Path(url.replace("sqlite:///", "", 1))
    return Path(os.getenv("NEXUSLEAD_DB", str(DEFAULT_DB_PATH)))


def database_summary() -> dict:
    url = database_url()
    if url and url.startswith(("postgres://", "postgresql://")):
        return {"engine": "postgresql", "configured": True, "driver": "psycopg"}
    return {"engine": "sqlite", "configured": True, "path": str(db_path())}


def database_health() -> dict:
    try:
        with connect() as connection:
            connection.execute("SELECT 1")
        return {**database_summary(), "status": "ok"}
    except Exception as exc:  # pragma: no cover - used by deployed health checks
        return {**database_summary(), "status": "error", "detail": str(exc)}


def connect() -> sqlite3.Connection:
    url = database_url()
    if url and url.startswith(("postgres://", "postgresql://")):
        return PostgresConnection(url)  # type: ignore[return-value]
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def execute_many(sql: str, rows: Iterable[tuple]) -> None:
    with connect() as connection:
        connection.executemany(sql, rows)
        connection.commit()


def initialize_database(seed: bool = True) -> None:
    if database_url() and database_url().startswith(("postgres://", "postgresql://")):
        with connect() as connection:
            if seed:
                _seed_postgres(connection)
            connection.commit()
        return

    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                city TEXT NOT NULL,
                service_area TEXT NOT NULL,
                min_budget INTEGER NOT NULL,
                max_budget INTEGER NOT NULL,
                contact_email TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                services TEXT NOT NULL DEFAULT '',
                target_customer TEXT NOT NULL DEFAULT '',
                target_industries TEXT NOT NULL DEFAULT '',
                service_categories TEXT NOT NULL DEFAULT '',
                keywords TEXT NOT NULL DEFAULT '',
                negative_keywords TEXT NOT NULL DEFAULT '',
                preferred_lead_types TEXT NOT NULL DEFAULT '',
                outreach_preferences TEXT NOT NULL DEFAULT '',
                qualification_rules TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                city TEXT NOT NULL,
                context TEXT NOT NULL,
                urgency INTEGER NOT NULL,
                budget INTEGER NOT NULL,
                client_fit INTEGER NOT NULL,
                priority TEXT NOT NULL,
                explanation TEXT NOT NULL,
                matched_client_id INTEGER,
                outreach_status TEXT NOT NULL,
                outreach_draft TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                next_action TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL DEFAULT 'Unassigned',
                attachment_name TEXT NOT NULL DEFAULT '',
                attachment_path TEXT NOT NULL DEFAULT '',
                attachment_type TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                raw_source_text TEXT NOT NULL DEFAULT '',
                detected_intent TEXT NOT NULL DEFAULT '',
                urgency_label TEXT NOT NULL DEFAULT '',
                estimated_value INTEGER NOT NULL DEFAULT 0,
                contact_info TEXT NOT NULL DEFAULT '',
                match_score INTEGER NOT NULL DEFAULT 0,
                match_reasons TEXT NOT NULL DEFAULT '',
                workflow_state TEXT NOT NULL DEFAULT 'Awaiting approval',
                duplicate_probability INTEGER NOT NULL DEFAULT 0,
                spam_probability INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(matched_client_id) REFERENCES clients(id)
            );

            CREATE TABLE IF NOT EXISTS lead_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                actor TEXT NOT NULL,
                event_type TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(lead_id) REFERENCES leads(id)
            );

            CREATE TABLE IF NOT EXISTS follow_up_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                client_id INTEGER,
                due_date TEXT NOT NULL,
                task TEXT NOT NULL,
                owner TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(lead_id) REFERENCES leads(id),
                FOREIGN KEY(client_id) REFERENCES clients(id)
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                rating INTEGER NOT NULL,
                text TEXT NOT NULL,
                sentiment TEXT NOT NULL,
                response_draft TEXT NOT NULL,
                attention_required INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id)
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS lead_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                content_type TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(lead_id) REFERENCES leads(id)
            );

            CREATE TABLE IF NOT EXISTS import_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                source TEXT NOT NULL,
                file_name TEXT NOT NULL DEFAULT '',
                total_rows INTEGER NOT NULL DEFAULT 0,
                created_count INTEGER NOT NULL DEFAULT 0,
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS automation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow TEXT NOT NULL,
                status TEXT NOT NULL,
                records_processed INTEGER NOT NULL DEFAULT 0,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        _ensure_column(connection, "users", "created_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "contact_email", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "notes", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "services", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "target_customer", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "target_industries", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "service_categories", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "keywords", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "negative_keywords", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "preferred_lead_types", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "outreach_preferences", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "qualification_rules", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "created_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "owner", "TEXT NOT NULL DEFAULT 'Unassigned'")
        _ensure_column(connection, "leads", "attachment_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "attachment_path", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "attachment_type", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "source_url", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "raw_source_text", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "detected_intent", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "urgency_label", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "estimated_value", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "leads", "contact_info", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "match_score", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "leads", "match_reasons", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "workflow_state", "TEXT NOT NULL DEFAULT 'Awaiting approval'")
        _ensure_column(connection, "leads", "duplicate_probability", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "leads", "spam_probability", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "leads", "updated_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "follow_up_tasks", "created_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "reviews", "created_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "import_batches", "file_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "import_batches", "summary", "TEXT NOT NULL DEFAULT ''")
        if seed:
            _seed(connection)
        _backfill_client_profiles(connection)
        connection.commit()


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _seed(connection: sqlite3.Connection) -> None:
    users = [
        (
            "admin@nextrns.local",
            "NextRNS Admin",
            "admin",
            "pbkdf2_sha256$200000$local-admin$5e4585e20b17aec7df3c62f081b85875e35cf918fa696bafc323375a2731e2c9",
        ),
        (
            "manager@nextrns.local",
            "Operations Manager",
            "manager",
            "pbkdf2_sha256$200000$local-manager$028fb7197ef6de45ab9ba05df9aa7b7c550f3d9c883f127f51576ac5109976f1",
        ),
        (
            "agent@nextrns.local",
            "Lead Operations Agent",
            "agent",
            "pbkdf2_sha256$200000$local-agent$b7856edb7f5f96ecdcfa31d4cdf1b79173b7343d8286a9c321dfdb41bacaf90e",
        ),
    ]
    connection.executemany(
        """
        INSERT OR IGNORE INTO users (email, name, role, password_hash)
        VALUES (?, ?, ?, ?)
        """,
        users,
    )

    existing = connection.execute("SELECT COUNT(*) AS count FROM clients").fetchone()["count"]
    if existing:
        _backfill_client_profiles(connection)
        return

    clients = [
        (
            "Northline Carpentry",
            "Carpenter",
            "Toronto",
            "Toronto, Scarborough, North York",
            500,
            12000,
            "ops+northline@nextrns.local",
            "Prefers residential repair and renovation leads with photos attached.",
            "Carpentry, repair, renovation, custom woodwork",
            "Property managers and homeowners",
            "Property management, retail, residential",
            "Carpenter, renovation, repair",
            "carpenter, repair, renovation, contractor, quote",
            "jobs, course, diy, training",
            "Repair requests, renovation quotes, water damage",
            "Professional, concise, request approval before contact",
            "Service area match plus project value above $500.",
            "active",
        ),
        (
            "Scarborough Realty Group",
            "Real estate agent",
            "Scarborough",
            "Scarborough, Toronto East",
            0,
            5000,
            "ops+realty@nextrns.local",
            "Best fit is buyer and seller intake in Scarborough and Toronto East.",
            "Buyer representation, seller representation, valuation",
            "Home buyers and sellers",
            "Residential real estate",
            "Real estate agent, realtor",
            "buyer, seller, agent, realtor, showing, valuation",
            "jobs, license, course, rent only",
            "Buyer requests, seller consultations",
            "Friendly, consultative, no pressure",
            "Location must be Scarborough or Toronto East.",
            "active",
        ),
        (
            "ShieldPoint Security",
            "Security company",
            "Mississauga",
            "GTA, Mississauga, Brampton",
            1000,
            25000,
            "ops+shieldpoint@nextrns.local",
            "Prioritize commercial and warehouse security requests.",
            "Commercial security, warehouse patrol, event security",
            "Facilities managers and operators",
            "Logistics, warehousing, retail, events",
            "Security company, patrol, guarding",
            "security, patrol, guard, warehouse, coverage, overnight",
            "jobs, license, training, course",
            "Urgent coverage requests, recurring patrols",
            "Professional and urgent-response oriented",
            "Commercial intent and budget above $1,000.",
            "active",
        ),
        (
            "Oak & Grain Cabinetry",
            "Custom cabinetry",
            "Toronto",
            "Toronto, Etobicoke, Vaughan",
            1500,
            30000,
            "ops+oakgrain@nextrns.local",
            "High-value kitchen remodel and custom storage projects.",
            "Custom cabinetry, kitchen renovation, storage",
            "Homeowners and renovation contractors",
            "Residential renovation",
            "Custom cabinetry, kitchen remodel",
            "cabinet, cabinetry, kitchen, remodel, custom storage",
            "jobs, diy, course, training",
            "Kitchen remodels, storage projects, custom quotes",
            "Design-forward, helpful, approval before handoff",
            "Estimated value should be above $1,500.",
            "active",
        ),
        (
            "BrightNest Cleaning",
            "Cleaning service",
            "Toronto",
            "Toronto, Scarborough, Markham",
            250,
            6000,
            "ops+brightnest@nextrns.local",
            "Recurring commercial and property management cleaning leads.",
            "Commercial cleaning, recurring office cleaning",
            "Office managers and property managers",
            "Commercial property, office operations",
            "Cleaning service, janitorial",
            "cleaning, janitorial, recurring, office, property",
            "jobs, supplies, course, training",
            "Recurring service requests, property management needs",
            "Friendly and operations-focused",
            "Recurring or commercial context preferred.",
            "active",
        ),
    ]
    connection.executemany(
        """
        INSERT INTO clients (
            name, category, city, service_area, min_budget, max_budget, contact_email, notes,
            services, target_customer, target_industries, service_categories, keywords,
            negative_keywords, preferred_lead_types, outreach_preferences, qualification_rules, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        clients,
    )
    _backfill_client_profiles(connection)


def _backfill_client_profiles(connection) -> None:
    profiles = [
        ("Northline Carpentry", "Carpentry, repair, renovation, custom woodwork", "Property managers and homeowners", "Property management, retail, residential", "Carpenter, renovation, repair", "carpenter, repair, renovation, contractor, quote", "jobs, course, diy, training", "Repair requests, renovation quotes, water damage", "Professional, concise, request approval before contact", "Service area match plus project value above $500."),
        ("Scarborough Realty Group", "Buyer representation, seller representation, valuation", "Home buyers and sellers", "Residential real estate", "Real estate agent, realtor", "buyer, seller, agent, realtor, showing, valuation", "jobs, license, course, rent only", "Buyer requests, seller consultations", "Friendly, consultative, no pressure", "Location must be Scarborough or Toronto East."),
        ("ShieldPoint Security", "Commercial security, warehouse patrol, event security", "Facilities managers and operators", "Logistics, warehousing, retail, events", "Security company, patrol, guarding", "security, patrol, guard, warehouse, coverage, overnight", "jobs, license, training, course", "Urgent coverage requests, recurring patrols", "Professional and urgent-response oriented", "Commercial intent and budget above $1,000."),
        ("Oak & Grain Cabinetry", "Custom cabinetry, kitchen renovation, storage", "Homeowners and renovation contractors", "Residential renovation", "Custom cabinetry, kitchen remodel", "cabinet, cabinetry, kitchen, remodel, custom storage", "jobs, diy, course, training", "Kitchen remodels, storage projects, custom quotes", "Design-forward, helpful, approval before handoff", "Estimated value should be above $1,500."),
        ("BrightNest Cleaning", "Commercial cleaning, recurring office cleaning", "Office managers and property managers", "Commercial property, office operations", "Cleaning service, janitorial", "cleaning, janitorial, recurring, office, property", "jobs, supplies, course, training", "Recurring service requests, property management needs", "Friendly and operations-focused", "Recurring or commercial context preferred."),
    ]
    for profile in profiles:
        connection.execute(
            """
            UPDATE clients
            SET services = CASE WHEN services = '' THEN ? ELSE services END,
                target_customer = CASE WHEN target_customer = '' THEN ? ELSE target_customer END,
                target_industries = CASE WHEN target_industries = '' THEN ? ELSE target_industries END,
                service_categories = CASE WHEN service_categories = '' THEN ? ELSE service_categories END,
                keywords = CASE WHEN keywords = '' THEN ? ELSE keywords END,
                negative_keywords = CASE WHEN negative_keywords = '' THEN ? ELSE negative_keywords END,
                preferred_lead_types = CASE WHEN preferred_lead_types = '' THEN ? ELSE preferred_lead_types END,
                outreach_preferences = CASE WHEN outreach_preferences = '' THEN ? ELSE outreach_preferences END,
                qualification_rules = CASE WHEN qualification_rules = '' THEN ? ELSE qualification_rules END
            WHERE name = ?
            """,
            (*profile[1:], profile[0]),
        )


class QueryResult:
    def __init__(self, rows: list[dict] | None = None, lastrowid: int | None = None):
        self._rows = rows or []
        self.lastrowid = lastrowid

    def fetchone(self) -> dict | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict]:
        return self._rows


class PostgresConnection:
    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row

        self._connection = psycopg.connect(url, row_factory=dict_row)

    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type:
            self._connection.rollback()
        self._connection.close()

    def execute(self, sql: str, params: Iterable = ()) -> QueryResult:
        sql_text = self._translate_sql(sql)
        lower = sql_text.strip().lower()
        should_return_id = lower.startswith("insert ") and " returning " not in lower
        if should_return_id:
            sql_text = f"{sql_text.rstrip()} RETURNING id"
        with self._connection.cursor() as cursor:
            cursor.execute(sql_text, tuple(params))
            if cursor.description:
                found = cursor.fetchall()
            else:
                found = []
            lastrowid = found[0]["id"] if should_return_id and found else None
        return QueryResult(found, lastrowid)

    def executemany(self, sql: str, records: Iterable[tuple]) -> None:
        sql_text = self._translate_sql(sql)
        with self._connection.cursor() as cursor:
            cursor.executemany(sql_text, list(records))

    def executescript(self, sql: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(sql)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    @staticmethod
    def _translate_sql(sql: str) -> str:
        return sql.replace("?", "%s")


def _seed_postgres(connection) -> None:
    users = [
        (
            "admin@nextrns.local",
            "NextRNS Admin",
            "admin",
            "pbkdf2_sha256$200000$local-admin$5e4585e20b17aec7df3c62f081b85875e35cf918fa696bafc323375a2731e2c9",
        ),
        (
            "manager@nextrns.local",
            "Operations Manager",
            "manager",
            "pbkdf2_sha256$200000$local-manager$028fb7197ef6de45ab9ba05df9aa7b7c550f3d9c883f127f51576ac5109976f1",
        ),
        (
            "agent@nextrns.local",
            "Lead Operations Agent",
            "agent",
            "pbkdf2_sha256$200000$local-agent$b7856edb7f5f96ecdcfa31d4cdf1b79173b7343d8286a9c321dfdb41bacaf90e",
        ),
    ]
    connection.executemany(
        """
        INSERT INTO users (email, name, role, password_hash)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (email) DO NOTHING
        """,
        users,
    )

    existing = connection.execute("SELECT COUNT(*) AS count FROM clients").fetchone()["count"]
    if existing:
        _backfill_client_profiles(connection)
        return

    clients = [
        ("Northline Carpentry", "Carpenter", "Toronto", "Toronto, Scarborough, North York", 500, 12000, "ops+northline@nextrns.local", "Prefers residential repair and renovation leads with photos attached.", "Carpentry, repair, renovation, custom woodwork", "Property managers and homeowners", "Property management, retail, residential", "Carpenter, renovation, repair", "carpenter, repair, renovation, contractor, quote", "jobs, course, diy, training", "Repair requests, renovation quotes, water damage", "Professional, concise, request approval before contact", "Service area match plus project value above $500.", "active"),
        ("Scarborough Realty Group", "Real estate agent", "Scarborough", "Scarborough, Toronto East", 0, 5000, "ops+realty@nextrns.local", "Best fit is buyer and seller intake in Scarborough and Toronto East.", "Buyer representation, seller representation, valuation", "Home buyers and sellers", "Residential real estate", "Real estate agent, realtor", "buyer, seller, agent, realtor, showing, valuation", "jobs, license, course, rent only", "Buyer requests, seller consultations", "Friendly, consultative, no pressure", "Location must be Scarborough or Toronto East.", "active"),
        ("ShieldPoint Security", "Security company", "Mississauga", "GTA, Mississauga, Brampton", 1000, 25000, "ops+shieldpoint@nextrns.local", "Prioritize commercial and warehouse security requests.", "Commercial security, warehouse patrol, event security", "Facilities managers and operators", "Logistics, warehousing, retail, events", "Security company, patrol, guarding", "security, patrol, guard, warehouse, coverage, overnight", "jobs, license, training, course", "Urgent coverage requests, recurring patrols", "Professional and urgent-response oriented", "Commercial intent and budget above $1,000.", "active"),
        ("Oak & Grain Cabinetry", "Custom cabinetry", "Toronto", "Toronto, Etobicoke, Vaughan", 1500, 30000, "ops+oakgrain@nextrns.local", "High-value kitchen remodel and custom storage projects.", "Custom cabinetry, kitchen renovation, storage", "Homeowners and renovation contractors", "Residential renovation", "Custom cabinetry, kitchen remodel", "cabinet, cabinetry, kitchen, remodel, custom storage", "jobs, diy, course, training", "Kitchen remodels, storage projects, custom quotes", "Design-forward, helpful, approval before handoff", "Estimated value should be above $1,500.", "active"),
        ("BrightNest Cleaning", "Cleaning service", "Toronto", "Toronto, Scarborough, Markham", 250, 6000, "ops+brightnest@nextrns.local", "Recurring commercial and property management cleaning leads.", "Commercial cleaning, recurring office cleaning", "Office managers and property managers", "Commercial property, office operations", "Cleaning service, janitorial", "cleaning, janitorial, recurring, office, property", "jobs, supplies, course, training", "Recurring service requests, property management needs", "Friendly and operations-focused", "Recurring or commercial context preferred.", "active"),
    ]
    connection.executemany(
        """
        INSERT INTO clients (
            name, category, city, service_area, min_budget, max_budget, contact_email, notes,
            services, target_customer, target_industries, service_categories, keywords,
            negative_keywords, preferred_lead_types, outreach_preferences, qualification_rules, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        clients,
    )
    _backfill_client_profiles(connection)
