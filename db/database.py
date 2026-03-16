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
    from config import TELEGRAM_CHAT_ID

    # Always-safe creates (new tables, no schema changes needed)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            approved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_tokens (
            chat_id INTEGER PRIMARY KEY,
            token_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rate_limit (
            chat_id INTEGER PRIMARY KEY,
            last_request_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_memory (
            chat_id INTEGER PRIMARY KEY,
            messages_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            remind_at TEXT NOT NULL,
            sent INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS event_task_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            event_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            event_summary TEXT NOT NULL,
            event_start_utc TEXT NOT NULL,
            task_title TEXT NOT NULL,
            notified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_event_task_links_pending
            ON event_task_links (notified, event_start_utc);

    """)

    # Per-user tables: create fresh or migrate old single-user schema
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    if 'addresses' not in tables:
        # Fresh install — create with multi-user schema
        conn.executescript("""
            CREATE TABLE addresses (
                chat_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                address TEXT NOT NULL,
                coords TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, name)
            );

            CREATE TABLE settings (
                chat_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (chat_id, key)
            );

            CREATE TABLE notified_events (
                chat_id INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                notified_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, event_id)
            );

            CREATE TABLE undo_stack (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                action_type TEXT NOT NULL,
                item_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
    else:
        # Check if migration to multi-user schema is needed
        cols = {r[1] for r in conn.execute("PRAGMA table_info(addresses)")}
        if 'chat_id' not in cols:
            _migrate_to_multi_user(conn, TELEGRAM_CHAT_ID)
        # Add session_id to undo_stack if missing (incremental migration)
        undo_cols = {r[1] for r in conn.execute("PRAGMA table_info(undo_stack)")}
        if 'session_id' not in undo_cols:
            conn.execute("ALTER TABLE undo_stack ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
            conn.commit()

    conn.commit()


def _migrate_to_multi_user(conn: sqlite3.Connection, owner_chat_id: int) -> None:
    """Migrate single-user schema to multi-user by adding chat_id to per-user tables."""
    # addresses
    conn.execute("ALTER TABLE addresses RENAME TO addresses_v1")
    conn.execute("""
        CREATE TABLE addresses (
            chat_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            coords TEXT NOT NULL,
            saved_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, name)
        )
    """)
    conn.execute(
        f"INSERT INTO addresses SELECT {owner_chat_id}, name, address, coords, saved_at FROM addresses_v1"
    )
    conn.execute("DROP TABLE addresses_v1")

    # settings
    conn.execute("ALTER TABLE settings RENAME TO settings_v1")
    conn.execute("""
        CREATE TABLE settings (
            chat_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (chat_id, key)
        )
    """)
    conn.execute(
        f"INSERT INTO settings SELECT {owner_chat_id}, key, value FROM settings_v1"
    )
    conn.execute("DROP TABLE settings_v1")

    # notified_events
    conn.execute("ALTER TABLE notified_events RENAME TO notified_events_v1")
    conn.execute("""
        CREATE TABLE notified_events (
            chat_id INTEGER NOT NULL,
            event_id TEXT NOT NULL,
            notified_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, event_id)
        )
    """)
    conn.execute(
        f"INSERT INTO notified_events SELECT {owner_chat_id}, event_id, notified_at FROM notified_events_v1"
    )
    conn.execute("DROP TABLE notified_events_v1")

    # undo_stack: add chat_id and session_id columns if missing
    undo_cols = {r[1] for r in conn.execute("PRAGMA table_info(undo_stack)")}
    if 'chat_id' not in undo_cols:
        conn.execute(
            f"ALTER TABLE undo_stack ADD COLUMN chat_id INTEGER NOT NULL DEFAULT {owner_chat_id}"
        )
    if 'session_id' not in undo_cols:
        conn.execute("ALTER TABLE undo_stack ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")

    conn.commit()


_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        from config import DB_PATH
        _conn = init_db(DB_PATH)
    return _conn
