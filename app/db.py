"""Database layer — SQLite dengan SQLAlchemy-like simplicity (std lib sqlite3)."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .config import DB_PATH

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    target_role TEXT NOT NULL,
    headline TEXT,
    summary TEXT,
    skills TEXT,          -- JSON list
    experience TEXT,      -- JSON list[{company, role, duration, description}]
    education TEXT,       -- JSON list[{school, degree, year}]
    cv_text TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portal TEXT NOT NULL,          -- kalibrr | glints | jobstreet | linkedin | direct
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    location TEXT,
    salary TEXT,
    description TEXT,
    questions TEXT,                -- JSON list[{question, type}]
    created_at TEXT NOT NULL,
    UNIQUE(portal, company, title)
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    status TEXT NOT NULL,          -- draft | generated | queued | submitted | failed | skipped
    cover_letter TEXT,
    answers TEXT,                  -- JSON list[{question, answer}]
    -- Browser automation detail untuk auto-submit
    submit_log TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(profile_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_job ON applications(job_id);
"""


def init_db() -> None:
    """Buat tabel kalau belum ada. Idempotent."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _lock, _connect() as conn:
        return conn.execute(sql, params).fetchall()


def execute(sql: str, params: tuple = ()) -> int:
    """Run INSERT/UPDATE/DELETE, return lastrowid."""
    with _lock, _connect() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")
