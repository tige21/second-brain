import sqlite3
import os


def init_db(db_path: str) -> sqlite3.Connection:
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _run_migrations(conn)
    return conn


def _run_migrations(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS addresses (
            name TEXT PRIMARY KEY,
            address TEXT NOT NULL,
            coords TEXT NOT NULL,
            saved_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notified_events (
            event_id TEXT PRIMARY KEY,
            notified_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rate_limit (
            chat_id INTEGER PRIMARY KEY,
            last_request_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_memory (
            chat_id INTEGER PRIMARY KEY,
            messages_json TEXT NOT NULL
        );
    """)
    conn.commit()


_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        from config import DB_PATH
        _conn = init_db(DB_PATH)
    return _conn
