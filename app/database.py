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
            """
        )
        _ensure_column(connection, "users", "created_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "contact_email", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "notes", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "created_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "owner", "TEXT NOT NULL DEFAULT 'Unassigned'")
        _ensure_column(connection, "leads", "attachment_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "attachment_path", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "attachment_type", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "leads", "updated_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "follow_up_tasks", "created_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "reviews", "created_at", "TEXT NOT NULL DEFAULT ''")
        if seed:
            _seed(connection)
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
            "active",
        ),
    ]
    connection.executemany(
        """
        INSERT INTO clients (name, category, city, service_area, min_budget, max_budget, contact_email, notes, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        clients,
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
        return

    clients = [
        ("Northline Carpentry", "Carpenter", "Toronto", "Toronto, Scarborough, North York", 500, 12000, "ops+northline@nextrns.local", "Prefers residential repair and renovation leads with photos attached.", "active"),
        ("Scarborough Realty Group", "Real estate agent", "Scarborough", "Scarborough, Toronto East", 0, 5000, "ops+realty@nextrns.local", "Best fit is buyer and seller intake in Scarborough and Toronto East.", "active"),
        ("ShieldPoint Security", "Security company", "Mississauga", "GTA, Mississauga, Brampton", 1000, 25000, "ops+shieldpoint@nextrns.local", "Prioritize commercial and warehouse security requests.", "active"),
        ("Oak & Grain Cabinetry", "Custom cabinetry", "Toronto", "Toronto, Etobicoke, Vaughan", 1500, 30000, "ops+oakgrain@nextrns.local", "High-value kitchen remodel and custom storage projects.", "active"),
        ("BrightNest Cleaning", "Cleaning service", "Toronto", "Toronto, Scarborough, Markham", 250, 6000, "ops+brightnest@nextrns.local", "Recurring commercial and property management cleaning leads.", "active"),
    ]
    connection.executemany(
        """
        INSERT INTO clients (name, category, city, service_area, min_budget, max_budget, contact_email, notes, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        clients,
    )
