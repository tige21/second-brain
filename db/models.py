import json
import sqlite3
from datetime import datetime, timezone, timedelta


# ── Addresses ─────────────────────────────────────────────────────────────────

def save_address(conn: sqlite3.Connection, chat_id: int, name: str, address: str, coords: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO addresses (chat_id, name, address, coords, saved_at) VALUES (?, ?, ?, ?, ?)",
        (chat_id, name, address, coords, now)
    )
    conn.commit()


def get_address(conn: sqlite3.Connection, chat_id: int, name: str) -> dict | None:
    row = conn.execute(
        "SELECT name, address, coords, saved_at FROM addresses WHERE chat_id = ? AND name = ?",
        (chat_id, name)
    ).fetchone()
    return dict(row) if row else None


def list_addresses(conn: sqlite3.Connection, chat_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT name, address, coords, saved_at FROM addresses WHERE chat_id = ?", (chat_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def delete_address(conn: sqlite3.Connection, chat_id: int, name: str) -> None:
    conn.execute("DELETE FROM addresses WHERE chat_id = ? AND name = ?", (chat_id, name))
    conn.commit()


# ── Settings ──────────────────────────────────────────────────────────────────

def set_setting(conn: sqlite3.Connection, chat_id: int, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings (chat_id, key, value) VALUES (?, ?, ?)",
        (chat_id, key, value)
    )
    conn.commit()


def get_setting(conn: sqlite3.Connection, chat_id: int, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM settings WHERE chat_id = ? AND key = ?", (chat_id, key)
    ).fetchone()
    return row[0] if row else None


# ── Notified events ───────────────────────────────────────────────────────────

def mark_notified(conn: sqlite3.Connection, chat_id: int, event_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO notified_events (chat_id, event_id, notified_at) VALUES (?, ?, ?)",
        (chat_id, event_id, now)
    )
    conn.commit()


def is_notified(conn: sqlite3.Connection, chat_id: int, event_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM notified_events WHERE chat_id = ? AND event_id = ?", (chat_id, event_id)
    ).fetchone()
    return row is not None


def cleanup_old_notified(conn: sqlite3.Connection, chat_id: int, days: int = 7) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn.execute(
        "DELETE FROM notified_events WHERE chat_id = ? AND notified_at < ?", (chat_id, cutoff)
    )
    conn.commit()


# ── Reminders ─────────────────────────────────────────────────────────────────

def save_reminder(conn: sqlite3.Connection, chat_id: int, text: str, remind_at_utc: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO reminders (chat_id, text, remind_at, sent, created_at) VALUES (?, ?, ?, 0, ?)",
        (chat_id, text, remind_at_utc, now),
    )
    conn.commit()
    return cur.lastrowid


def get_due_reminders(conn: sqlite3.Connection) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    rows = conn.execute(
        "SELECT id, chat_id, text FROM reminders WHERE remind_at <= ? AND sent = 0",
        (now,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_reminder_sent(conn: sqlite3.Connection, reminder_id: int) -> None:
    conn.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
    conn.commit()


# ── Undo stack ────────────────────────────────────────────────────────────────

def push_undo(conn: sqlite3.Connection, chat_id: int, action_type: str, item_id: str, summary: str, session_id: str = '') -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO undo_stack (chat_id, session_id, action_type, item_id, summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, session_id, action_type, item_id, summary, now),
    )
    # Keep only last 20 entries per user
    conn.execute(
        "DELETE FROM undo_stack WHERE chat_id = ? AND id NOT IN "
        "(SELECT id FROM undo_stack WHERE chat_id = ? ORDER BY id DESC LIMIT 20)",
        (chat_id, chat_id)
    )
    conn.commit()


def pop_undo_session(conn: sqlite3.Connection, chat_id: int) -> list[dict]:
    """Pop all actions from the most recent session for this user."""
    row = conn.execute(
        "SELECT id, session_id FROM undo_stack WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
        (chat_id,)
    ).fetchone()
    if not row:
        return []
    session_id = row['session_id']

    # Empty session_id means a legacy/migrated row — treat it as a single-item session
    # to avoid accidentally grouping unrelated old actions together.
    if not session_id:
        rows = conn.execute(
            "SELECT id, action_type, item_id, summary FROM undo_stack "
            "WHERE chat_id = ? AND id = ? ORDER BY id DESC",
            (chat_id, row['id'])
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, action_type, item_id, summary FROM undo_stack "
            "WHERE chat_id = ? AND session_id = ? ORDER BY id DESC",
            (chat_id, session_id)
        ).fetchall()

    if not rows:
        return []
    ids = [r['id'] for r in rows]
    conn.execute(
        f"DELETE FROM undo_stack WHERE id IN ({','.join(['?'] * len(ids))})", tuple(ids)
    )
    conn.commit()
    return [dict(r) for r in rows]


# ── Rate limit ────────────────────────────────────────────────────────────────

def update_rate_limit(conn: sqlite3.Connection, chat_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO rate_limit (chat_id, last_request_at) VALUES (?, ?)",
        (chat_id, now)
    )
    conn.commit()


def get_last_request_time(conn: sqlite3.Connection, chat_id: int) -> datetime | None:
    row = conn.execute(
        "SELECT last_request_at FROM rate_limit WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    if not row:
        return None
    return datetime.fromisoformat(row[0])


# ── Conversation memory ───────────────────────────────────────────────────────

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


# ── Users ─────────────────────────────────────────────────────────────────────

def get_or_create_user(conn: sqlite3.Connection, chat_id: int, username: str = None) -> tuple[dict, bool]:
    """Returns (user_dict, is_new)."""
    row = conn.execute(
        "SELECT chat_id, username, approved FROM users WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    if row:
        return dict(row), False
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users (chat_id, username, approved, created_at) VALUES (?, ?, 0, ?)",
        (chat_id, username, now)
    )
    conn.commit()
    return {"chat_id": chat_id, "username": username, "approved": 0}, True


def is_user_approved(conn: sqlite3.Connection, chat_id: int) -> bool:
    row = conn.execute("SELECT approved FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
    return bool(row and row[0])


def approve_user(conn: sqlite3.Connection, chat_id: int) -> None:
    conn.execute(
        "UPDATE users SET approved = 1 WHERE chat_id = ?",
        (chat_id,)
    )
    conn.commit()


def list_pending_users(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT chat_id, username, created_at FROM users WHERE approved = 0"
    ).fetchall()
    return [dict(r) for r in rows]


def list_connected_users(conn: sqlite3.Connection) -> list[int]:
    """Return chat_ids of all approved users with Google tokens."""
    rows = conn.execute(
        "SELECT u.chat_id FROM users u "
        "JOIN user_tokens t ON u.chat_id = t.chat_id "
        "WHERE u.approved = 1"
    ).fetchall()
    return [r[0] for r in rows]


# ── User tokens ───────────────────────────────────────────────────────────────

def save_user_token(conn: sqlite3.Connection, chat_id: int, token_json: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO user_tokens (chat_id, token_json, updated_at) VALUES (?, ?, ?)",
        (chat_id, token_json, now)
    )
    conn.commit()


def get_user_token(conn: sqlite3.Connection, chat_id: int) -> str | None:
    row = conn.execute(
        "SELECT token_json FROM user_tokens WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return row[0] if row else None


# ── Event-task links ──────────────────────────────────────────────────────────

def add_event_task_link(
    conn: sqlite3.Connection,
    chat_id: int,
    event_id: str,
    task_id: str,
    event_summary: str,
    event_start_utc: str,
    task_title: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO event_task_links "
        "(chat_id, event_id, task_id, event_summary, event_start_utc, task_title, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (chat_id, event_id, task_id, event_summary, event_start_utc, task_title, now),
    )
    conn.commit()


def get_pending_event_task_links(
    conn: sqlite3.Connection,
    window_start_utc: str,
    window_end_utc: str,
) -> list[dict]:
    rows = conn.execute(
        "SELECT id, chat_id, event_id, task_id, event_summary, event_start_utc, task_title "
        "FROM event_task_links "
        "WHERE notified = 0 AND event_start_utc >= ? AND event_start_utc <= ?",
        (window_start_utc, window_end_utc),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_event_task_links_notified(conn: sqlite3.Connection, ids: list[int]) -> None:
    if not ids:
        return
    placeholders = ','.join(['?'] * len(ids))
    conn.execute(
        f"UPDATE event_task_links SET notified = 1 WHERE id IN ({placeholders})",
        tuple(ids),
    )
    conn.commit()


def cleanup_old_event_task_links(conn: sqlite3.Connection, days: int = 7) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn.execute(
        "DELETE FROM event_task_links WHERE notified = 1 AND created_at < ?",
        (cutoff,),
    )
    conn.commit()
