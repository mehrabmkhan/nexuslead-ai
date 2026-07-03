from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable


DEFAULT_DB_PATH = Path("data/nexuslead_demo.db")


def db_path() -> Path:
    return Path(os.getenv("NEXUSLEAD_DB", str(DEFAULT_DB_PATH)))


def connect() -> sqlite3.Connection:
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
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                city TEXT NOT NULL,
                service_area TEXT NOT NULL,
                min_budget INTEGER NOT NULL,
                max_budget INTEGER NOT NULL,
                status TEXT NOT NULL
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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(matched_client_id) REFERENCES clients(id)
            );

            CREATE TABLE IF NOT EXISTS follow_up_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                client_id INTEGER,
                due_date TEXT NOT NULL,
                task TEXT NOT NULL,
                owner TEXT NOT NULL,
                status TEXT NOT NULL,
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
                FOREIGN KEY(client_id) REFERENCES clients(id)
            );
            """
        )
        if seed:
            _seed(connection)
        connection.commit()


def _seed(connection: sqlite3.Connection) -> None:
    existing = connection.execute("SELECT COUNT(*) AS count FROM clients").fetchone()["count"]
    if existing:
        return

    clients = [
        ("Northline Carpentry", "Carpenter", "Toronto", "Toronto, Scarborough, North York", 500, 12000, "active"),
        ("Scarborough Realty Group", "Real estate agent", "Scarborough", "Scarborough, Toronto East", 0, 5000, "active"),
        ("ShieldPoint Security", "Security company", "Mississauga", "GTA, Mississauga, Brampton", 1000, 25000, "active"),
        ("Oak & Grain Cabinetry", "Custom cabinetry", "Toronto", "Toronto, Etobicoke, Vaughan", 1500, 30000, "active"),
        ("BrightNest Cleaning", "Cleaning service", "Toronto", "Toronto, Scarborough, Markham", 250, 6000, "active"),
    ]
    connection.executemany(
        """
        INSERT INTO clients (name, category, city, service_area, min_budget, max_budget, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        clients,
    )
