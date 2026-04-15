"""SQLite persistence for consent-based share sessions (survives server restarts)."""

import os
import sqlite3
import time

SESSION_TTL_SEC = 3600

_DB_PATH = os.path.join(os.path.dirname(__file__), "phone_tracer.db")


def _conn():
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS share_sessions (
                token TEXT PRIMARY KEY,
                phone_label TEXT NOT NULL,
                lat REAL,
                lng REAL,
                accuracy_m REAL,
                address TEXT,
                updated_at REAL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )


def cleanup_expired():
    cutoff = time.time() - SESSION_TTL_SEC
    with _conn() as db:
        db.execute("DELETE FROM share_sessions WHERE created_at < ?", (cutoff,))


def create_session(token: str, phone_label: str) -> None:
    init_db()
    now = time.time()
    with _conn() as db:
        db.execute(
            """INSERT INTO share_sessions
               (token, phone_label, lat, lng, accuracy_m, address, updated_at, status, created_at)
               VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, 'pending', ?)""",
            (token, phone_label, now),
        )


def get_session(token: str):
    init_db()
    cleanup_expired()
    with _conn() as db:
        row = db.execute("SELECT * FROM share_sessions WHERE token = ?", (token,)).fetchone()
    if not row:
        return None
    return dict(row)


def update_session_gps(token: str, lat: float, lng: float, accuracy_m, address):
    init_db()
    now = time.time()
    with _conn() as db:
        db.execute(
            """UPDATE share_sessions SET lat=?, lng=?, accuracy_m=?, address=?,
               updated_at=?, status='live' WHERE token=?""",
            (lat, lng, accuracy_m, address, now, token),
        )


init_db()
