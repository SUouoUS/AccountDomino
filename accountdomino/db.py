"""SQLite 연결과 스키마."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    service_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    profile        TEXT NOT NULL CHECK (profile IN ('before', 'after')),
    service_id     TEXT NOT NULL REFERENCES services(service_id),
    username       TEXT NOT NULL,
    password_group TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    salt           TEXT NOT NULL,
    mfa_enabled    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (profile, service_id)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario          TEXT,
    profile           TEXT NOT NULL,
    leaked_service_id TEXT NOT NULL,
    leaked_username   TEXT NOT NULL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS login_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER REFERENCES runs(run_id),
    profile    TEXT NOT NULL,
    service_id TEXT NOT NULL,
    username   TEXT NOT NULL,
    result     TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path) if path else config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection, reset: bool = False) -> None:
    if reset:
        conn.executescript(
            "DROP TABLE IF EXISTS login_logs; DROP TABLE IF EXISTS runs;"
            "DROP TABLE IF EXISTS accounts; DROP TABLE IF EXISTS services;"
        )
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT OR IGNORE INTO services(service_id, name) VALUES (?, ?)",
        list(config.SERVICES.items()),
    )
    conn.commit()
