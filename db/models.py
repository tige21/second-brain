import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional


def save_address(conn: sqlite3.Connection, name: str, address: str, coords: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO addresses (name, address, coords, saved_at) VALUES (?, ?, ?, ?)",
        (name, address, coords, now)
    )
    conn.commit()


def get_address(conn: sqlite3.Connection, name: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT name, address, coords, saved_at FROM addresses WHERE name = ?", (name,)
    ).fetchone()
    return dict(row) if row else None


def list_addresses(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT name, address, coords, saved_at FROM addresses").fetchall()
    return [dict(r) for r in rows]


def delete_address(conn: sqlite3.Connection, name: str) -> None:
    conn.execute("DELETE FROM addresses WHERE name = ?", (name,))
    conn.commit()


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def mark_notified(conn: sqlite3.Connection, event_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO notified_events (event_id, notified_at) VALUES (?, ?)",
        (event_id, now)
    )
    conn.commit()


def is_notified(conn: sqlite3.Connection, event_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM notified_events WHERE event_id = ?", (event_id,)
    ).fetchone()
    return row is not None


def update_rate_limit(conn: sqlite3.Connection, chat_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO rate_limit (chat_id, last_request_at) VALUES (?, ?)",
        (chat_id, now)
    )
    conn.commit()


def get_last_request_time(conn: sqlite3.Connection, chat_id: int) -> Optional[datetime]:
    row = conn.execute(
        "SELECT last_request_at FROM rate_limit WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    if not row:
        return None
    return datetime.fromisoformat(row[0])


def save_memory(conn: sqlite3.Connection, chat_id: int, messages: list[dict]) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO conversation_memory (chat_id, messages_json) VALUES (?, ?)",
        (chat_id, json.dumps(messages, ensure_ascii=False))
    )
    conn.commit()


def load_memory(conn: sqlite3.Connection, chat_id: int) -> list[dict]:
    row = conn.execute(
        "SELECT messages_json FROM conversation_memory WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    if not row:
        return []
    return json.loads(row[0])


def clear_memory(conn: sqlite3.Connection, chat_id: int) -> None:
    conn.execute("DELETE FROM conversation_memory WHERE chat_id = ?", (chat_id,))
    conn.commit()
